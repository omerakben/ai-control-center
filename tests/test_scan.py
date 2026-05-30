from acc.scan import scan_files, DEFAULT_EXCLUDES


def test_scan_is_sorted_and_relative(tmp_path):
    (tmp_path / "b.md").write_text("b")
    (tmp_path / "a.md").write_text("a")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.md").write_text("c")
    rels = [p.relative_to(tmp_path).as_posix() for p in scan_files(tmp_path)]
    assert rels == ["a.md", "b.md", "sub/c.md"]


def test_scan_excludes_known_dirs(tmp_path):
    (tmp_path / "keep.md").write_text("k")
    for bad in DEFAULT_EXCLUDES:
        d = tmp_path / bad
        d.mkdir()
        (d / "skip.md").write_text("s")
    rels = [p.relative_to(tmp_path).as_posix() for p in scan_files(tmp_path)]
    assert rels == ["keep.md"]


def test_scan_skips_symlinks(tmp_path):
    real = tmp_path / "real.md"
    real.write_text("r")
    (tmp_path / "link.md").symlink_to(real)
    rels = [p.relative_to(tmp_path).as_posix() for p in scan_files(tmp_path)]
    assert rels == ["real.md"]


def test_scan_keeps_file_named_like_excluded_dir(tmp_path):
    # a regular FILE whose name matches an excluded DIR must be kept
    (tmp_path / "vendor").write_text("not a dir")
    (tmp_path / "build").write_text("also a file")
    (tmp_path / "keep.md").write_text("k")
    rels = [p.relative_to(tmp_path).as_posix() for p in scan_files(tmp_path)]
    assert "vendor" in rels
    assert "build" in rels
    assert "keep.md" in rels
