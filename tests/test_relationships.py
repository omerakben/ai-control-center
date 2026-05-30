import json

from acc.adapters.base import ScanContext
from acc.adapters.claude import ClaudeAdapter
from acc.adapters.codex import CodexAdapter
from acc.adapters.generic import GenericAdapter
from acc.generate import _build_relationships, generate
from acc.adapters.base import make_item, empty_inventory, empty_docs
from acc.ids import stable_id
from tests.builders import (
    make_brownfield_repo, make_claude_repo, make_codex_repo, make_multi_provider_repo)


def _doc(doc_id, path, body):
    return {"id": doc_id, "title": path, "path": path, "summary": "",
            "html": "", "_refScanBody": body}


def _claude_docs(tmp_path):
    make_claude_repo(tmp_path)
    files = [f for f in tmp_path.rglob("*") if f.is_file()]
    ctx = ScanContext(root=tmp_path, files=files)
    adapter = ClaudeAdapter()
    part = adapter.normalize(ctx, adapter.detect(ctx)[0])
    return part["docs"]["references"]


def test_claude_doc_carries_refscanbody(tmp_path):
    docs = _claude_docs(tmp_path)
    claude_md = next(d for d in docs if d["path"] == "CLAUDE.md")
    assert "_refScanBody" in claude_md
    assert "Project memory and rules." in claude_md["_refScanBody"]


def test_codex_and_generic_docs_carry_refscanbody(tmp_path):
    make_codex_repo(tmp_path)
    make_brownfield_repo(tmp_path)
    files = [f for f in tmp_path.rglob("*") if f.is_file()]
    ctx = ScanContext(root=tmp_path, files=files)
    cod = CodexAdapter().normalize(ctx, CodexAdapter().detect(ctx)[0])
    agents = next(d for d in cod["docs"]["references"] if d["path"] == "AGENTS.md")
    assert "Guide." in agents["_refScanBody"]
    gen = GenericAdapter().normalize(ctx, GenericAdapter().detect(ctx)[0])
    assert all("_refScanBody" in d for d in gen["docs"]["references"])


def test_reference_edge_from_doc_body_path_mention():
    agent = make_item("claude", "agent", "Claude agent", "reviewer",
                      ".claude/agents/reviewer.md", "")
    inv = empty_inventory()
    inv["agents"].append(agent)
    docs = empty_docs()
    docs["references"].append(
        _doc("docid", "CLAUDE.md", "See .claude/agents/reviewer.md for review rules."))
    edges = _build_relationships(inv, docs)
    refs = [e for e in edges if e["type"] == "reference"]
    assert refs == [{"from": "docid", "to": agent["id"], "type": "reference",
                     "evidence": ".claude/agents/reviewer.md"}]


def test_reference_dedup_and_boundary_and_unique():
    a1 = make_item("claude", "agent", "Claude agent", "x", ".claude/agents/x.md", "")
    inv = empty_inventory()
    inv["agents"].append(a1)
    docs = empty_docs()
    docs["references"].append(_doc(
        "d", "CLAUDE.md",
        ".claude/agents/x.md and again .claude/agents/x.md but not .claude/agents/x.md.bak"))
    refs = [e for e in _build_relationships(inv, docs) if e["type"] == "reference"]
    assert len(refs) == 1 and refs[0]["to"] == a1["id"]


def test_declares_edges_from_config_file_nodes():
    inv = empty_inventory()
    hook = make_item("claude", "hook", "Claude hook", "PreToolUse (Bash)",
                     ".claude/settings.json", "echo hi")
    mcp1 = make_item("claude", "mcpServer", "MCP server", "local",
                     ".claude/settings.json", "node")
    mcp2 = make_item("cursor", "mcpServer", "MCP server", "figma",
                     ".cursor/mcp.json", "")
    inv["hooks"].append(hook)
    inv["mcpServers"].extend([mcp1, mcp2])
    edges = _build_relationships(inv, empty_docs())
    declares = [e for e in edges if e["type"] == "declares"]
    settings_node = stable_id("config", "configFile", ".claude/settings.json", "")
    cursor_node = stable_id("config", "configFile", ".cursor/mcp.json", "")
    assert {(e["from"], e["to"], e["evidence"]) for e in declares} == {
        (settings_node, hook["id"], ".claude/settings.json"),
        (settings_node, mcp1["id"], ".claude/settings.json"),
        (cursor_node, mcp2["id"], ".cursor/mcp.json"),
    }


def test_declares_excludes_commands():
    inv = empty_inventory()
    inv["commands"].append(make_item("claude", "command", "Claude command",
                                     "ship", ".claude/commands/ship.md", ""))
    declares = [e for e in _build_relationships(inv, empty_docs())
                if e["type"] == "declares"]
    assert declares == []


def _island(html: str) -> dict:
    marker = '<script id="acc-data" type="application/json">'
    start = html.index(marker) + len(marker)
    end = html.index("</script>", start)
    return json.loads(html[start:end])


def test_generate_populates_relationships_and_drops_private_fields(tmp_path):
    make_multi_provider_repo(tmp_path)
    (tmp_path / "docs" / "links.md").write_text(
        "# Links\n\nUses .claude/agents/reviewer.md and the figma server.")
    html = generate(tmp_path).read_text(encoding="utf-8")
    assert "_refScanBody" not in html and "_rawBody" not in html
    data = _island(html)
    assert isinstance(data["relationships"], list) and data["relationships"]
    kinds = {e["type"] for e in data["relationships"]}
    assert kinds <= {"reference", "declares"}
    assert any(e["type"] == "reference" and e["evidence"] == ".claude/agents/reviewer.md"
               for e in data["relationships"])


def test_redaction_drops_keyword_prefixed_path(tmp_path):
    # leak.md is the ONLY mention of reviewer.md, and it sits behind a secret
    # keyword, so redact_text removes the path before the scan -> no edge.
    make_claude_repo(tmp_path)
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "leak.md").write_text(
        "# Leak\n\ntoken: .claude/agents/reviewer.md")
    data = _island(generate(tmp_path).read_text(encoding="utf-8"))
    assert not any(e["type"] == "reference" and e["evidence"] == ".claude/agents/reviewer.md"
                   for e in data["relationships"])


def test_config_path_not_a_reference_target(tmp_path):
    make_codex_repo(tmp_path)  # single mcpServer -> .codex/config.toml is a unique path
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "ref.md").write_text("# Ref\n\nconfigured in .codex/config.toml here")
    data = _island(generate(tmp_path).read_text(encoding="utf-8"))
    assert not any(e["type"] == "reference" and e["evidence"] == ".codex/config.toml"
                   for e in data["relationships"])
    assert any(e["type"] == "declares" and e["evidence"] == ".codex/config.toml"
               for e in data["relationships"])
