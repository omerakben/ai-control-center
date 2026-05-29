import re

REDACTED = "[redacted]"

_SECRET_PATTERNS = [
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|secret|access[_-]?token|token|password|passwd|pwd|client[_-]?secret)\b"
        r"\s*[:=]\s*[\"']?[^\s\"']{6,}"
    ),
    re.compile(r"\b(?:sk|pk|gho|ghp|ghs|xox[baprs])[-_][A-Za-z0-9]{10,}"),
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
