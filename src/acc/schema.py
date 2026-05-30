import json

from .redaction import find_secrets

SCHEMA_VERSION = "1.0"

_REQUIRED_TOP = {
    "schemaVersion", "generator", "source", "providers",
    "project", "inventory", "docs", "relationships", "search",
}


def canonical_json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _scan_strings(obj) -> int:
    """Count secret-shaped substrings across every string leaf of the data.

    Walks the structure rather than the JSON text so quote-bearing values are
    scanned in their real form — `json.dumps` escapes embedded quotes to `\\"`,
    which would otherwise hide a `KEY = "value"` secret from the matcher.
    """
    if isinstance(obj, str):
        return find_secrets(obj)
    if isinstance(obj, dict):
        return sum(_scan_strings(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(_scan_strings(v) for v in obj)
    return 0


def assert_no_secrets(data: dict) -> None:
    """Final tripwire: re-scan the assembled output for surviving secrets.

    Everything reaching `data` is already redacted at extraction. A match here
    means an adapter skipped redaction on a structured-config value — fail loud
    rather than ship a leak.
    """
    n = _scan_strings(data)
    if n:
        raise ValueError(f"redaction tripwire: {n} secret-shaped value(s) survived into output")


def validate(data: dict) -> None:
    missing = _REQUIRED_TOP - data.keys()
    if missing:
        raise ValueError(f"missing required keys: {sorted(missing)}")
    if data["schemaVersion"] != SCHEMA_VERSION:
        raise ValueError(f"unexpected schemaVersion: {data['schemaVersion']!r}")
    assert_no_secrets(data)
