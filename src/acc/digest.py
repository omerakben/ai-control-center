import hashlib
from pathlib import Path


def source_digest(files: list[Path], root: Path) -> str:
    root = root.resolve()
    h = hashlib.sha256()
    for p in sorted(files, key=lambda x: x.resolve().relative_to(root).as_posix()):
        rel = p.resolve().relative_to(root).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:16]
