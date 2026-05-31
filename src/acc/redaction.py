import re

REDACTED = "[redacted]"

# A credential keyword that may be glued into a compound identifier
# (AWS_SECRET_ACCESS_KEY, GITHUB_TOKEN, OPENAI_API_KEY). The old leading \b
# failed on these: "_" is a word char, so there was no boundary between a
# descriptive prefix and the glued keyword, and every UPPER_SNAKE credential
# name leaked. Separator-joined segments before/after the keyword fix that,
# while the trailing [:=] requirement keeps "tokenizer"/"secretary" (keyword
# followed by letters, not a separator or assignment) from matching.
_KEYWORD = (
    r"(?:[A-Za-z0-9]+[_-])*"
    r"(?:api[_-]?key|secret|access[_-]?token|token|password|passwd|pwd|client[_-]?secret)"
    r"(?:[_-][A-Za-z0-9]+)*"
)

# Format-based hard secrets, detected with no keyword context. These give the
# validation tripwire a detection path independent of the keyword heuristic, so
# a structural blind spot in keyword matching cannot silently pass a leak.
_HARD_FORMATS = [
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                                # AWS access key id
    re.compile(r"-----BEGIN (?:[A-Z][A-Z ]* )?PRIVATE KEY-----"),       # PEM private key
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{6,}"),  # JWT
]

def _keyword_assignment(value_chars: str) -> "re.Pattern[str]":
    """`keyword = value` matcher with a configurable value character class.

    The optional quote after the keyword catches the JSON / config form
    "PGPASSWORD": "value" (a quoted key whose closing quote would otherwise block
    the [:=]). The value group captures an optional opening quote and redacts a
    matching closing quote (\\1?) — a closed value leaves no dangling quote, an
    unclosed value is still redacted.
    """
    return re.compile(r"(?i)" + _KEYWORD + r"[\"']?\s*[:=]\s*([\"']?)" + value_chars + r"{6,}\1?")


# Patterns shared by extraction-time redaction and the output tripwire. Their
# alphabets already exclude HTML structural chars, so rendering does not perturb
# them the way it does the keyword=value heuristic.
_COMMON_PATTERNS = [
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
    # provider-prefixed keys, including multi-segment forms (sk-proj-…, sk_live_…,
    # xoxb-…-…): allow internal -/_ separators, >=10 body chars, no trailing-
    # separator over-match.
    re.compile(
        r"\b(?:sk|pk|gho|ghp|ghs|xox[baprs])[-_]"
        r"(?=[A-Za-z0-9_-]{10,}\b)[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)*\b(?![-_])"
    ),
    re.compile(r"(?i)\b[a-z][a-z0-9+.\-]*://[^/\s:@]+:[^/\s:@]+@\S+"),
    *_HARD_FORMATS,
]

# redact_text runs on RAW markdown: the value class stays maximally greedy so a
# real password containing `&` or `<` is redacted at extraction (full recall).
_SECRET_PATTERNS = [_keyword_assignment(r"[^\s\"']"), *_COMMON_PATTERNS]

# find_secrets runs on the ASSEMBLED output, which includes rendered html. There
# the value stops at the HTML structural chars `<` and `&`, so markup (`</code>`)
# and escaped specials (`&lt;`) can neither inflate a short placeholder past the
# 6-char floor nor bridge a bare `KEYWORD=` to a following prose word — the false
# blocks a real repo's docs (`export XAI_API_KEY=...`, a `PASSWORD=` shape) would
# otherwise hit. Real secrets rarely contain `<`/`&`, and raw redaction (full
# recall, above) is the primary defense; this is the backstop for a field that
# skipped it.
_TRIPWIRE_PATTERNS = [_keyword_assignment(r"[^\s\"'<&]"), *_COMMON_PATTERNS]


def redact_text(text: str) -> tuple[str, int]:
    n = 0
    for pat in _SECRET_PATTERNS:
        text, count = pat.subn(REDACTED, text)
        n += count
    return text, n


def find_secrets(text: str) -> int:
    """Count secret-shaped substrings without mutating the text.

    The validation tripwire over the assembled output. Uses the rendered-safe
    keyword pattern (value stops at `<`/`&`) so HTML markup neither creates nor
    masks a match; the provider/format patterns are shared with redact_text.
    """
    return sum(len(pat.findall(text)) for pat in _TRIPWIRE_PATTERNS)


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
        # redact KEYS too: a nested config key can itself be secret-shaped
        # (e.g. an env/arg map keyed by a credential string).
        return {(redact_text(k)[0] if isinstance(k, str) else k): _redact_value(v)
                for k, v in value.items()}
    return value
