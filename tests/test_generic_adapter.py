from acc.adapters.base import ScanContext
from acc.adapters.generic import GenericAdapter
from acc.scan import scan_files


def _ctx(tmp_path):
    return ScanContext(root=tmp_path, files=scan_files(tmp_path))


def test_generic_extracts_docs_and_headings(tmp_path):
    (tmp_path / "notes.md").write_text("# Notes\n\nSome body text.")
    part = GenericAdapter().normalize(_ctx(tmp_path), GenericAdapter().detect(_ctx(tmp_path))[0])
    refs = part["docs"]["references"]
    assert len(refs) == 1
    assert refs[0]["title"] == "Notes"
    assert refs[0]["path"] == "notes.md"
    assert "<p>Some body text.</p>" in refs[0]["html"]


def test_generic_collects_open_todos(tmp_path):
    (tmp_path / "plan.md").write_text("- [ ] ship it\n- [x] done already")
    part = GenericAdapter().normalize(_ctx(tmp_path), GenericAdapter().detect(_ctx(tmp_path))[0])
    todos = [t["text"] for t in part["project"]["openTodos"]]
    assert todos == ["ship it"]


def test_generic_redacts_secrets_in_docs(tmp_path):
    (tmp_path / "config.md").write_text("token ghp_0123456789abcdefghij")
    part = GenericAdapter().normalize(_ctx(tmp_path), GenericAdapter().detect(_ctx(tmp_path))[0])
    blob = str(part)
    assert "ghp_0123456789abcdefghij" not in blob


def test_generic_uses_readme_title(tmp_path):
    (tmp_path / "README.md").write_text("# My Project\n\nintro")
    part = GenericAdapter().normalize(_ctx(tmp_path), GenericAdapter().detect(_ctx(tmp_path))[0])
    assert part["project"]["title"] == "My Project"
