import re
from .base import ScanContext, ProviderRoot
from ..ids import stable_id, rel_posix
from ..redaction import redact_text
from ..markdown import render_markdown_safe

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
            clean, _ = redact_text(raw)
            heading = _first_heading(clean) or rel
            docs.append({
                "id": stable_id("generic", "doc", rel, heading),
                "title": heading,
                "path": rel,
                "summary": _first_paragraph(clean),
                "html": render_markdown_safe(clean),
            })
            for line in clean.splitlines():
                m = _TODO.match(line)
                if m:
                    todos.append({"text": m.group(1).strip(), "path": rel})
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
