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


def test_digest_disambiguates_nul_in_content(tmp_path):
    # Two different file SETS that collide under naive `rel\0content\0` framing
    # must produce different digests.
    a = tmp_path / "set_a"
    a.mkdir()
    (a / "p").write_bytes(b"\x00q\x00hello")
    b = tmp_path / "set_b"
    b.mkdir()
    (b / "p").write_bytes(b"")
    (b / "q").write_bytes(b"hello")
    assert source_digest(scan_files(a), a) != source_digest(scan_files(b), b)
