from pathlib import Path

from .base import ScanContext, ProviderRoot, make_item, empty_inventory, empty_docs
from ..ids import rel_posix
from ..redaction import redact_text
from ..markdown import render_markdown_safe
from ..config import load_toml, safe_mcp, as_dict
from .generic import _first_heading, _first_paragraph

_CONFIG_FACTS = ("model", "model_reasoning_effort", "sandbox", "approval_policy")


class CodexAdapter:
    id = "codex"
    display_name = "Codex"

    def detect(self, ctx: ScanContext) -> list[ProviderRoot]:
        root = ctx.root
        if (root / ".codex").is_dir() or (root / "AGENTS.md").is_file():
            base = root / ".codex" if (root / ".codex").is_dir() else root
            return [ProviderRoot(provider="codex", path=base)]
        return []

    def normalize(self, ctx: ScanContext, root: ProviderRoot) -> dict:
        inv = empty_inventory()
        docs = empty_docs()
        toml = load_toml(ctx.root / ".codex" / "config.toml")

        # as_dict guards the `[[mcp_servers]]` array-of-tables typo, which
        # tomllib parses to a list — iterating it directly would crash.
        for name, cfg in as_dict(toml.get("mcp_servers")).items():
            clean = safe_mcp(cfg if isinstance(cfg, dict) else {})
            item = make_item("codex", "mcpServer", "MCP server", name,
                             ".codex/config.toml", clean.get("command") or clean.get("url") or "")
            item["config"] = clean
            inv["mcpServers"].append(item)

        for p in ctx.files:
            rel = rel_posix(p, ctx.root)
            if rel.startswith(".codex/prompts/") and rel.endswith(".md"):
                try:
                    raw = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                clean, _ = redact_text(raw)
                # prompts are invoked by filename, so the stem is the title
                inv["commands"].append(make_item(
                    "codex", "command", "Codex prompt", p.stem, rel,
                    _first_paragraph(clean)))
            elif rel == "AGENTS.md" or (rel.startswith(".codex/") and rel.endswith("/AGENTS.md")):
                try:
                    raw = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                clean, _ = redact_text(raw)
                heading = _first_heading(clean) or rel
                docs["references"].append({
                    "id": make_item("codex", "doc", "Codex instructions", heading, rel, "")["id"],
                    "title": heading,
                    "path": rel,
                    "summary": _first_paragraph(clean),
                    "html": render_markdown_safe(clean),
                })

        facts = {k: redact_text(str(toml[k]))[0] for k in _CONFIG_FACTS if k in toml}
        return {
            "provider": {"id": self.id, "displayName": self.display_name,
                         "root": rel_posix(root.path, ctx.root) if root.path != ctx.root else ".",
                         "detected": True, "config": facts},
            "inventory": inv,
            "docs": docs,
        }
