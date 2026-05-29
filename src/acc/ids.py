import hashlib
from pathlib import Path


def stable_id(provider: str, kind: str, rel_path: str, heading: str = "") -> str:
    raw = f"{provider}\0{kind}\0{rel_path}\0{heading}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def rel_posix(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
