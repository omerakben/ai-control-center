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


def test_scan_excludes_local_secret_files(tmp_path):
    # local credential / per-machine state files must never be scanned: their
    # bytes would otherwise feed the committed, public sourceDigest.
    (tmp_path / "keep.md").write_text("k")
    (tmp_path / ".env").write_text("AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE")
    (tmp_path / ".env.local").write_text("TOKEN=ghp_deadbeefdeadbeefdeadbeefdeadbeef0000")
    (tmp_path / ".DS_Store").write_bytes(b"\x00\x01")
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.local.json").write_text('{"permissions": {"allow": []}}')
    (claude / "scheduled_tasks.lock").write_text("pid 4242")
    rels = [p.relative_to(tmp_path).as_posix() for p in scan_files(tmp_path)]
    assert rels == ["keep.md"]


def test_scan_keeps_env_placeholder_files(tmp_path):
    # committed placeholders carry no secrets and stay part of the scan
    for name in (".env.example", ".env.sample", ".env.template"):
        (tmp_path / name).write_text("API_KEY=changeme")
    (tmp_path / "keep.md").write_text("k")
    rels = [p.relative_to(tmp_path).as_posix() for p in scan_files(tmp_path)]
    assert set(rels) == {".env.example", ".env.sample", ".env.template", "keep.md"}


def test_scan_envrc_placeholders_kept_secrets_dropped(tmp_path):
    # the .env safe-suffix carve-out applies to .envrc.* too: placeholders stay,
    # real direnv files (.envrc, .envrc.local) are excluded.
    (tmp_path / ".envrc").write_text("export TOKEN=ghp_x")
    (tmp_path / ".envrc.local").write_text("export TOKEN=ghp_y")
    for name in (".envrc.example", ".envrc.sample", ".envrc.template"):
        (tmp_path / name).write_text("export TOKEN=changeme")
    (tmp_path / "keep.md").write_text("k")
    rels = [p.relative_to(tmp_path).as_posix() for p in scan_files(tmp_path)]
    assert set(rels) == {".envrc.example", ".envrc.sample", ".envrc.template", "keep.md"}


def test_scan_excludes_build_and_local_artifacts(tmp_path):
    # case-insensitive secret names, direnv, and build eggs feed source_digest
    # if scanned, so all are pruned. (`.env` as a directory is tested separately
    # because a case-insensitive FS cannot hold both `.ENV` and `.env` at once.)
    (tmp_path / "keep.md").write_text("k")
    (tmp_path / ".ENV").write_text("AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE")
    (tmp_path / ".envrc").write_text("export TOKEN=ghp_x")
    direnv = tmp_path / ".direnv"
    direnv.mkdir()
    (direnv / "cache").write_text("c")
    egg = tmp_path / "agent_context_center.egg-info"
    egg.mkdir()
    (egg / "PKG-INFO").write_text("Metadata-Version: 2.1")
    rels = [p.relative_to(tmp_path).as_posix() for p in scan_files(tmp_path)]
    assert rels == ["keep.md"]


def test_scan_excludes_vs_dotnet_artifact_dirs(tmp_path):
    # Visual Studio / .NET build + IDE-state dirs. `.vs` holds open-locked
    # `.vsidx` index files that crash source_digest's read_bytes() on Windows;
    # bin/obj/packages/TestResults are per-build artifacts that would churn the
    # byte-stable digest. None hold AI-context markdown an adapter would parse.
    (tmp_path / "keep.md").write_text("k")
    for bad in (".vs", ".vscode", "bin", "obj", "packages",
                "TestResults", "Screenshots", "TestReports"):
        d = tmp_path / bad
        d.mkdir()
        (d / "skip.md").write_text("s")
    rels = [p.relative_to(tmp_path).as_posix() for p in scan_files(tmp_path)]
    assert rels == ["keep.md"]


def test_scan_excludes_secret_named_directory(tmp_path):
    # a `.env` used as a DIRECTORY (some secret-manager layouts) would otherwise
    # be descended into and its contents hashed into the digest.
    (tmp_path / "keep.md").write_text("k")
    envdir = tmp_path / ".env"
    envdir.mkdir()
    (envdir / "credentials").write_text("SECRET=value")
    rels = [p.relative_to(tmp_path).as_posix() for p in scan_files(tmp_path)]
    assert rels == ["keep.md"]
