import json

from .redaction import redact_text

SCHEMA_VERSION = "1.0"

_REQUIRED_TOP = {
    "schemaVersion", "generator", "source", "providers",
    "project", "inventory", "docs", "relationships", "search",
}


def canonical_json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def assert_no_secrets(data: dict) -> None:
    """Final tripwire: re-scan the serialized output for surviving secrets.

    Everything reaching `data` is already redacted at extraction. A match here
    means an adapter skipped redaction on a structured-config value — fail loud
    rather than ship a leak.
    """
    _, n = redact_text(canonical_json(data))
    if n:
        raise ValueError(f"redaction tripwire: {n} secret-shaped value(s) survived into output")


def validate(data: dict) -> None:
    missing = _REQUIRED_TOP - data.keys()
    if missing:
        raise ValueError(f"missing required keys: {sorted(missing)}")
    if data["schemaVersion"] != SCHEMA_VERSION:
        raise ValueError(f"unexpected schemaVersion: {data['schemaVersion']!r}")
    assert_no_secrets(data)
