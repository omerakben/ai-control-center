from pathlib import Path

from .base import ScanContext, ProviderRoot, make_item, empty_inventory, empty_docs
from ..ids import rel_posix
from ..redaction import redact_text
from ..markdown import render_markdown_safe
from ..frontmatter import parse_frontmatter
from ..config import load_json, safe_mcp, mcp_summary, as_dict
from .generic import _first_heading, _first_paragraph


def _title(fields: dict, fallback: str) -> str:
    name = fields.get("name")
    return name if isinstance(name, str) and name else fallback


def _desc(fields: dict) -> str:
    d = fields.get("description", "")
    return redact_text(d)[0] if isinstance(d, str) else ""


def _classify(rel: str) -> str | None:
    """Map a repo-relative path to its Claude inventory/doc kind, or None.

    Classification happens here, before any file is read, so the scan's full
    file list (which can span the whole repo) only incurs I/O for the files we
    actually index. Keeping the path patterns in one place also stops the
    dispatch in normalize() from drifting out of sync with the read filter.
    """
    if rel.startswith(".claude/agents/") and rel.endswith(".md"):
        return "agent"
    if rel.startswith(".claude/commands/") and rel.endswith(".md"):
        return "command"
    if rel.startswith(".claude/skills/") and rel.endswith("/SKILL.md"):
        return "skill"
    if rel == "CLAUDE.md" or (rel.startswith(".claude/") and rel.endswith("/CLAUDE.md")):
        return "doc"
    return None


class ClaudeAdapter:
    id = "claude"
    display_name = "Claude Code"

    def detect(self, ctx: ScanContext) -> list[ProviderRoot]:
        root = ctx.root
        if (root / ".claude").is_dir() or (root / "CLAUDE.md").is_file():
            base = root / ".claude" if (root / ".claude").is_dir() else root
            return [ProviderRoot(provider="claude", path=base)]
        return []

    def normalize(self, ctx: ScanContext, root: ProviderRoot) -> dict:
        inv = empty_inventory()
        docs = empty_docs()

        for p in ctx.files:
            rel = rel_posix(p, ctx.root)
            kind = _classify(rel)
            if kind is None:
                continue  # filter on path first; most scanned files match nothing
            try:
                raw = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            stem = p.stem

            if kind == "agent":
                fields, _ = parse_frontmatter(raw)
                inv["agents"].append(make_item(
                    "claude", "agent", "Claude agent",
                    _title(fields, stem), rel, _desc(fields)))
            elif kind == "command":
                fields, _ = parse_frontmatter(raw)
                inv["commands"].append(make_item(
                    "claude", "command", "Claude command",
                    _title(fields, stem), rel, _desc(fields)))
            elif kind == "skill":
                fields, _ = parse_frontmatter(raw)
                name = _title(fields, Path(rel).parent.name)
                inv["skills"].append(make_item(
                    "claude", "skill", "Claude skill", name, rel, _desc(fields)))
            else:  # "doc" — CLAUDE.md at root or nested under .claude/
                clean, _ = redact_text(raw)
                heading = _first_heading(clean) or rel
                docs["references"].append({
                    "id": make_item("claude", "doc", "Claude instructions", heading, rel, "")["id"],
                    "title": heading,
                    "path": rel,
                    "summary": _first_paragraph(clean),
                    "html": render_markdown_safe(clean),
                    "_refScanBody": clean,
                })

        inv["hooks"].extend(self._hooks(ctx.root))
        inv["mcpServers"].extend(self._mcp(ctx.root))

        return {
            "provider": {"id": self.id, "displayName": self.display_name,
                         "root": rel_posix(root.path, ctx.root) if root.path != ctx.root else ".",
                         "detected": True},
            "inventory": inv,
            "docs": docs,
        }

    # Reuses generic's prose helpers (_first_heading/_first_paragraph) to derive
    # the heading/summary for CLAUDE.md. No import cycle: generic imports only
    # base/ids/redaction/markdown, none of which import this adapter.
    def _hooks(self, root: Path) -> list[dict]:
        settings = load_json(root / ".claude" / "settings.json")
        out: list[dict] = []
        # Guard every level: hooks may be a non-dict, an event may map to a
        # non-list, and an entry or inner hook may be a non-dict. A hand-edited
        # settings.json should degrade to no hooks, never crash the pipeline.
        for event, entries in as_dict(settings.get("hooks")).items():
            for entry in entries if isinstance(entries, list) else []:
                if not isinstance(entry, dict):
                    continue
                matcher = entry.get("matcher", "")
                inner = entry.get("hooks", [])
                for h in inner if isinstance(inner, list) else []:
                    if not isinstance(h, dict):
                        continue
                    cmd = redact_text(str(h.get("command", "")))[0]
                    title = f"{event} ({matcher})" if matcher else event
                    out.append(make_item(
                        "claude", "hook", "Claude hook", title,
                        ".claude/settings.json", cmd))
        return out

    def _mcp(self, root: Path) -> list[dict]:
        merged: dict[str, tuple[str, dict]] = {}
        # settings.json first, then .mcp.json overrides on name conflict
        for rel in (".claude/settings.json", ".mcp.json"):
            path = root / rel
            servers = as_dict(load_json(path).get("mcpServers"))
            for name, cfg in servers.items():
                merged[name] = (rel, cfg if isinstance(cfg, dict) else {})
        out: list[dict] = []
        for name, (rel, cfg) in merged.items():
            clean = safe_mcp(cfg)
            item = make_item("claude", "mcpServer", "MCP server", name, rel,
                             mcp_summary(clean))
            item["config"] = clean
            out.append(item)
        return out
