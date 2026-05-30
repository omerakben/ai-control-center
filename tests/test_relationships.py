from acc.adapters.base import ScanContext
from acc.adapters.claude import ClaudeAdapter
from acc.adapters.codex import CodexAdapter
from acc.adapters.generic import GenericAdapter
from acc.generate import _build_relationships
from acc.adapters.base import make_item, empty_inventory, empty_docs
from tests.builders import make_brownfield_repo, make_claude_repo, make_codex_repo


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
