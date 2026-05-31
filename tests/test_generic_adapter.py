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
    # docs carry the full clean markdown in _refScanBody (the reading-body and
    # relationship-scan source); no server-rendered `html` is shipped anymore.
    assert "html" not in refs[0]
    assert "Some body text." in refs[0]["_refScanBody"]


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


def test_generic_strips_front_matter(tmp_path):
    (tmp_path / "doc.md").write_text(
        "---\ntitle: Meta\ntags: [a, b]\n---\n# Real Heading\n\nReal body text.\n"
    )
    part = GenericAdapter().normalize(_ctx(tmp_path), GenericAdapter().detect(_ctx(tmp_path))[0])
    ref = part["docs"]["references"][0]
    assert ref["title"] == "Real Heading"
    assert ref["summary"] == "Real body text."


def test_generic_summary_skips_list_and_code_fence(tmp_path):
    (tmp_path / "plan.md").write_text(
        "# Plan\n\n- [ ] task one\n```\ncode\n```\n\nActual prose summary.\n"
    )
    part = GenericAdapter().normalize(_ctx(tmp_path), GenericAdapter().detect(_ctx(tmp_path))[0])
    assert part["docs"]["references"][0]["summary"] == "Actual prose summary."


def test_generic_summary_keeps_emphasis_line(tmp_path):
    # a line starting with *emphasis* is real prose, not a list marker
    (tmp_path / "note.md").write_text("# Note\n\n*Important* detail here.\n")
    part = GenericAdapter().normalize(_ctx(tmp_path), GenericAdapter().detect(_ctx(tmp_path))[0])
    assert part["docs"]["references"][0]["summary"] == "*Important* detail here."


def test_generic_skips_unreadable_file(tmp_path):
    real = tmp_path / "ok.md"
    real.write_text("# OK\n\nfine")
    ghost = tmp_path / "ghost.md"  # in the file list but does not exist -> read raises OSError
    ctx = ScanContext(root=tmp_path, files=[real, ghost])
    part = GenericAdapter().normalize(ctx, GenericAdapter().detect(ctx)[0])
    assert [d["path"] for d in part["docs"]["references"]] == ["ok.md"]


def test_extract_todos_carry_stable_id():
    from acc.adapters.generic import _extract_todos
    todos = _extract_todos("- [ ] first thing\n- [ ] second thing\n", "PLAN.md")
    assert len(todos) == 2
    for t in todos:
        assert len(t["id"]) == 12
        assert set(t.keys()) == {"id", "text", "path"}
    # deterministic: same input -> same id
    again = _extract_todos("- [ ] first thing\n", "PLAN.md")
    assert again[0]["id"] == todos[0]["id"]
