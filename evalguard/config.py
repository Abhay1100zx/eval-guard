import os
from pathlib import Path
from dataclasses import dataclass

# Load environment variables manually or via dotenv if available
def load_env_file(env_path: Path = None):
    if env_path is None:
        # Search current working dir or evalguard-ai root
        candidates = [
            Path.cwd() / ".env",
            Path(__file__).resolve().parent.parent / ".env"
        ]
        for c in candidates:
            if c.exists():
                env_path = c
                break

    if env_path and env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=env_path)
        except ImportError:
            # Fallback manual parser for .env
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip())

load_env_file()

# Optimize offline sentence-transformers & huggingface caching
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

BASE_DIR = Path(__file__).resolve().parent.parent

def _resolve_config_path(env_var: str, default_rel_path: str) -> str:
    raw_val = os.getenv(env_var, default_rel_path)
    p = Path(raw_val)
    if p.is_absolute():
        return str(p)
    return str((BASE_DIR / p).resolve())

@dataclass
class Settings:
    # LLM Settings
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini").lower()
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "baidu/ernie-5.5-flash-preview:free")
    # Judge differs from the answering model so the system doesn't grade its own output
    OPENROUTER_JUDGE_MODEL: str = os.getenv("OPENROUTER_JUDGE_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
    # Ollama reserves memory for its whole context window; a RAG prompt needs ~1,200 tokens, and the default (4096+) fails on small machines
    OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "2048"))

    # Scheduled runs: every SCHEDULE_HOURS the domain with the oldest real score is evaluated on a small sample (0 = off).
    # Free models allow ~50 calls a day and one question costs 3 calls, so keep the sample small.
    SCHEDULE_HOURS: float = float(os.getenv("EVALGUARD_SCHEDULE_HOURS", "0") or 0)
    SCHEDULE_QUESTIONS: int = int(os.getenv("EVALGUARD_SCHEDULE_QUESTIONS", "6") or 6)

    # Drift alerts (all optional). A Slack/Discord-style webhook and/or email.
    WEB_URL: str = os.getenv("EVALGUARD_WEB_URL", "").rstrip("/")  # makes alerts link to the run page
    ALERT_WEBHOOK_URL: str = os.getenv("ALERT_WEBHOOK_URL", "")
    ALERT_SMTP_HOST: str = os.getenv("ALERT_SMTP_HOST", "")
    ALERT_SMTP_PORT: int = int(os.getenv("ALERT_SMTP_PORT", "587") or 587)
    ALERT_SMTP_USER: str = os.getenv("ALERT_SMTP_USER", "")
    ALERT_SMTP_PASSWORD: str = os.getenv("ALERT_SMTP_PASSWORD", "")
    ALERT_EMAIL_FROM: str = os.getenv("ALERT_EMAIL_FROM", "")
    ALERT_EMAIL_TO: str = os.getenv("ALERT_EMAIL_TO", "")

    # Embeddings & ChromaDB (strictly resolved to BASE_DIR regardless of CWD)
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    CHROMA_PERSIST_DIR: str = _resolve_config_path("CHROMA_PERSIST_DIR", "data/chroma_db")
    SQLITE_DB_PATH: str = _resolve_config_path("SQLITE_DB_PATH", "evalguard.db")

    # Evaluation & Retrieval Thresholds
    FAITHFULNESS_THRESHOLD: float = float(os.getenv("FAITHFULNESS_THRESHOLD", "0.70"))
    RELEVANCE_THRESHOLD: float = float(os.getenv("RELEVANCE_THRESHOLD", "0.70"))
    DRIFT_P_VALUE_THRESHOLD: float = float(os.getenv("DRIFT_P_VALUE_THRESHOLD", "0.05"))
    RETRIEVAL_TOP_K: int = int(os.getenv("RETRIEVAL_TOP_K", "3"))

    # Ingestion
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))

    # API: comma-separated browser origins allowed to call it (the Next.js app)
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")

    # Directories
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"

settings = Settings()


def utcnow_iso() -> str:
    """Naive-UTC ISO timestamp (keeps string ordering consistent with existing rows)."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


# Clerk keys live in the Next.js app's env file; reuse it so the publishable key has one source of truth.
def _load_clerk_env():
    p = BASE_DIR / "web" / ".env.local"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        k, _, v = line.partition("=")
        if k.strip() == "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY" and v.strip():
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_clerk_env()
