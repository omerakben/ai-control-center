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


def test_local_secret_file_does_not_change_digest(tmp_path):
    # the committed, public sourceDigest must not depend on a developer's
    # private .env / settings.local.json — planting one leaves the digest equal.
    (tmp_path / "a.md").write_text("hello")
    base = source_digest(scan_files(tmp_path), tmp_path)
    (tmp_path / ".env").write_text("DB_PASSWORD=hunter2hunter2hunter2hunter2")
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.local.json").write_text('{"x": 1}')
    after = source_digest(scan_files(tmp_path), tmp_path)
    assert base == after


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
