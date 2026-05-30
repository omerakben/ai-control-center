import copy
import html as _html
import logging
import os
import re
from pathlib import Path
from .scan import scan_files
from .digest import source_digest
from .schema import SCHEMA_VERSION, validate
from .render import render_html
from .ids import rel_posix, stable_id
from .adapters.base import ScanContext, empty_inventory, empty_docs, doc_type_label
from .adapters.generic import GenericAdapter, harvest_todos
from .adapters.claude import ClaudeAdapter
from .adapters.codex import CodexAdapter
from .adapters.cursor import CursorAdapter
from . import __version__

logger = logging.getLogger(__name__)

_WARN_BYTES = 1_000_000
_TRUNCATE_BYTES = 2_000_000
# Degraded mode keeps all `declares` edges (bounded by MCP+hook count) but caps
# `reference` edges, which are unbounded in the worst case, to a deterministic prefix.
_MAX_DEGRADED_REFERENCE_EDGES = 200
# Cap on the per-item body slice appended to each search record's `text`.
# Budget math (pre-escape): at ~500 indexable items, 500 * 200 = 100 KB.
# Post-escape worst case is ~5x (& -> &amp;), so ~500 KB at 500 items — still
# under the _WARN_BYTES (1 MB) line. _reduce_for_size drops the slice entirely
# above the budget, so it is the real safety valve. str slicing is codepoint-
# based, so a char cap cuts cleanly on multibyte boundaries.
_SEARCH_BODY_CHARS = 200

_PROVIDER_MARKERS = {"claude": "CLAUDE.md", "codex": "AGENTS.md", "cursor": ".cursorrules"}
_PROVIDER_DIR_BY_ID = {"claude": ".claude", "codex": ".codex", "cursor": ".cursor"}
_PRECEDENCE = ("claude", "codex", "cursor")
_KNOWN_OWNER_DIRS = (".claude", ".codex", ".cursor", ".ai-control-center")

# The provider config files that declare MCP servers and hooks. They are the
# `declares` channel, so they are never `reference` targets — otherwise a
# single-server config (one id, unique path) would draw a stray reference edge.
_CONFIG_PATHS = frozenset({
    ".claude/settings.json", ".mcp.json", ".codex/config.toml", ".cursor/mcp.json",
})


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


def _build_relationships(inv: dict, docs: dict) -> list[dict]:
    """Deterministic edges over the merged inventory + docs.

    `reference`: a doc body mentions an inventory item's exact, unique,
    boundary-delimited repo-relative path. `declares` (Task 3): a config-file
    node -> the MCP servers / hooks it declares.
    """
    edges: list[dict] = []

    # reference pass: path -> set(ids) over inventory items only, keep unique
    # paths that are not a provider config file.
    path_ids: dict[str, set[str]] = {}
    for items in inv.values():
        for it in items:
            path_ids.setdefault(it["path"], set()).add(it["id"])
    unique = {p: next(iter(ids)) for p, ids in path_ids.items()
              if len(ids) == 1 and p not in _CONFIG_PATHS}
    # boundary match: reject a hit that is part of a longer path/word token.
    # The trailing guard rejects a path that continues into more word/slash/
    # hyphen chars (e.g. ".md.bak") but allows a sentence-ending period
    # ("...reviewer.md." at a clause boundary), so a path that closes a
    # sentence still produces a reference edge.
    matchers = {p: re.compile(r"(?<![\w./-])" + re.escape(p) + r"(?![\w/-])(?!\.[\w/-])")
                for p in unique}
    for bucket in docs.values():
        for doc in bucket:
            body = doc.get("_refScanBody", "")
            if not body:
                continue
            for path, item_id in unique.items():
                if item_id == doc["id"]:
                    continue  # self-edge guard
                if matchers[path].search(body):
                    edges.append({"from": doc["id"], "to": item_id,
                                  "type": "reference", "evidence": path})

    # declares pass: config-file node -> each MCP server / hook it declares.
    # Commands are file-discovered, not config-declared, so they are excluded.
    config_items: dict[str, list[str]] = {}
    for kind in ("mcpServers", "hooks"):
        for it in inv.get(kind, []):
            config_items.setdefault(it["path"], []).append(it["id"])
    for config_path, item_ids in config_items.items():
        node_id = stable_id("config", "configFile", config_path, "")
        for item_id in item_ids:
            edges.append({"from": node_id, "to": item_id,
                          "type": "declares", "evidence": config_path})

    return _dedup_sort_edges(edges)


