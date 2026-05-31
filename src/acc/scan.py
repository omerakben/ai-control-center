import os
from pathlib import Path

DEFAULT_EXCLUDES = {
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    ".superpowers", ".remember", "dist", "build", ".next", "vendor",
    # agent/tool-local state dirs — never part of the shared repo, can hold
    # session data, and would otherwise perturb the byte-stable sourceDigest
    ".serena", ".playwright-mcp",
    # generated tool caches — their contents change between runs, so indexing
    # them adds noise and breaks the byte-stable sourceDigest guarantee
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
}

# `.env` variants that are safe to scan: they hold placeholder values and are
# routinely committed as documentation, so they may contribute to the digest.
_ENV_SAFE_SUFFIXES = (".example", ".sample", ".template")


def _is_local_secret_file(name: str) -> bool:
    """Files that must never be scanned, matched by name in any directory.

    These hold local credentials (`.env`, `.env.local`) or per-machine state
    (`settings.local.json`, the scheduler lock). No adapter renders them, but
    `source_digest` hashes every scanned file's bytes — so without this filter a
    developer's private `.env` would change the `sourceDigest` baked into the
    committed, shared, public dashboard, breaking byte-stable output across
    machines. Placeholder `.env.example`/`.sample`/`.template` files are kept.
    """
    if name in {".DS_Store", "settings.local.json", "scheduled_tasks.lock"}:
        return True
    if name == ".env":
        return True
    if name.startswith(".env.") and not name.endswith(_ENV_SAFE_SUFFIXES):
        return True
    return False


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
            if _is_local_secret_file(name):
                continue
            p = base / name
            if p.is_symlink() or not p.is_file():
                continue
            out.append(p)
    return sorted(out, key=lambda x: x.relative_to(root).as_posix())
