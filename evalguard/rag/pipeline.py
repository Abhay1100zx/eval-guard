import time
import re
import json
from typing import List, Dict, Any, Iterator, Optional
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

    def stream_generate(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        """Yield the answer in pieces as the model writes it. Clients that can't stream yield it all at once."""
        yield self.generate(prompt, system_prompt)


class QuotaExceeded(RuntimeError):
    """A hard provider limit (e.g. OpenRouter free-models-per-day). Retrying or skipping questions can't help."""


def _is_daily_limit(status: int, text: str) -> bool:
    return status == 429 and bool(re.search(r"per[- ]?day|daily", text, re.IGNORECASE))  # also Gemini's "PerDay"


def _daily_limit_error(text: str) -> QuotaExceeded:
    return QuotaExceeded(
        "The LLM provider's daily request limit is used up. Wait for the reset (OpenRouter resets at 00:00 UTC), "
        "add credits, or switch LLM_PROVIDER. Provider said: " + text[:180])


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
            if _is_daily_limit(res.status_code, res.text):
                raise _daily_limit_error(res.text)
            last = RuntimeError(f"HTTP {res.status_code}: {res.text[:200]}")
        time.sleep(2 ** attempt * 2)
    raise RuntimeError(f"LLM request failed after {retries} attempts: {last}")


def _open_stream(url: str, *, headers=None, json_body=None, timeout=(10, 120)):
    """POST and return the open streaming response. No retries here: when a model is busy or out of quota the
    fallback chain moves on to the next one, which is faster than waiting. Close the response when done."""
    import requests
    try:
        res = requests.post(url, headers=headers, json=json_body, stream=True, timeout=timeout)
    except requests.RequestException as e:
        raise RuntimeError(f"Could not reach the model: {e}")
    if res.status_code != 200:
        text = res.text[:300]
        res.close()
        if _is_daily_limit(res.status_code, text):
            raise _daily_limit_error(text)
        raise RuntimeError(f"HTTP {res.status_code}: {text[:200]}")
    res.encoding = "utf-8"
    return res


def _sse_json(res) -> Iterator[dict]:
    """The JSON objects of a Server-Sent-Events response (`data: {...}` lines), until `[DONE]`."""
    for line in res.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue  # blank separators and ": keep-alive" comments
        payload = line[5:].strip()
        if payload == "[DONE]":
            return
        try:
            yield json.loads(payload)
        except ValueError:
            continue


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

    def stream_generate(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        messages = ([{"role": "system", "content": system_prompt}] if system_prompt else [])
        messages.append({"role": "user", "content": prompt})
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        res = _open_stream(f"{self.base_url}/chat/completions", headers=headers,
                           json_body={"model": self.model_name, "messages": messages, "temperature": 0, "stream": True})
        got = False
        try:
            for data in _sse_json(res):
                if "error" in data:
                    raise RuntimeError(f"OpenRouter error: {data['error']}")
                piece = ((data.get("choices") or [{}])[0].get("delta") or {}).get("content")
                if piece:
                    got = True
                    yield piece
        finally:
            res.close()
        if not got:
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

    def stream_generate(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:streamGenerateContent?alt=sse"
        res = _open_stream(url, headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
                           json_body={"contents": [{"parts": [{"text": full_prompt}]}]})
        got = False
        try:
            for data in _sse_json(res):
                parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
                piece = "".join(p.get("text", "") for p in parts)
                if piece:
                    got = True
                    yield piece
        finally:
            res.close()
        if not got:
            raise RuntimeError(f"Gemini model {self.model_name} returned empty content")


class OllamaLLMClient(BaseLLMClient):
    """Client for local Ollama models."""
    is_free = True

    def __init__(self, base_url: str = "http://localhost:11434", model_name: str = "llama3"):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name

    def available(self) -> bool:
        """True when the local server is up and the configured model is pulled (so a fallback never waits on a dead server)."""
        import requests
        try:
            names = {m.get("name", "") for m in requests.get(f"{self.base_url}/api/tags", timeout=1.5).json().get("models", [])}
        except Exception:
            return False
        return self.model_name in names or f"{self.model_name}:latest" in names

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        data = _post_with_retry(
            f"{self.base_url}/api/generate",
            json_body={"model": self.model_name, "prompt": prompt, "system": system_prompt or "", "stream": False,
                       "options": {"num_ctx": settings.OLLAMA_NUM_CTX},
                       "keep_alive": "30s"},  # Ollama's default keeps the model in RAM for 5 minutes, which starves the app on a small machine
            timeout=120, retries=1,  # a local model that timed out once is just slow; retrying would hang the request for minutes
        )
        return data.get("response", "").strip()

    def stream_generate(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        res = _open_stream(
            f"{self.base_url}/api/generate",
            json_body={"model": self.model_name, "prompt": prompt, "system": system_prompt or "", "stream": True,
                       "options": {"num_ctx": settings.OLLAMA_NUM_CTX}, "keep_alive": "30s"},
            timeout=(5, 120),
        )
        got = False
        try:
            for line in res.iter_lines(decode_unicode=True):  # newline-delimited JSON, not SSE
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                if data.get("error"):
                    raise RuntimeError(f"Ollama error: {str(data['error'])[:200]}")
                if data.get("response"):
                    got = True
                    yield data["response"]
                if data.get("done"):
                    break
        finally:
            res.close()
        if not got:
            raise RuntimeError(f"Ollama model {self.model_name} returned empty content")


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

    def stream_generate(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        yield from re.findall(r"\S+\s*", self.generate(prompt, system_prompt))  # word by word, like a real stream


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


class FallbackLLMClient(BaseLLMClient):
    """Tries each client in turn and keeps the first answer. `model_name` is the model that actually answered
    and `skipped` says why earlier ones were passed over. Chat only: a benchmark run must keep one fixed model,
    or its scores can't be compared with other runs."""

    def __init__(self, clients: List[BaseLLMClient]):
        self.clients = clients
        self.model_name = clients[0].model_name
        self.is_mock = clients[0].is_mock
        self.is_free = all(c.is_free for c in clients)
        self.skipped: List[str] = []
        self._quota_hit: set = set()  # providers (by class) whose daily limit is used up; kept so a second call doesn't retry them

    def _skip(self, why: str) -> None:
        if why not in self.skipped:
            self.skipped.append(why)

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        for c in self.clients:
            if type(c) in self._quota_hit:  # a daily limit is per account, so a sibling model from the same provider can't help
                continue
            try:
                out = c.generate(prompt, system_prompt)
            except QuotaExceeded:
                self._quota_hit.add(type(c))
                self._skip(f"{c.model_name}: daily limit used up")
            except Exception as e:
                self._skip(f"{c.model_name}: {str(e)[:90]}")
            else:
                self.model_name = c.model_name
                return out
        raise self._all_failed()

    def stream_generate(self, prompt: str, system_prompt: Optional[str] = None) -> Iterator[str]:
        """Same fallback as generate(), but only until the first piece arrives: a half-written answer can't be
        handed to another model, so a failure after that point is raised to the caller (who keeps what it got)."""
        for c in self.clients:
            if type(c) in self._quota_hit:
                continue
            started = False
            try:
                for piece in c.stream_generate(prompt, system_prompt):
                    if not started:
                        started = True
                        self.model_name = c.model_name
                    yield piece
                return
            except QuotaExceeded:
                if started:
                    raise
                self._quota_hit.add(type(c))
                self._skip(f"{c.model_name}: daily limit used up")
            except Exception as e:
                if started:
                    raise
                self._skip(f"{c.model_name}: {str(e)[:90]}")
        raise self._all_failed()

    def _all_failed(self) -> RuntimeError:
        msg = ("Every available model failed. " + " | ".join(self.skipped)
               + ". Free daily limits reset at 00:00 UTC; or add a Gemini key / start Ollama as a backup.")
        return (QuotaExceeded if self._quota_hit else RuntimeError)(msg)


def get_chat_client(role: str = "answer") -> BaseLLMClient:
    """The configured model first, then every other free option that is set up: the other OpenRouter models, a Gemini key,
    a local Ollama model. Used by chat and on-demand scoring only; benchmark runs stay on one fixed model."""
    primary = get_llm_client(role)
    if primary.is_mock:
        return primary
    chain: List[BaseLLMClient] = [primary]
    if isinstance(primary, OpenRouterLLMClient):
        others = dict.fromkeys([settings.OPENROUTER_MODEL, settings.OPENROUTER_JUDGE_MODEL, "openrouter/free"])
        chain += [OpenRouterLLMClient(settings.OPENROUTER_API_KEY, m, settings.OPENROUTER_BASE_URL) for m in others if m != primary.model_name]
    if not isinstance(primary, GeminiLLMClient) and _has_key(settings.GEMINI_API_KEY):
        chain.append(GeminiLLMClient(api_key=settings.GEMINI_API_KEY, model_name=settings.GEMINI_MODEL))
    if not isinstance(primary, OllamaLLMClient):
        ollama = OllamaLLMClient(base_url=settings.OLLAMA_BASE_URL, model_name=settings.OLLAMA_MODEL)
        if ollama.available():
            chain.append(ollama)
    return FallbackLLMClient(chain) if len(chain) > 1 else primary


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
