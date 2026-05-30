import json
import re
from pathlib import Path
from acc.generate import generate, detect_out_dir
from tests.builders import make_multi_provider_repo, make_claude_repo, make_codex_repo


def _make_repo(tmp_path):
    (tmp_path / "README.md").write_text("# Demo\n\nA demo repo.")
    (tmp_path / "PLAN.md").write_text("- [ ] build the thing\ntoken ghp_0123456789abcdefghij")
    return tmp_path


def test_generate_writes_dashboard(tmp_path):
    out = generate(_make_repo(tmp_path))
    assert out.exists()
    assert out.name == "dashboard.html"
    assert "<!DOCTYPE html>" in out.read_text(encoding="utf-8")


def test_generate_is_deterministic(tmp_path):
    _make_repo(tmp_path)
    first = generate(tmp_path).read_text(encoding="utf-8")
    second = generate(tmp_path).read_text(encoding="utf-8")
    assert first == second


def test_generate_redacts_secrets_from_output(tmp_path):
    out = generate(_make_repo(tmp_path))
    assert "ghp_0123456789abcdefghij" not in out.read_text(encoding="utf-8")


def test_generate_escapes_hostile_markdown(tmp_path):
    (tmp_path / "evil.md").write_text("# Evil\n\n<img src=x onerror=alert(1)>")
    out = generate(tmp_path)
    html = out.read_text(encoding="utf-8")
    assert "onerror=alert(1)>" not in html
    assert "&lt;img" in html


def test_detect_out_dir_prefers_provider_folder(tmp_path):
    (tmp_path / ".claude").mkdir()
    assert detect_out_dir(tmp_path) == (tmp_path / ".claude").resolve()


def test_detect_out_dir_falls_back(tmp_path):
    assert detect_out_dir(tmp_path) == (tmp_path / ".ai-control-center").resolve()


def test_generate_includes_provider_folder_markdown(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "CLAUDE.md").write_text("# Claude Instructions\n\nProject rules.")
    out = generate(tmp_path)
    # out_dir is .claude when that folder exists
    assert out.resolve() == (tmp_path / ".claude" / "dashboard.html").resolve()
    html = out.read_text(encoding="utf-8")
    assert "Claude Instructions" in html
    assert ".claude/CLAUDE.md" in html


def _island(out_path) -> dict:
    html = out_path.read_text(encoding="utf-8")
    raw = html.split('id="acc-data"', 1)[1].split(">", 1)[1].split("</script>", 1)[0]
    return json.loads(raw.replace("<\\/", "</"))


def test_generate_merges_all_providers(tmp_path):
    make_multi_provider_repo(tmp_path)
    out = generate(tmp_path)
    data = _island(out)
    ids = {p["id"] for p in data["providers"]}
    assert {"claude", "codex", "cursor", "generic"} <= ids
    assert any(a["typeLabel"] == "Claude agent" for a in data["inventory"]["agents"])
    assert any(r["typeLabel"] == "Cursor rule" for r in data["inventory"]["rules"])
    assert data["inventory"]["mcpServers"], "expected merged mcp servers"


def test_generate_owner_is_dot_claude_for_multi(tmp_path):
    make_multi_provider_repo(tmp_path)
    out = generate(tmp_path)
    assert out.resolve() == (tmp_path / ".claude" / "dashboard.html").resolve()


def test_generate_multi_provider_is_deterministic(tmp_path):
    make_multi_provider_repo(tmp_path)
    first = generate(tmp_path).read_text(encoding="utf-8")
    second = generate(tmp_path).read_text(encoding="utf-8")
    assert first == second


def test_generic_does_not_double_list_provider_files(tmp_path):
    make_multi_provider_repo(tmp_path)
    data = _island(generate(tmp_path))
    ref_paths = [d["path"] for d in data["docs"]["references"]]
    # provider files appear via their adapters, never duplicated by generic
    assert ref_paths == sorted(set(ref_paths))
    # the loose doc is indexed; the agent file is NOT a generic reference
    assert "docs/notes.md" in ref_paths
    assert ".claude/agents/reviewer.md" not in ref_paths


def test_generate_preserves_provider_doc_todos(tmp_path):
    # CLAUDE.md is claimed by the Claude adapter (which does not extract TODOs)
    # and excluded from generic indexing — its open TODOs must still surface
    (tmp_path / ".claude").mkdir()
    (tmp_path / "CLAUDE.md").write_text(
        "# Rules\n\n- [ ] wire up CI\n- [x] already done\n")
    data = _island(generate(tmp_path))
    todos = [t["text"] for t in data["project"]["openTodos"]]
    assert "wire up CI" in todos
    assert "already done" not in todos  # checked items are not open TODOs


def test_generate_drops_mcp_env_secret(tmp_path):
    make_claude_repo(tmp_path)
    out = generate(tmp_path)
    assert "s3cr3tpassword" not in out.read_text(encoding="utf-8")


def test_generate_tripwire_blocks_unredacted_leak(tmp_path):
    # an agent whose frontmatter description carries a token shape
    make_claude_repo(tmp_path, with_secret=True)
    out = generate(tmp_path)
    # the description is redacted, so the token never reaches the file
    assert "ghp_0123456789abcdefghij" not in out.read_text(encoding="utf-8")


def test_generate_escapes_hostile_title(tmp_path):
    # a hostile frontmatter name lands in an item title — must be escaped in the island
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "x.md").write_text(
        '---\nname: "<img src=x onerror=alert(1)>"\ndescription: ok\n---\n')
    html = generate(tmp_path).read_text(encoding="utf-8")
    assert "onerror=alert(1)>" not in html
    assert "&lt;img" in html


def test_generate_digest_ignores_stale_other_dashboard(tmp_path):
    make_codex_repo(tmp_path)
    out_dir = tmp_path / ".codex"
    first = generate(tmp_path, out_dir=out_dir).read_text(encoding="utf-8")
    # a stale dashboard left in another provider folder must not perturb the digest
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "dashboard.html").write_text("<stale>" * 100)
    second = generate(tmp_path, out_dir=out_dir).read_text(encoding="utf-8")
    dig = lambda h: re.search(r'"sourceDigest":"([0-9a-f]+)"', h).group(1)
    assert dig(first) == dig(second)
