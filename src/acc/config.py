import json
import tomllib
from pathlib import Path

from .redaction import allowlist_config

# MCP server config keys that are safe to surface. `type` is the transport
# (stdio/http/sse); `url` is redacted for embedded credentials. Everything
# else (env, headers, tokens, ...) is dropped — this tier fails closed.
MCP_ALLOWED = {"command", "args", "type", "url"}


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load_toml(path: Path) -> dict:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def as_dict(value) -> dict:
    """Coerce a parsed-config value to a dict before iterating it.

    `load_json`/`load_toml` guard only the document root, and the `... or {}`
    idiom guards only None/empty — a well-formed-but-wrong-shape value (a list,
    string, or a TOML `[[mcp_servers]]` array-of-tables) is truthy and would
    crash `.items()`. Per the design's no-crash contract, treat it as empty.
    """
    return value if isinstance(value, dict) else {}


def safe_mcp(server: dict) -> dict:
    """Allowlist a single MCP server config, redacting surviving values."""
    return allowlist_config(server, MCP_ALLOWED)
