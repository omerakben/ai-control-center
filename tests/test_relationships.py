from acc.adapters.base import ScanContext
from acc.adapters.claude import ClaudeAdapter
from acc.adapters.codex import CodexAdapter
from acc.adapters.generic import GenericAdapter
from tests.builders import make_brownfield_repo, make_claude_repo, make_codex_repo


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
