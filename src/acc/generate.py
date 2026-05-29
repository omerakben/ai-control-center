import html as _html
from pathlib import Path
from .scan import scan_files
from .digest import source_digest
from .schema import SCHEMA_VERSION, validate
from .render import render_html
from .adapters.base import ScanContext
from .adapters.generic import GenericAdapter
from . import __version__

_PROVIDER_DIRS = (".claude", ".codex", ".cursor")


def detect_out_dir(root: Path) -> Path:
    root = root.resolve()
    for prov in _PROVIDER_DIRS:
        if (root / prov).is_dir():
            return (root / prov).resolve()
    return (root / ".ai-control-center").resolve()


def _build_search(part: dict) -> list[dict]:
    records: list[dict] = []
    for group in part["docs"].values():
        for doc in group:
            records.append({"id": doc["id"], "title": doc["title"],
                            "path": doc["path"], "text": _html.escape(doc.get("summary", ""))})
    records.sort(key=lambda r: (r["path"], r["title"]))
    return records


def _escape_plain_text_fields(part: dict) -> None:
    """HTML-escape summary (plain-text) on every doc so raw tags never appear in the output file."""
    for group in part["docs"].values():
        for doc in group:
            if "summary" in doc:
                doc["summary"] = _html.escape(doc["summary"])


def generate(root: Path, out_dir: Path | None = None) -> Path:
    root = root.resolve()

    # Resolve out_dir early so we can exclude it from the source scan, which
    # keeps source_digest stable across repeated calls (the written dashboard
    # must not feed back into its own digest).
    out_dir = out_dir.resolve() if out_dir else detect_out_dir(root)

    all_files = scan_files(root)
    # Exclude anything written under the output directory.
    files = [f for f in all_files if not str(f.resolve()).startswith(str(out_dir) + "/")
             and f.resolve() != out_dir]

    ctx = ScanContext(root=root, files=files)
    adapter = GenericAdapter()
    proot = adapter.detect(ctx)[0]
    part = adapter.normalize(ctx, proot)

    # Escape plain-text fields before they land in the HTML data island.
    _escape_plain_text_fields(part)

    out_dir.mkdir(parents=True, exist_ok=True)
    dashboard = out_dir / "dashboard.html"

    data = {
        "schemaVersion": SCHEMA_VERSION,
        "generator": {"name": "ai-control-center", "version": __version__, "rendererDigest": ""},
        "source": {
            "repoName": root.name,
            "dashboardPath": (
                dashboard.resolve().relative_to(root).as_posix()
                if dashboard.resolve().is_relative_to(root)
                else str(dashboard.resolve())
            ),
            "sourceDigest": source_digest(files, root),
            "vcs": {"kind": "none"},
        },
        "providers": [{"id": "generic", "displayName": "Generic", "root": "."}],
        "project": part["project"],
        "inventory": part["inventory"],
        "docs": {**part["docs"], "references": part["docs"]["references"]},
        "relationships": part["relationships"],
        "search": _build_search(part),
    }
    validate(data)
    dashboard.write_text(render_html(data), encoding="utf-8")
    return dashboard
