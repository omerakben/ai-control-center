from .base import ScanContext, ProviderRoot, make_item, empty_inventory, empty_docs
from ..ids import rel_posix
from ..redaction import redact_text
from ..frontmatter import parse_frontmatter
from ..config import load_json, safe_mcp, mcp_summary, as_dict


class CursorAdapter:
    id = "cursor"
    display_name = "Cursor"

    def detect(self, ctx: ScanContext) -> list[ProviderRoot]:
        root = ctx.root
        if (root / ".cursor").is_dir() or (root / ".cursorrules").is_file():
            base = root / ".cursor" if (root / ".cursor").is_dir() else root
            return [ProviderRoot(provider="cursor", path=base)]
        return []

    def normalize(self, ctx: ScanContext, root: ProviderRoot) -> dict:
        inv = empty_inventory()
        docs = empty_docs()

        for p in ctx.files:
            rel = rel_posix(p, ctx.root)
            if rel.startswith(".cursor/rules/") and rel.endswith(".mdc"):
                try:
                    raw = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                fields, _ = parse_frontmatter(raw)
                desc = fields.get("description", "")
                summary = redact_text(desc)[0] if isinstance(desc, str) else ""
                inv["rules"].append(make_item(
                    "cursor", "rule", "Cursor rule", p.stem, rel, summary))
            elif rel == ".cursorrules":
                inv["rules"].append(make_item(
                    "cursor", "rule", "Cursor rule", ".cursorrules", rel,
                    "Legacy single-file Cursor rules"))

        servers = as_dict(load_json(ctx.root / ".cursor" / "mcp.json").get("mcpServers"))
        for name, cfg in servers.items():
            clean = safe_mcp(cfg if isinstance(cfg, dict) else {})
            item = make_item("cursor", "mcpServer", "MCP server", name,
                             ".cursor/mcp.json", mcp_summary(clean))
            item["config"] = clean
            inv["mcpServers"].append(item)

        return {
            "provider": {"id": self.id, "displayName": self.display_name,
                         "root": rel_posix(root.path, ctx.root) if root.path != ctx.root else ".",
                         "detected": True},
            "inventory": inv,
            "docs": docs,
        }