def _dedup_sort_edges(edges: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for e in edges:
        key = (e["from"], e["to"], e["type"])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    out.sort(key=lambda e: (e["from"], e["to"], e["type"]))
    return out


def _build_search(inv: dict, docs: dict, todos: list[dict]) -> list[dict]:
    records: list[dict] = []
    # Docs lack type/typeLabel (built by a separate adapter path keyed only by
    # bucket); synthesize a fixed type="doc" + a bucket-derived typeLabel so doc
    # hits group correctly instead of landing in an undefined group. Inventory
    # items already carry both via make_item.
    for bucket_key, items in docs.items():
        label = doc_type_label(bucket_key)
        for it in items:
            records.append(_search_record(it, "doc", label))
    for items in inv.values():
        for it in items:
            records.append(_search_record(it, it.get("type", ""), it.get("typeLabel", "")))
    # TODOs are searchable+jumpable too (spec: every searchable item has a stable
    # id). They carry {id,text,path} and no body — the (already-escaped) text is
    # both the searchable and display title, so title=text and text="". type/
    # typeLabel are fixed generator constants ("todo"/"TODO"), not author input.
    for todo in todos:
        records.append({"id": todo["id"], "type": "todo", "typeLabel": "TODO",
                        "title": todo["text"], "path": todo["path"], "text": ""})
    # Explicit sort is load-bearing: render.py's json.dumps(sort_keys=True) sorts
    # dict keys but NOT list order, so determinism depends on this.
    records.sort(key=lambda r: (r["path"], r["title"], r["id"]))
    return records


def _search_record(it: dict, type_: str, type_label: str) -> dict:
    # text = escaped summary + escaped capped body slice (both escaped on the
    # same pass in _escape_text_fields, preserving the "search reads escaped
    # fields" contract). type/type_label are generator-controlled constants,
    # not author input, so they are not escaped.
    summary = it.get("summary", "")
    body = it.get("_searchBody", "")
    text = (summary + " " + body).strip() if body and body != summary else summary
    return {"id": it["id"], "type": type_, "typeLabel": type_label,
            "title": it["title"], "path": it["path"], "text": text}


def _escape_text_fields(inv: dict, docs: dict, project: dict) -> None:
    # Escape every author-derived plain-text display field so hostile content
    # (script tags, onerror, </script>) can never reach the data island raw.
    # The `html` field is already sanitized by render_markdown_safe — leave it.
    # `provider`/`typeLabel`/`displayName` are NOT escaped here because they are
    # generator-controlled constants (adapter ids and fixed labels), never
    # author input. If a future adapter derives any of them from frontmatter,
    # add it to the escape pass below.
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
                # Capture a capped, escaped body slice on the SAME pass so the
                # island stays uniformly escaped and the later _build_search reads
                # escaped fields (Phase 1 contract). Source: a raw body if the
                # adapter carries one, else the (now-escaped) summary. char-cap the
                # RAW source before escaping so the visible length, not the
                # entity-expanded one, is what _SEARCH_BODY_CHARS bounds.
                # `_rawBody` is the documented private override: an adapter may set
                # it on an item to make the search slice come from full body text
                # instead of the summary. No adapter sets it today (items fall back
                # to the escaped summary); the branch is live plumbing for Phase 4b+.
                raw = it.get("_rawBody")
                if isinstance(raw, str) and raw:
                    it["_searchBody"] = _html.escape(raw[:_SEARCH_BODY_CHARS])
                else:
                    # no raw body: reuse the already-escaped summary as the slice
                    it["_searchBody"] = it.get("summary", "")
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
    # Light index: keep names + paths searchable after truncation, drop the
    # body slice. The omnibox still finds items by name/path in degraded mode.
    reduced["search"] = [
        {"id": r["id"], "type": r["type"], "typeLabel": r["typeLabel"],
         "title": r["title"], "path": r["path"], "text": ""}
        for r in reduced["search"]
    ]
    if "relationships" in reduced:
        declares = [e for e in reduced["relationships"] if e["type"] == "declares"]
        refs = [e for e in reduced["relationships"] if e["type"] == "reference"]
        if len(refs) > _MAX_DEGRADED_REFERENCE_EDGES:
            logger.warning("degraded mode: capping %d reference edges to %d",
                           len(refs), _MAX_DEGRADED_REFERENCE_EDGES)
            refs = refs[:_MAX_DEGRADED_REFERENCE_EDGES]
        reduced["relationships"] = sorted(
            declares + refs, key=lambda e: (e["from"], e["to"], e["type"]))
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
    # _escape_text_fields ran first, so todo["text"] is already escaped here — the
    # todo title enters the index uniformly escaped, like every other record.
    search = _build_search(inv, docs, project["openTodos"])  # reads the escaped fields (Phase 1 contract)
    relationships = _build_relationships(inv, docs)  # reads docs' _refScanBody
    # Drop the private slice key so it never reaches the serialized island.
    for bucket in (inv, docs):
        for items in bucket.values():
            for it in items:
                it.pop("_searchBody", None)
                it.pop("_refScanBody", None)

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
        "relationships": relationships,
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
