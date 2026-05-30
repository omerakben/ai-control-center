from pathlib import Path

from .base import ScanContext, ProviderRoot, make_item, empty_inventory, empty_docs
from ..ids import rel_posix
from ..redaction import redact_text
from ..markdown import render_markdown_safe
from ..frontmatter import parse_frontmatter
from ..config import load_json, safe_mcp
from .generic import _first_heading, _first_paragraph


def _title(fields: dict, fallback: str) -> str:
    name = fields.get("name")
    return name if isinstance(name, str) and name else fallback


def _desc(fields: dict) -> str:
    d = fields.get("description", "")
    return redact_text(d)[0] if isinstance(d, str) else ""


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
            try:
                raw = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            stem = p.stem

            if rel.startswith(".claude/agents/") and rel.endswith(".md"):
                fields, _ = parse_frontmatter(raw)
                inv["agents"].append(make_item(
                    "claude", "agent", "Claude agent",
                    _title(fields, stem), rel, _desc(fields)))
            elif rel.startswith(".claude/commands/") and rel.endswith(".md"):
                fields, _ = parse_frontmatter(raw)
                inv["commands"].append(make_item(
                    "claude", "command", "Claude command",
                    _title(fields, stem), rel, _desc(fields)))
            elif rel.startswith(".claude/skills/") and rel.endswith("/SKILL.md"):
                fields, _ = parse_frontmatter(raw)
                name = _title(fields, Path(rel).parent.name)
                inv["skills"].append(make_item(
                    "claude", "skill", "Claude skill", name, rel, _desc(fields)))
            elif rel == "CLAUDE.md" or (rel.startswith(".claude/") and rel.endswith("/CLAUDE.md")):
                clean, _ = redact_text(raw)
                heading = _first_heading(clean) or rel
                docs["references"].append({
                    "id": make_item("claude", "doc", "Claude instructions", heading, rel, "")["id"],
                    "title": heading,
                    "path": rel,
                    "summary": _first_paragraph(clean),
                    "html": render_markdown_safe(clean),
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
        for event, entries in (settings.get("hooks") or {}).items():
            for entry in entries if isinstance(entries, list) else []:
                matcher = entry.get("matcher", "")
                for h in entry.get("hooks", []):
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
            servers = load_json(path).get("mcpServers") or {}
            for name, cfg in servers.items():
                merged[name] = (rel, cfg if isinstance(cfg, dict) else {})
        out: list[dict] = []
        for name, (rel, cfg) in merged.items():
            clean = safe_mcp(cfg)
            summary = clean.get("command") or clean.get("url") or ""
            item = make_item("claude", "mcpServer", "MCP server", name, rel, summary)
            item["config"] = clean
            out.append(item)
        return out
