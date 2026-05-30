from acc.scan import scan_files
from tests.builders import (
    make_claude_repo, make_codex_repo, make_cursor_repo,
    make_multi_provider_repo, make_brownfield_repo,
)


def _rels(root):
    return {p.relative_to(root).as_posix() for p in scan_files(root)}


def test_claude_repo_has_expected_files(tmp_path):
    make_claude_repo(tmp_path)
    rels = _rels(tmp_path)
    assert ".claude/agents/reviewer.md" in rels
    assert ".claude/commands/ship.md" in rels
    assert ".claude/skills/pdf/SKILL.md" in rels
    assert ".claude/settings.json" in rels
    assert ".mcp.json" in rels
    assert "CLAUDE.md" in rels


def test_codex_repo_has_expected_files(tmp_path):
    make_codex_repo(tmp_path)
    rels = _rels(tmp_path)
    assert ".codex/config.toml" in rels
    assert ".codex/prompts/refactor.md" in rels
    assert "AGENTS.md" in rels


def test_cursor_repo_has_expected_files(tmp_path):
    make_cursor_repo(tmp_path)
    rels = _rels(tmp_path)
    assert ".cursor/rules/style.mdc" in rels
    assert ".cursorrules" in rels
    assert ".cursor/mcp.json" in rels


def test_multi_provider_repo_has_all_three(tmp_path):
    make_multi_provider_repo(tmp_path)
    rels = _rels(tmp_path)
    assert ".claude/agents/reviewer.md" in rels
    assert ".codex/config.toml" in rels
    assert ".cursor/rules/style.mdc" in rels
    assert "docs/notes.md" in rels


def test_brownfield_repo_has_only_loose_markdown(tmp_path):
    make_brownfield_repo(tmp_path)
    rels = _rels(tmp_path)
    assert "README.md" in rels
    assert not any(r.startswith((".claude/", ".codex/", ".cursor/")) for r in rels)
