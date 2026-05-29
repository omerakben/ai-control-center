from pathlib import Path

DEFAULT_EXCLUDES = {
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    ".superpowers", ".remember", "dist", "build", ".next", "vendor",
}


def scan_files(root: Path, excludes: set[str] | None = None) -> list[Path]:
    if excludes is None:
        excludes = DEFAULT_EXCLUDES
    root = root.resolve()
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_symlink() or not p.is_file():
            continue
        rel_parts = set(p.relative_to(root).parts)
        if rel_parts & excludes:
            continue
        out.append(p)
    return sorted(out, key=lambda x: x.relative_to(root).as_posix())
