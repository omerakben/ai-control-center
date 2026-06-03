import re
from pathlib import Path
from .base import ScanContext, ProviderRoot, extract_metadata
from ..ids import stable_id, rel_posix
from ..redaction import redact_text
from ..frontmatter import parse_frontmatter

_TODO = re.compile(r"^\s*[-*+]\s*\[ \]\s*(.+)$")
_HEADING = re.compile(r"^\s*#{1,6}\s+(.*)$")
_FENCE = re.compile(r"^\s*```")
# markdown block markers that are not prose (heading, list/task, quote, numbered)
_BLOCK_MARKER = re.compile(r"^\s*(?:#{1,6}\s|[-*+]\s|>|\d+[.)]\s)")


def _strip_front_matter(text: str) -> str:
    lines = text.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].strip() in ("---", "+++"):
        fence = lines[i].strip()
        for j in range(i + 1, len(lines)):
            if lines[j].strip() == fence:
                return "\n".join(lines[j + 1:])
    return text


def _content_lines(text: str):
    """Yield prose-candidate lines: front matter stripped, fenced code skipped."""
    in_code = False
    for line in _strip_front_matter(text).splitlines():
        if _FENCE.match(line):
            in_code = not in_code
            continue
        if not in_code:
            yield line


def _first_heading(text: str) -> str:
    for line in _content_lines(text):
        m = _HEADING.match(line)
        if m:
            return m.group(1).strip()
    return ""


def _first_paragraph(text: str) -> str:
    for line in _content_lines(text):
        s = line.strip()
        if s and not _BLOCK_MARKER.match(line):
            return s
    return ""


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _lead_sentence(text: str, cap: int = 200) -> str:
    """First sentence of `text`, whitespace-collapsed and length-capped.

    Real Claude agent/skill `description`s are multi-sentence and carry whole
    <example> blocks, which makes a wall of a one-line summary. Take the lead
    sentence so the row stays glanceable; the full body is in the reading pane.
    Collapsing whitespace also tidies any newline a decoded description carries.
    """
    text = " ".join(text.split())
    if not text:
        return ""
    lead = _SENTENCE_END.split(text, 1)[0]
    if len(lead) > cap:
        lead = lead[:cap].rsplit(" ", 1)[0].rstrip() + "…"
    return lead


def _extract_todos(text: str, rel: str) -> list[dict]:
    """Open-checkbox (`- [ ]`) lines from already-redacted markdown.

    Each TODO carries a stable_id so the omnibox can jump to its rendered row,
    plus its source line so copied diffs can point at the real location.
    """
    out: list[dict] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        m = _TODO.match(line)
        if m:
            todo_text = m.group(1).strip()
            out.append({"id": stable_id("generic", "todo", rel, todo_text),
                        "text": todo_text, "path": rel, "rawLine": line,
                        "lineNumber": line_number})
    return out


def harvest_todos(files: list[Path], root: Path) -> list[dict]:
    """Open TODOs from markdown that GenericAdapter does not index itself.

    Provider docs (CLAUDE.md, AGENTS.md, .claude/**, ...) are filtered out of
    generic doc indexing, but the open TODOs inside them still belong to the
    project. Pull them out here so the filter does not silently drop them.
    Redaction is applied before extraction, exactly as the adapter does.
    """
    todos: list[dict] = []
    for p in files:
        if p.suffix.lower() != ".md":
            continue
        rel = rel_posix(p, root)
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        clean, _ = redact_text(raw)
        todos.extend(_extract_todos(clean, rel))
    return todos


class GenericAdapter:
    id = "generic"
    display_name = "Generic"

    def detect(self, ctx: ScanContext) -> list[ProviderRoot]:
        return [ProviderRoot(provider="generic", path=ctx.root)]

    def normalize(self, ctx: ScanContext, root: ProviderRoot) -> dict:
        docs: list[dict] = []
        todos: list[dict] = []
        title = ctx.root.name
        for p in ctx.files:
            if p.suffix.lower() != ".md":
                continue
            rel = rel_posix(p, ctx.root)
            try:
                raw = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            fields, body_text = parse_frontmatter(raw)
            clean, _ = redact_text(body_text)
            heading = _first_heading(clean)
            if not heading:
                heading = fields.get("title") or fields.get("name") or rel
            summary = _first_paragraph(clean)
            if not summary:
                # Use description/summary if paragraph is empty
                summary = fields.get("description") or fields.get("summary") or ""
            doc_item = {
                "id": stable_id("generic", "doc", rel, heading),
                "title": heading,
                "path": rel,
                "summary": summary,
                "_refScanBody": clean,
            }
            meta = extract_metadata(fields)
            if meta:
                doc_item["metadata"] = meta
            docs.append(doc_item)
            todos.extend(_extract_todos(clean, rel))
            if rel.lower() == "readme.md" and heading:
                title = heading
        docs.sort(key=lambda d: d["path"])
        todos.sort(key=lambda t: (t["path"], t["text"]))
        return {
            "project": {"title": title, "openTodos": todos, "recentDocs": [], "warnings": []},
            "docs": {"references": docs, "prds": [], "adrs": [], "decisions": [], "workflows": []},
            "inventory": {"agents": [], "skills": [], "hooks": [], "commands": [], "mcpServers": [], "rules": []},
            "relationships": [],
        }
