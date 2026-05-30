import os
from pathlib import Path

DEFAULT_EXCLUDES = {
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    ".superpowers", ".remember", "dist", "build", ".next", "vendor",
    # generated tool caches — their contents change between runs, so indexing
    # them adds noise and breaks the byte-stable sourceDigest guarantee
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
}


def scan_files(root: Path, excludes: set[str] | None = None) -> list[Path]:
    if excludes is None:
        excludes = DEFAULT_EXCLUDES
    root = root.resolve()
    out: list[Path] = []
    # Top-down walk so excluded directories are pruned BEFORE descending (keeps
    # node_modules/.git/etc. from being traversed at all). Only directory names
    # are matched against excludes — a regular file named `vendor`/`build` is
    # kept, unlike the old set(parts) filter which dropped it.
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = [d for d in dirnames if d not in excludes]
        base = Path(dirpath)
        for name in filenames:
            p = base / name
            if p.is_symlink() or not p.is_file():
                continue
            out.append(p)
    return sorted(out, key=lambda x: x.relative_to(root).as_posix())
