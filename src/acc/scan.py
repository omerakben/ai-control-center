import os
from pathlib import Path

DEFAULT_EXCLUDES = {
    ".git", "node_modules", ".venv", "venv", "__pycache__",
    ".superpowers", ".remember", "dist", "build", ".next", "vendor",
    # agent/tool-local state dirs — never part of the shared repo, can hold
    # session data, and would otherwise perturb the byte-stable sourceDigest
    ".serena", ".playwright-mcp", ".direnv",
    # generated tool caches — their contents change between runs, so indexing
    # them adds noise and breaks the byte-stable sourceDigest guarantee
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
}

# `.env` variants that are safe to scan: they hold placeholder values and are
# routinely committed as documentation, so they may contribute to the digest.
_ENV_SAFE_SUFFIXES = (".example", ".sample", ".template")


def _is_local_secret_file(name: str) -> bool:
    """Names that must never be scanned, matched case-insensitively in any dir.

    These hold local credentials (`.env`, `.env.local`, `.envrc`) or per-machine
    state (`settings.local.json`, the scheduler lock). No adapter renders them,
    but `source_digest` hashes every scanned file's bytes — so without this
    filter a developer's private `.env` would change the `sourceDigest` baked
    into the committed, shared, public dashboard, breaking byte-stable output
    across machines. Matched on both files and directory names (a `.env/`
    directory leaks the same way). Placeholder `.env.example`/`.sample`/
    `.template` files are kept. `.gitignore` is not consulted, so this list and
    the digest stay identical on non-git repos; widening it to honor `.gitignore`
    is a deferred follow-up.
    """
    low = name.lower()
    if low in {".ds_store", "settings.local.json", "scheduled_tasks.lock"}:
        return True
    if low in {".env", ".envrc"}:
        return True
    if low.startswith(".env.") and not low.endswith(_ENV_SAFE_SUFFIXES):
        return True
    if low.startswith(".envrc."):
        return True
    return False


def _is_excluded_dir(name: str, excludes: set[str]) -> bool:
    # `*.egg-info` is a build artifact that appears the moment anyone runs
    # `pip install`/`-e .`; matching it by suffix (not a fixed name) keeps the
    # digest dependent only on shareable, tracked inputs.
    return (
        name in excludes
        or name.lower().endswith(".egg-info")
        or _is_local_secret_file(name)
    )


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
        dirnames[:] = [d for d in dirnames if not _is_excluded_dir(d, excludes)]
        base = Path(dirpath)
        for name in filenames:
            if _is_local_secret_file(name):
                continue
            p = base / name
            if p.is_symlink() or not p.is_file():
                continue
            out.append(p)
    return sorted(out, key=lambda x: x.relative_to(root).as_posix())
