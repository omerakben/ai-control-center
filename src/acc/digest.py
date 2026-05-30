import hashlib
from pathlib import Path


def source_digest(files: list[Path], root: Path) -> str:
    root = root.resolve()
    h = hashlib.sha256()
    for p in sorted(files, key=lambda x: x.resolve().relative_to(root).as_posix()):
        rel_bytes = p.resolve().relative_to(root).as_posix().encode("utf-8")
        content = p.read_bytes()
        # Length-prefix each field (8-byte big-endian) so the byte stream is
        # unambiguous even when content contains NUL bytes. A bare `rel\0content\0`
        # framing could collide two different file sets (paths can't hold NUL, but
        # content can), masking real source changes.
        h.update(len(rel_bytes).to_bytes(8, "big"))
        h.update(rel_bytes)
        h.update(len(content).to_bytes(8, "big"))
        h.update(content)
    return h.hexdigest()[:16]
