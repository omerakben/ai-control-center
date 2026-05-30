import hashlib
from pathlib import Path


def stable_id(provider: str, kind: str, rel_path: str, heading: str = "") -> str:
    raw = f"{provider}\0{kind}\0{rel_path}\0{heading}"
    # 12 hex chars = 48 bits, ample for any repo-scale corpus
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def rel_posix(path: Path, root: Path) -> str:
    # Try the lexical absolute path first so the scanned structure is preserved
    # even when a symlinked directory inside the repo points elsewhere (resolving
    # both would escape root and raise). Fall back to a resolved comparison.
    try:
        return path.absolute().relative_to(root.absolute()).as_posix()
    except ValueError:
        try:
            return path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            raise ValueError(f"path {path!r} is not under root {root!r}") from None
