import json

from .ids import stable_id
from .redaction import find_secrets

SCHEMA_VERSION = "1.0"

_REQUIRED_TOP = {
    "schemaVersion", "generator", "source", "providers",
    "project", "inventory", "docs", "relationships", "search",
}

_SEARCH_KEYS = ("id", "type", "typeLabel", "title", "path", "text")
_KNOWN_SEARCH_TYPES = {
    "agent", "skill", "hook", "command", "mcpServer", "rule", "doc", "todo",
}


def _validate_search(records: list) -> None:
    if not isinstance(records, list):
        raise ValueError("search must be a list")
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            raise ValueError(f"search[{i}] is not an object")
        for key in _SEARCH_KEYS:
            if key not in rec:
                raise ValueError(f"search[{i}] missing key: {key!r}")
            if not isinstance(rec[key], str):
                raise ValueError(f"search[{i}].{key} must be a string")
        if rec["type"] not in _KNOWN_SEARCH_TYPES:
            raise ValueError(f"search[{i}] unknown type: {rec['type']!r}")


_REL_TYPES = {"reference", "declares"}
_REL_KEYS = ("from", "to", "type", "evidence")


def _validate_relationships(edges, item_ids: set, doc_ids: set, config_node_ids: set) -> None:
    if not isinstance(edges, list):
        raise ValueError("relationships must be a list")
    for i, e in enumerate(edges):
        if not isinstance(e, dict):
            raise ValueError(f"relationships[{i}] is not an object")
        for key in _REL_KEYS:
            if key not in e:
                raise ValueError(f"relationships[{i}] missing key: {key!r}")
            if not isinstance(e[key], str):
                raise ValueError(f"relationships[{i}].{key} must be a string")
        if e["type"] not in _REL_TYPES:
            raise ValueError(f"relationships[{i}] unknown type: {e['type']!r}")
        if e["to"] not in item_ids:
            raise ValueError(f"relationships[{i}] dangling 'to': {e['to']!r}")
        if e["type"] == "reference" and e["from"] not in doc_ids:
            raise ValueError(f"relationships[{i}] reference 'from' not a doc: {e['from']!r}")
        if e["type"] == "declares" and e["from"] not in config_node_ids:
            raise ValueError(f"relationships[{i}] declares 'from' not a config node: {e['from']!r}")


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
    _validate_search(data["search"])
    inv = data["inventory"]
    item_ids = {it["id"] for items in inv.values() for it in items}
    doc_ids = {d["id"] for bucket in data["docs"].values() for d in bucket}
    config_node_ids = {
        stable_id("config", "configFile", it["path"], "")
        for kind in ("mcpServers", "hooks") for it in inv.get(kind, [])
    }
    _validate_relationships(data["relationships"], item_ids, doc_ids, config_node_ids)
    assert_no_secrets(data)
