import hashlib

DEFAULT_PROMPT_NAME = "Default (strict, grounded)"

DEFAULT_SYSTEM_PROMPT = (
    "You are EvalGuard AI Assistant. Answer the question strictly using only the provided context. "
    "If the information is not present in the context, state that clearly. Do not fabricate facts."
)


def prompt_hash(text: str) -> str:
    """Short stable fingerprint so runs can tell prompt versions apart even if a name is reused."""
    return hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:10]
