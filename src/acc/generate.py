import copy
import html as _html
import logging
import os
from pathlib import Path
from .scan import scan_files
from .digest import source_digest
from .schema import SCHEMA_VERSION, validate
from .render import render_html
from .ids import rel_posix
from .adapters.base import ScanContext, empty_inventory, empty_docs
from .adapters.generic import GenericAdapter, harvest_todos
from .adapters.claude import ClaudeAdapter
from .adapters.codex import CodexAdapter
from .adapters.cursor import CursorAdapter
from . import __version__

logger = logging.getLogger(__name__)

_WARN_BYTES = 1_000_000
_TRUNCATE_BYTES = 2_000_000

_PROVIDER_MARKERS = {"claude": "CLAUDE.md", "codex": "AGENTS.md", "cursor": ".cursorrules"}
_PROVIDER_DIR_BY_ID = {"claude": ".claude", "codex": ".codex", "cursor": ".cursor"}
_PRECEDENCE = ("claude", "codex", "cursor")
_KNOWN_OWNER_DIRS = (".claude", ".codex", ".cursor", ".ai-control-center")


class OwnerAmbiguousError(Exception):
    pass


def detect_providers(root: Path) -> list[str]:
    root = root.resolve()
    out: list[str] = []
    for pid in _PRECEDENCE:
        if (root / _PROVIDER_DIR_BY_ID[pid]).is_dir() or (root / _PROVIDER_MARKERS[pid]).is_file():
            out.append(pid)
    return out


def _existing_dashboards(root: Path) -> list[Path]:
    return [root / d / "dashboard.html" for d in _KNOWN_OWNER_DIRS
            if (root / d / "dashboard.html").is_file()]


def resolve_owner(root: Path, detected_ids: list[str], owner_override: str | None = None) -> Path:
    root = root.resolve()
    if owner_override:
        return (root / owner_override).resolve()
    existing = _existing_dashboards(root)
    if len(existing) == 1:
        return existing[0].parent.resolve()
    if len(existing) >= 2:
        names = ", ".join(d.parent.relative_to(root).as_posix() for d in existing)
        raise OwnerAmbiguousError(
            f"multiple dashboards found ({names}); pick one with --owner <dir>")
    for pid in _PRECEDENCE:
        if pid in detected_ids:
            return (root / _PROVIDER_DIR_BY_ID[pid]).resolve()
    return (root / ".ai-control-center").resolve()


def detect_out_dir(root: Path) -> Path:
    root = root.resolve()
    return resolve_owner(root, detect_providers(root))


_FIRST_CLASS = (ClaudeAdapter, CodexAdapter, CursorAdapter)
_CLAIM_DIRS = (".claude", ".codex", ".cursor")
_CLAIM_MARKERS = ("CLAUDE.md", "AGENTS.md", ".cursorrules")


def _claimed_by_provider(rel: str) -> bool:
    top = rel.split("/", 1)[0]
    return top in _CLAIM_DIRS or rel in _CLAIM_MARKERS


def _merge_parts(parts: list[dict]) -> tuple[dict, dict]:
    inv = empty_inventory()
    docs = empty_docs()
    for part in parts:
        for k, items in part.get("inventory", {}).items():
            inv.setdefault(k, []).extend(items)
        for k, items in part.get("docs", {}).items():
            docs.setdefault(k, []).extend(items)
    for bucket in (inv, docs):
        for k in bucket:
            bucket[k].sort(key=lambda x: (x["path"], x["title"], x["id"]))
    return inv, docs


def _build_search(inv: dict, docs: dict) -> list[dict]:
    records: list[dict] = []
    for bucket in (docs, inv):
        for items in bucket.values():
            for it in items:
                records.append({"id": it["id"], "title": it["title"],
                                "path": it["path"], "text": it.get("summary", "")})
    records.sort(key=lambda r: (r["path"], r["title"], r["id"]))
    return records


def _escape_text_fields(inv: dict, docs: dict, project: dict) -> None:
    # Escape every author-derived plain-text display field so hostile content
    # (script tags, onerror, </script>) can never reach the data island raw.
    # The `html` field is already sanitized by render_markdown_safe — leave it.
    for bucket in (inv, docs):
        for items in bucket.values():
            for it in items:
                for field in ("title", "summary"):
                    if field in it:
                        # display fields are strings by contract; coerce any
                        # wrong-shape leaf from a malformed config so escape
                        # (and the renderer) never sees a list/dict here
                        value = it[field]
                        it[field] = _html.escape(value if isinstance(value, str) else "")
    project["title"] = _html.escape(project.get("title", ""))
    for todo in project.get("openTodos", []):
        if "text" in todo:
            todo["text"] = _html.escape(todo["text"])


