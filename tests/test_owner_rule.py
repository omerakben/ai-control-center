import pytest
from acc.generate import resolve_owner, detect_providers, OwnerAmbiguousError
from tests.builders import make_claude_repo, make_codex_repo, make_multi_provider_repo


def test_detect_providers_lists_present(tmp_path):
    make_multi_provider_repo(tmp_path)
    assert detect_providers(tmp_path) == ["claude", "codex", "cursor"]


def test_detect_providers_empty_on_brownfield(tmp_path):
    (tmp_path / "README.md").write_text("# x")
    assert detect_providers(tmp_path) == []


def test_owner_none_existing_uses_precedence(tmp_path):
    make_multi_provider_repo(tmp_path)
    out = resolve_owner(tmp_path, detect_providers(tmp_path))
    assert out == (tmp_path / ".claude").resolve()


def test_owner_codex_only(tmp_path):
    make_codex_repo(tmp_path)
    out = resolve_owner(tmp_path, detect_providers(tmp_path))
    assert out == (tmp_path / ".codex").resolve()


def test_owner_falls_back_when_no_provider(tmp_path):
    out = resolve_owner(tmp_path, [])
    assert out == (tmp_path / ".ai-control-center").resolve()


def test_owner_single_existing_dashboard_wins(tmp_path):
    make_codex_repo(tmp_path)
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".cursor" / "dashboard.html").write_text("<html>")
    out = resolve_owner(tmp_path, detect_providers(tmp_path))
    assert out == (tmp_path / ".cursor").resolve()


def test_owner_multiple_existing_raises(tmp_path):
    for d in (".claude", ".codex"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "dashboard.html").write_text("<html>")
    with pytest.raises(OwnerAmbiguousError, match="--owner"):
        resolve_owner(tmp_path, ["claude", "codex"])


def test_owner_override_wins(tmp_path):
    for d in (".claude", ".codex"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "dashboard.html").write_text("<html>")
    out = resolve_owner(tmp_path, ["claude", "codex"], owner_override=".codex")
    assert out == (tmp_path / ".codex").resolve()
