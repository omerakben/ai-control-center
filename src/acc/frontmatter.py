import re

_KEY = re.compile(r"([A-Za-z0-9_-]+):\s*(.*)$")
_BLOCK_ITEM = re.compile(r"\s*-\s+(.*)$")


def _scalar(s: str):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    if s == "true":
        return True
    if s == "false":
        return False
    return s


def _parse_block(lines: list[str]) -> dict:
    fields: dict = {}
    key: str | None = None
    for line in lines:
        if not line.strip():
            continue
        item = _BLOCK_ITEM.match(line)
        if item and key is not None and isinstance(fields.get(key), list):
            fields[key].append(_scalar(item.group(1)))
            continue
        m = _KEY.match(line)
        if not m:
            # unparseable line — skip, never raise
            continue
        key = m.group(1)
        val = m.group(2).strip()
        if val == "":
            fields[key] = []          # may be filled by a following block list
        elif val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fields[key] = [_scalar(x) for x in inner.split(",")] if inner else []
        else:
            fields[key] = _scalar(val)
    return fields


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse a leading --- fenced frontmatter block. Returns (fields, body).

    Handles the shallow YAML subset real Claude/Cursor artifacts use:
    key: value, quoted strings, inline [a, b] and block (- item) lists, booleans.
    No nested maps. Unparseable lines are skipped. No fence -> ({}, text).
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    return _parse_block(lines[1:end]), "\n".join(lines[end + 1:])
