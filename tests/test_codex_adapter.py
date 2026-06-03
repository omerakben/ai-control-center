from acc.adapters.base import ScanContext
from acc.adapters.codex import CodexAdapter
from acc.scan import scan_files
from tests.builders import make_codex_repo, make_brownfield_repo


def _normalize(tmp_path):
    ctx = ScanContext(root=tmp_path, files=scan_files(tmp_path))
    ad = CodexAdapter()
    roots = ad.detect(ctx)
    return roots, (ad.normalize(ctx, roots[0]) if roots else None)


def test_detects_codex_provider(tmp_path):
    make_codex_repo(tmp_path)
    roots, _ = _normalize(tmp_path)
    assert roots and roots[0].provider == "codex"


def test_does_not_detect_on_brownfield(tmp_path):
    make_brownfield_repo(tmp_path)
    ctx = ScanContext(root=tmp_path, files=scan_files(tmp_path))
    assert CodexAdapter().detect(ctx) == []


def test_inventories_mcp_from_toml(tmp_path):
    make_codex_repo(tmp_path)
    _, part = _normalize(tmp_path)
    names = {m["title"] for m in part["inventory"]["mcpServers"]}
    assert "context7" in names


def test_prompts_map_into_commands_bucket(tmp_path):
    make_codex_repo(tmp_path)
    _, part = _normalize(tmp_path)
    cmds = part["inventory"]["commands"]
    assert any(c["title"] == "refactor" and c["typeLabel"] == "Codex prompt" for c in cmds)


def test_prompt_frontmatter_fallbacks_require_strings(tmp_path):
    prompts = tmp_path / ".codex" / "prompts"
    prompts.mkdir(parents=True)
    (prompts / "bad_meta.md").write_text(
        "---\nname: [bad]\ndescription: true\n---\nPrompt body summary.\n"
    )
    _, part = _normalize(tmp_path)
    cmd = part["inventory"]["commands"][0]
    assert cmd["title"] == "bad_meta"
    assert cmd["summary"] == "Prompt body summary."


def test_surfaces_agents_md_doc(tmp_path):
    make_codex_repo(tmp_path)
    _, part = _normalize(tmp_path)
    refs = part["docs"]["references"]
    assert any(d["path"] == "AGENTS.md" for d in refs)


def test_provider_summary_has_config_facts(tmp_path):
    make_codex_repo(tmp_path)
    _, part = _normalize(tmp_path)
    prov = part["provider"]
    assert prov["id"] == "codex"
    assert prov["displayName"] == "Codex"
    assert prov["config"]["model"] == "gpt-5.5"
    assert prov["config"]["approval_policy"] == "on-request"


def test_survives_array_of_tables_mcp(tmp_path):
    # `[[mcp_servers]]` (array-of-tables typo) parses to a list — must not crash
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text('[[mcp_servers]]\nname = "x"\n')
    _, part = _normalize(tmp_path)
    assert part["inventory"]["mcpServers"] == []


def test_drops_mcp_env_secret(tmp_path):
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex" / "config.toml").write_text(
        '[mcp_servers.db]\ncommand = "psql"\n'
        '[mcp_servers.db.env]\nPGPASSWORD = "s3cr3tpassword"\n')
    _, part = _normalize(tmp_path)
    assert "s3cr3tpassword" not in str(part)
    db = next(m for m in part["inventory"]["mcpServers"] if m["title"] == "db")
    assert "env" not in db["config"]
