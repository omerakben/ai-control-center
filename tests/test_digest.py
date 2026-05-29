from acc.digest import source_digest
from acc.scan import scan_files


def test_digest_is_stable(tmp_path):
    (tmp_path / "a.md").write_text("hello")
    files = scan_files(tmp_path)
    assert source_digest(files, tmp_path) == source_digest(files, tmp_path)


def test_digest_changes_with_content(tmp_path):
    (tmp_path / "a.md").write_text("hello")
    before = source_digest(scan_files(tmp_path), tmp_path)
    (tmp_path / "a.md").write_text("hello world")
    after = source_digest(scan_files(tmp_path), tmp_path)
    assert before != after
