import re

REDACTED = "[redacted]"

_SECRET_PATTERNS = [
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|secret|access[_-]?token|token|password|passwd|pwd|client[_-]?secret)\b"
        # capture an optional opening quote and redact a matching closing quote
        # if present (\1?) — so a closed value leaves no dangling quote, and an
        # UNCLOSED value is still redacted (never matches less than before).
        r"\s*[:=]\s*([\"']?)[^\s\"']{6,}\1?"
    ),
    re.compile(
        # provider-prefixed keys, including multi-segment forms like sk-proj-…,
        # sk_live_…, xoxb-…-…  (allow internal -/_ separators, >=10 body chars,
        # no trailing separator over-match).
        r"\b(?:sk|pk|gho|ghp|ghs|xox[baprs])[-_]"
        r"(?=[A-Za-z0-9_-]{10,}\b)[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*\b(?![-_])"
    ),
    re.compile(r"(?i)\b[a-z][a-z0-9+.\-]*://[^/\s:@]+:[^/\s:@]+@\S+"),
]


def redact_text(text: str) -> tuple[str, int]:
    n = 0
    for pat in _SECRET_PATTERNS:
        text, count = pat.subn(REDACTED, text)
        n += count
    return text, n


def allowlist_config(config: dict, allowed: set[str]) -> dict:
    clean: dict = {}
    for key, value in config.items():
        if key not in allowed:
            continue
        clean[key] = _redact_value(value)
    return clean


def _redact_value(value):
    if isinstance(value, str):
        return redact_text(value)[0]
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    return value
