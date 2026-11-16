import time
import re
import json
from typing import List, Dict, Any, Optional
from evalguard.config import settings
from evalguard.rag.vector_store import BaseVectorStore, get_vector_store
from evalguard.metrics.performance import PerformanceTracker
from evalguard.prompts import DEFAULT_SYSTEM_PROMPT

_PLACEHOLDER_KEYS = {"", "your_gemini_api_key_here", "your_openrouter_api_key_here"}


class BaseLLMClient:
    is_mock = False
    model_name = "unknown"
    is_free = False

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        raise NotImplementedError


class QuotaExceeded(RuntimeError):
    """A hard provider limit (e.g. OpenRouter free-models-per-day). Retrying or skipping questions can't help."""


def _post_with_retry(url: str, *, headers=None, json_body=None, timeout=90, retries=4) -> dict:
    """POST JSON with exponential backoff on 429/5xx (free tiers rate-limit aggressively)."""
    import requests
    last = None
    for attempt in range(retries):
        try:
            res = requests.post(url, headers=headers, json=json_body, timeout=timeout)
        except requests.RequestException as e:
            last = e
        else:
            if res.status_code not in (429, 500, 502, 503, 504):
                res.raise_for_status()
                return res.json()
            if res.status_code == 429 and re.search(r"per-day|per day|daily", res.text, re.IGNORECASE):
                raise QuotaExceeded(
                    "The LLM provider's daily request limit is used up. Wait for the reset (OpenRouter resets at 00:00 UTC), "
                    "add credits, or switch LLM_PROVIDER. Provider said: " + res.text[:180])
            last = RuntimeError(f"HTTP {res.status_code}: {res.text[:200]}")
        time.sleep(2 ** attempt * 2)
    raise RuntimeError(f"LLM request failed after {retries} attempts: {last}")


class OpenRouterLLMClient(BaseLLMClient):
    """OpenAI-compatible chat client for OpenRouter (works with ':free' models)."""

    def __init__(self, api_key: str, model_name: str, base_url: str = "https://openrouter.ai/api/v1"):
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.is_free = model_name.endswith(":free") or model_name == "openrouter/free"

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        messages = ([{"role": "system", "content": system_prompt}] if system_prompt else [])
        messages.append({"role": "user", "content": prompt})
        body = {"model": self.model_name, "messages": messages, "temperature": 0}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        for _ in range(3):  # free models occasionally return an empty completion
            data = _post_with_retry(f"{self.base_url}/chat/completions", headers=headers, json_body=body)
            if "error" in data:
                raise RuntimeError(f"OpenRouter error: {data['error']}")
            content = (data["choices"][0]["message"].get("content") or "").strip()
            if content:
                return content
        raise RuntimeError(f"OpenRouter model {self.model_name} returned empty content")