def _path_prefix(root: Path, out_dir: Path) -> str:
    """Posix relative path from the dashboard's dir back to the repo root.

    Normally "..", "." when out_dir == root, "../.." when nested. Returns ""
    when the path is not expressible (e.g. a different Windows drive), in which
    case the renderer falls back to plain-text paths instead of a broken href.
    """
    try:
        return Path(os.path.relpath(root, out_dir)).as_posix()
    except ValueError:
        return ""


def _reduce_for_size(data: dict) -> dict:
    """Summary-only island: deep-copy then blank known heavy values.

    Blanks every inventory/doc summary, every doc html body, and the search
    array, and sets generator.truncated. Deep-copy-then-blank preserves every
    key and optional field (item id, MCP config, doc id), so validate() and
    assert_no_secrets still pass on the result.
    """
    reduced = copy.deepcopy(data)
    for bucket in reduced["inventory"].values():
        for item in bucket:
            item["summary"] = ""
    for bucket in reduced["docs"].values():
        for doc in bucket:
            doc["summary"] = ""
            if "html" in doc:
                doc["html"] = ""
    reduced["search"] = []
    reduced["generator"]["truncated"] = True
    return reduced


def generate(root: Path, out_dir: Path | None = None, owner: str | None = None) -> Path:
    root = root.resolve()
    all_files = scan_files(root)

    detected_ids = detect_providers(root)
    out_dir = out_dir.resolve() if out_dir else resolve_owner(root, detected_ids, owner)
    dashboard = (out_dir / "dashboard.html").resolve()

    # Exclude every known dashboard.html (not just the target) so a stale
    # dashboard left in another provider folder cannot perturb sourceDigest.
    known_dashboards = {(root / d / "dashboard.html").resolve() for d in _KNOWN_OWNER_DIRS}
    known_dashboards.add(dashboard)
    files = [f for f in all_files if f.resolve() not in known_dashboards]
    ctx = ScanContext(root=root, files=files)

    parts: list[dict] = []
    provider_summaries: list[dict] = []
    for adapter_cls in _FIRST_CLASS:
        adapter = adapter_cls()
        roots = adapter.detect(ctx)
        if not roots:
            continue
        part = adapter.normalize(ctx, roots[0])
        parts.append(part)
        provider_summaries.append(part["provider"])

    # generic indexes only the markdown not claimed by a provider folder/marker
    claimed, unclaimed = [], []
    for f in files:
        (claimed if _claimed_by_provider(rel_posix(f, root)) else unclaimed).append(f)
    gctx = ScanContext(root=root, files=unclaimed)
    gadapter = GenericAdapter()
    gpart = gadapter.normalize(gctx, gadapter.detect(gctx)[0])
    # Provider docs are dropped from generic doc indexing, but the open TODOs
    # inside them still belong to the project — harvest them before the filter
    # discards the files, then re-sort to keep output deterministic.
    project = gpart["project"]
    project["openTodos"].extend(harvest_todos(claimed, root))
    project["openTodos"].sort(key=lambda t: (t["path"], t["text"]))
    parts.append(gpart)
    provider_summaries.append({"id": "generic", "displayName": "Generic",
                               "root": ".", "detected": True})

    inv, docs = _merge_parts(parts)
    _escape_text_fields(inv, docs, gpart["project"])  # escape titles/summaries for the island
    search = _build_search(inv, docs)   # search reads the escaped fields (Phase 1 contract)

    out_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "schemaVersion": SCHEMA_VERSION,
        "generator": {"name": "ai-control-center", "version": __version__,
                      "rendererDigest": "", "truncated": False},
        "source": {
            "repoName": root.name,
            "pathPrefix": _path_prefix(root, out_dir),
            "dashboardPath": (
                dashboard.relative_to(root).as_posix()
                if dashboard.is_relative_to(root) else str(dashboard)
            ),
            "sourceDigest": source_digest(files, root),
            "vcs": {"kind": "none"},
        },
        "providers": provider_summaries,
        "project": gpart["project"],
        "inventory": inv,
        "docs": docs,
        "relationships": [],
        "search": search,
    }
    validate(data)
    html = render_html(data)
    size = len(html.encode("utf-8"))
    if size > _TRUNCATE_BYTES:
        reduced = _reduce_for_size(data)
        validate(reduced)
        html = render_html(reduced)
        rsize = len(html.encode("utf-8"))
        logger.warning("dashboard %d bytes exceeds %d; reduced to %d bytes",
                       size, _TRUNCATE_BYTES, rsize)
        # Last-resort guard: reducer blanks heavy content so this is rarely hit.
        if rsize > _TRUNCATE_BYTES:
            logger.warning("reduced dashboard still %d bytes (over budget)", rsize)
    elif size > _WARN_BYTES:
        logger.warning("dashboard %d bytes exceeds %d", size, _WARN_BYTES)
    dashboard.write_text(html, encoding="utf-8")
    return dashboard
