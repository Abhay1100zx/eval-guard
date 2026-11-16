import json
import re
from typing import Tuple


def parse_judge_json(raw: str) -> Tuple[float, str]:
    """Extract (score, reasoning) from an LLM judge reply.

    Tolerates ```json fences, <think> blocks, prose around the object and nested braces.
    Raises ValueError if no score can be recovered.
    """
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            return float(obj["score"]), str(obj.get("reasoning", ""))
        except (ValueError, KeyError, TypeError):
            pass
    m = re.search(r'"?score"?\s*[:=]\s*([0-9]*\.?[0-9]+)', text, re.IGNORECASE)
    if m:
        return float(m.group(1)), text.strip()[:300]
    raise ValueError(f"No score in judge output: {raw[:120]!r}")