class GeminiLLMClient(BaseLLMClient):
    """Google Gemini via REST (no SDK dependency)."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model_name = model_name

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
        data = _post_with_retry(
            url,
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            json_body={"contents": [{"parts": [{"text": full_prompt}]}]},
        )
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()


class OllamaLLMClient(BaseLLMClient):
    """Client for local Ollama models."""
    is_free = True

    def __init__(self, base_url: str = "http://localhost:11434", model_name: str = "llama3"):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        data = _post_with_retry(
            f"{self.base_url}/api/generate",
            json_body={"model": self.model_name, "prompt": prompt, "system": system_prompt or "", "stream": False},
            timeout=120,
        )
        return data.get("response", "").strip()


class MockLLMClient(BaseLLMClient):
    """Deterministic local mock LLM for testing & demo without API keys."""
    is_mock = True
    is_free = True

    def __init__(self, model_name: str = "mock-eval-llm"):
        self.model_name = model_name

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        # If it's a judge/evaluation prompt expecting JSON
        if "faithfulness" in prompt.lower() and "json" in prompt.lower():
            return json.dumps({
                "score": 0.95,
                "reasoning": "All stated facts directly correspond to the provided reference context."
            })
        if "relevance" in prompt.lower() and "json" in prompt.lower():
            return json.dumps({
                "score": 0.90,
                "reasoning": "The response directly answers the user question with precise details."
            })

        # Standard RAG extraction from prompt
        context_match = re.search(r"Context:\s*(.*?)(?=\n\s*Question:|\Z)", prompt, re.DOTALL | re.IGNORECASE)
        question_match = re.search(r"Question:\s*(.*?)(?=\n\s*Answer:|\Z)", prompt, re.DOTALL | re.IGNORECASE)

        if context_match and question_match:
            context = context_match.group(1).strip()
            # Pick the most relevant sentences
            sentences = [s.strip() for s in re.split(r"[.\n]+", context) if len(s.strip()) > 15]
            if sentences:
                return "Based on the provided documentation: " + ". ".join(sentences[:2]) + "."
        return "Based on the provided guidelines, the relevant policy applies as specified in the context."


def _has_key(key: str) -> bool:
    return key.strip() not in _PLACEHOLDER_KEYS


def get_llm_client(role: str = "answer", model: Optional[str] = None) -> BaseLLMClient:
    """role='answer' builds the RAG generator; role='judge' builds the evaluation judge
    (a different OpenRouter model, so the system doesn't grade its own homework).
    `model` overrides the configured OpenRouter model (used by model-comparison experiments)."""
    provider = settings.LLM_PROVIDER
    if provider == "openrouter" and _has_key(settings.OPENROUTER_API_KEY):
        model = model or (settings.OPENROUTER_JUDGE_MODEL if role == "judge" else settings.OPENROUTER_MODEL)
        return OpenRouterLLMClient(settings.OPENROUTER_API_KEY, model, settings.OPENROUTER_BASE_URL)
    if provider == "gemini" and _has_key(settings.GEMINI_API_KEY):
        return GeminiLLMClient(api_key=settings.GEMINI_API_KEY, model_name=settings.GEMINI_MODEL)
    if provider == "ollama":
        return OllamaLLMClient(base_url=settings.OLLAMA_BASE_URL, model_name=settings.OLLAMA_MODEL)
    return MockLLMClient()


class RAGPipeline:
    """Full question -> retrieve -> answer pipeline."""

    SYSTEM_PROMPT = DEFAULT_SYSTEM_PROMPT

    def __init__(self, vector_store: Optional[BaseVectorStore] = None, llm_client: Optional[BaseLLMClient] = None,
                 system_prompt: Optional[str] = None):
        self.vector_store = vector_store or get_vector_store()
        self.llm_client = llm_client or get_llm_client()
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    def retrieve(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        k = top_k or settings.RETRIEVAL_TOP_K
        return self.vector_store.search(query=query, top_k=k)

    def format_prompt(self, query: str, contexts: List[Dict[str, Any]]) -> str:
        context_str = "\n\n".join([f"[Context Chunk {i+1}]: {c['text']}" for i, c in enumerate(contexts)])
        return f"Context:\n{context_str}\n\nQuestion: {query}\n\nAnswer:"

    def query(self, question: str, top_k: Optional[int] = None) -> Dict[str, Any]:
        t0 = time.perf_counter()
        contexts = self.retrieve(question, top_k=top_k)
        t_retrieval = (time.perf_counter() - t0) * 1000.0

        t1 = time.perf_counter()
        prompt = self.format_prompt(question, contexts)
        answer = self.llm_client.generate(prompt=prompt, system_prompt=self.system_prompt)
        t_generation = (time.perf_counter() - t1) * 1000.0

        total_latency_ms = (time.perf_counter() - t0) * 1000.0
        cost = PerformanceTracker.calculate_cost(prompt, answer, free=self.llm_client.is_free)

        return {
            "question": question,
            "answer": answer,
            "contexts": contexts,
            "retrieval_latency_ms": round(t_retrieval, 2),
            "generation_latency_ms": round(t_generation, 2),
            "total_latency_ms": round(total_latency_ms, 2),
            "estimated_cost": cost
        }
