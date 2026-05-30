from acc.ids import stable_id, rel_posix


def test_stable_id_is_deterministic_and_12_chars():
    a = stable_id("generic", "doc", "docs/x.md", "Title")
    b = stable_id("generic", "doc", "docs/x.md", "Title")
    assert a == b
    assert len(a) == 12
    assert a.isalnum()


def test_stable_id_changes_with_inputs():
    base = stable_id("generic", "doc", "docs/x.md", "Title")
    assert base != stable_id("claude", "doc", "docs/x.md", "Title")
    assert base != stable_id("generic", "skill", "docs/x.md", "Title")
    assert base != stable_id("generic", "doc", "docs/y.md", "Title")
    assert base != stable_id("generic", "doc", "docs/x.md", "Other")


def test_stable_id_delimiter_prevents_collision():
    # without the NUL delimiter these would collide
    assert stable_id("a", "bc", "d", "") != stable_id("a", "b", "cd", "")


def test_rel_posix_uses_forward_slashes(tmp_path):
    root = tmp_path
    f = root / "sub" / "a.md"
    f.parent.mkdir(parents=True)
    f.write_text("hi")
    assert rel_posix(f, root) == "sub/a.md"


def test_rel_posix_handles_symlinked_dir_under_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "a.md").write_text("x")
    link = root / "lnk"
    link.symlink_to(outside, target_is_directory=True)
    # path is lexically under root via the symlink; its resolved path escapes root
    assert rel_posix(link / "a.md", root) == "lnk/a.md"
