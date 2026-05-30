from acc.adapters.base import ScanContext
from acc.adapters.claude import ClaudeAdapter
from acc.scan import scan_files
from tests.builders import make_claude_repo, make_brownfield_repo


def _normalize(tmp_path):
    ctx = ScanContext(root=tmp_path, files=scan_files(tmp_path))
    ad = ClaudeAdapter()
    roots = ad.detect(ctx)
    return ad, roots, ad.normalize(ctx, roots[0]) if roots else None


def test_detects_claude_provider(tmp_path):
    make_claude_repo(tmp_path)
    ad, roots, _ = _normalize(tmp_path)
    assert roots and roots[0].provider == "claude"


def test_does_not_detect_on_brownfield(tmp_path):
    make_brownfield_repo(tmp_path)
    ctx = ScanContext(root=tmp_path, files=scan_files(tmp_path))
    assert ClaudeAdapter().detect(ctx) == []


def test_inventories_agents_commands_skills(tmp_path):
    make_claude_repo(tmp_path)
    _, _, part = _normalize(tmp_path)
    inv = part["inventory"]
    assert [a["title"] for a in inv["agents"]] == ["reviewer"]
    assert inv["agents"][0]["typeLabel"] == "Claude agent"
    assert inv["agents"][0]["summary"] == "Reviews code for bugs"
    assert [c["title"] for c in inv["commands"]] == ["ship"]
    assert [s["title"] for s in inv["skills"]] == ["pdf"]


def test_inventories_hooks_and_mcp(tmp_path):
    make_claude_repo(tmp_path)
    _, _, part = _normalize(tmp_path)
    inv = part["inventory"]
    assert inv["hooks"], "expected a hook from settings.json"
    names = {m["title"] for m in inv["mcpServers"]}
    assert {"postgres", "local"} <= names


def test_mcp_env_secret_is_dropped(tmp_path):
    make_claude_repo(tmp_path)
    _, _, part = _normalize(tmp_path)
    assert "s3cr3tpassword" not in str(part)


def test_surfaces_claude_md_doc(tmp_path):
    make_claude_repo(tmp_path)
    _, _, part = _normalize(tmp_path)
    refs = part["docs"]["references"]
    assert any(d["path"] == "CLAUDE.md" and d["title"] == "My Project" for d in refs)


def test_provider_summary_shape(tmp_path):
    make_claude_repo(tmp_path)
    _, _, part = _normalize(tmp_path)
    prov = part["provider"]
    assert prov["id"] == "claude"
    assert prov["displayName"] == "Claude Code"
    assert prov["detected"] is True
