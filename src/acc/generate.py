import copy
import html as _html
import logging
import os
import re
from pathlib import Path
from typing import NamedTuple
from .scan import scan_files
from .config import load_json, load_toml, as_dict
from .digest import source_digest
from .redaction import redact_text
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
# Cap on the per-item readable `body` slice (the inline reading pane). Larger
# than the search slice because this IS the content a reader expands, but still
# bounded: at ~535 docs a 4 KB cap is ~2 MB pre-escape, so the body is the FIRST
# thing _reduce_for_size sheds on a large repo (it is what blows the budget).
# Codepoint-based slice cuts cleanly on multibyte boundaries.
_BODY_CHARS = 4000
# Graduated-truncation summary cap (step 2): shorten rather than blank.
_TRUNCATED_SUMMARY_CHARS = 280

_PROVIDER_MARKERS = {"claude": "CLAUDE.md", "codex": "AGENTS.md", "cursor": ".cursorrules"}
_PROVIDER_DIR_BY_ID = {"claude": ".claude", "codex": ".codex", "cursor": ".cursor"}
_PRECEDENCE = ("claude", "codex", "cursor")
# `.agent-context-center` is the current generic-repo fallback; `.ai-control-center`
# stays recognized so dashboards committed under the old default are still detected
# and excluded from the source digest (back-compat after the rename).
_KNOWN_OWNER_DIRS = (".claude", ".codex", ".cursor", ".agent-context-center", ".ai-control-center")

# The provider config files that declare MCP servers and hooks. They are the
# `declares` channel, so they are never `reference` targets — otherwise a
# single-server config (one id, unique path) would draw a stray reference edge.
_CONFIG_PATHS = frozenset({
    ".claude/settings.json", ".mcp.json", ".codex/config.toml", ".cursor/mcp.json",
})


class OwnerAmbiguousError(Exception):
    pass


class GenerateResult(NamedTuple):
    """What a generate run produced, for callers that need more than the path.

    `scanned_file_count` is the number of inputs that feed `source_digest`
    (after dashboards are excluded), so it matches the freshness marker the
    dashboard displays.
    """
    path: Path
    source_digest: str
    scanned_file_count: int
    providers: list[str]
    truncated: bool


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
    return (root / ".agent-context-center").resolve()


def detect_out_dir(root: Path) -> Path:
    root = root.resolve()
    return resolve_owner(root, detect_providers(root))


def _resolve_repo_name(root: Path, override: str | None = None) -> str:
    """Stable repo name for the dashboard, independent of the local checkout dir.

    `root.name` (the clone directory) is volatile: a repo cloned into `acc`
    locally and `agent-context-center` on CI would otherwise produce different
    dashboards from byte-identical content, breaking the byte-stable-across-
    machines guarantee (the sourceDigest already is stable — it hashes content +
    repo-relative paths, not the root dir name). Precedence: explicit override ->
    `pyproject.toml` `[project].name` -> `package.json` `name` -> the directory
    name as a last resort. The manifest reads are offline and deterministic.
    """
    if override and override.strip():
        return override
    py = as_dict(load_toml(root / "pyproject.toml").get("project")).get("name")
    if isinstance(py, str) and py.strip():
        return py
    js = load_json(root / "package.json").get("name")
    if isinstance(js, str) and js.strip():
        return js
    return root.name


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
            # _refScanBody is the already-redacted body; never scan the raw body, which can hold secrets.
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


def _redact_escape(value) -> str:
    # Redact THEN escape every author-derived display string. Redaction is the
    # security boundary: an adapter that derives a field from frontmatter (e.g. a
    # title from a skill's `name:`) might not redact it, and these fields are
    # plain text that bypasses render_markdown_safe, so the output tripwire — by
    # design rendered-safe — would not catch a `&`/`<`-bearing value here.
    # Redacting centrally closes that bypass for every display field uniformly.
    return _html.escape(redact_text(value)[0] if isinstance(value, str) else "")


def _escape_text_fields(inv: dict, docs: dict, project: dict) -> None:
    # Redact + escape every author-derived plain-text display field so a secret
    # never reaches the island and hostile content (script tags, onerror,
    # </script>) can never reach it raw. The `html` field is already redacted
    # (its source markdown is redacted before render) and sanitized by
    # render_markdown_safe — leave it. `provider`/`typeLabel`/`displayName` are
    # NOT touched here because they are generator-controlled constants (adapter
    # ids and fixed labels), never author input. If a future adapter derives any
    # of them from frontmatter, add it to the pass below.
    for bucket in (inv, docs):
        for items in bucket.values():
            for it in items:
                for field in ("title", "summary"):
                    if field in it:
                        it[field] = _redact_escape(it[field])
                if "metadata" in it and isinstance(it["metadata"], dict):
                    escaped_meta = {}
                    for mk, mv in it["metadata"].items():
                        ek = _redact_escape(mk)
                        if isinstance(mv, str):
                            escaped_meta[ek] = _redact_escape(mv)
                        elif isinstance(mv, list):
                            escaped_meta[ek] = [_redact_escape(x) if isinstance(x, str) else x for x in mv]
                        else:
                            escaped_meta[ek] = mv
                    it["metadata"] = escaped_meta
                # Capture a capped, escaped body slice on the SAME pass so the
                # island stays uniformly escaped and the later _build_search reads
                # escaped fields (Phase 1 contract). Source: a raw body if the
                # adapter carries one, else the (now-escaped) summary. char-cap the
                # RAW source before escaping so the visible length, not the
                # entity-expanded one, is what _SEARCH_BODY_CHARS bounds.
                # `_rawBody` (inventory items: agent/skill/command/rule body) and
                # `_refScanBody` (docs: full clean markdown) are the two readable-
                # body sources, both already redacted at extraction. They feed BOTH
                # the search slice and the inline reading pane's `body` field, each
                # capped-then-escaped on this pass so the island stays uniform and
                # the reader gets redacted-then-escaped content (no render sink).
                raw = it.get("_rawBody") or it.get("_refScanBody")
                if isinstance(raw, str) and raw:
                    it["_searchBody"] = _redact_escape(raw[:_SEARCH_BODY_CHARS])
                    it["body"] = _redact_escape(raw[:_BODY_CHARS])
                    # Flag a capped body so the reading pane never hides content
                    # silently — it links out to the full file instead.
                    if len(raw) > _BODY_CHARS:
                        it["bodyTruncated"] = True
                else:
                    # no raw body: reuse the already-redacted+escaped summary slice
                    it["_searchBody"] = it.get("summary", "")
    project["title"] = _redact_escape(project.get("title", ""))
    for todo in project.get("openTodos", []):
        if "text" in todo:
            todo["text"] = _redact_escape(todo["text"])
        if "rawLine" in todo:
            todo["rawLine"] = _redact_escape(todo["rawLine"])


def _redact_paths(data: dict) -> None:
    # Paths are author-controlled — a filename can hold a secret-shaped string —
    # and reach the island for links without going through render_markdown_safe,
    # so the rendered-safe tripwire would not catch a `&`/`<`-bearing path. Redact
    # them after relationships have matched on the raw paths. A normal path never
    # matches a secret pattern, so links are unaffected; only a pathological
    # secret-named file is masked. IDs are sha256 of the raw path, so they never
    # leak it. Paths are textContent/URL-encoded by the renderer, so no escape.
    for bucket in (data["inventory"], data["docs"]):
        for items in bucket.values():
            for it in items:
                if isinstance(it.get("path"), str):
                    it["path"] = redact_text(it["path"])[0]
    for rec in data["search"]:
        if isinstance(rec.get("path"), str):
            rec["path"] = redact_text(rec["path"])[0]
    for edge in data["relationships"]:
        if isinstance(edge.get("evidence"), str):
            edge["evidence"] = redact_text(edge["evidence"])[0]
    for todo in data["project"].get("openTodos", []):
        if isinstance(todo.get("path"), str):
            todo["path"] = redact_text(todo["path"])[0]
    # source.repoName / dashboardPath / pathPrefix derive from the repo's own dir
    # and file names, which are author-controlled; sourceDigest is a hash and
    # vcs.kind a constant, so leave those.
    src = data.get("source", {})
    for key in ("repoName", "dashboardPath", "pathPrefix"):
        if isinstance(src.get(key), str):
            src[key] = redact_text(src[key])[0]


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


def _strip_bodies(data: dict) -> None:
    """Drop the per-item reading body — the multi-MB cost on a large repo."""
    for bucket in (data["inventory"], data["docs"]):
        for items in bucket.values():
            for it in items:
                if "body" in it:
                    it["body"] = ""
                if "html" in it:  # legacy guard: html is no longer emitted
                    it["html"] = ""


def _cap_summaries(data: dict, n: int) -> None:
    """Shorten (not blank) summaries to n codepoints, preserving the lead."""
    for bucket in (data["inventory"], data["docs"]):
        for items in bucket.values():
            for it in items:
                s = it.get("summary", "")
                if isinstance(s, str) and len(s) > n:
                    it["summary"] = s[:n]


def _blank_summaries(data: dict) -> None:
    for bucket in (data["inventory"], data["docs"]):
        for items in bucket.values():
            for it in items:
                if "summary" in it:
                    it["summary"] = ""


def _strip_search_body(data: dict) -> None:
    """Keep names + paths searchable; drop the per-record body slice."""
    data["search"] = [
        {"id": r["id"], "type": r["type"], "typeLabel": r["typeLabel"],
         "title": r["title"], "path": r["path"], "text": ""}
        for r in data["search"]
    ]


def _cap_reference_edges(data: dict) -> None:
    """Cap unbounded `reference` edges; `declares` is bounded so it is kept."""
    if "relationships" not in data:
        return
    declares = [e for e in data["relationships"] if e["type"] == "declares"]
    refs = [e for e in data["relationships"] if e["type"] == "reference"]
    if len(refs) > _MAX_DEGRADED_REFERENCE_EDGES:
        logger.warning("degraded mode: capping %d reference edges to %d",
                       len(refs), _MAX_DEGRADED_REFERENCE_EDGES)
        refs = refs[:_MAX_DEGRADED_REFERENCE_EDGES]
    data["relationships"] = sorted(
        declares + refs, key=lambda e: (e["from"], e["to"], e["type"]))


def _reduce_for_size(data: dict, measure) -> dict:
    """Graduated, biggest-cost-first trim; stop as soon as it is under budget.

    Deep-copy, then shed cost in a fixed deterministic order, re-measuring
    between steps so a repo that only slightly overflows keeps as much as it can
    (summaries, body search) instead of being blanked wholesale. `measure(d)`
    returns the rendered byte size of a candidate. Deep-copy-then-mutate
    preserves every key, so validate() and assert_no_secrets still pass.

    `generator.reducedSteps` records which steps fired so the banner can name
    exactly what was dropped. Reference edges are always capped in degraded mode
    (cheap, deterministic, independent of the byte budget).
    """
    reduced = copy.deepcopy(data)
    reduced["generator"]["truncated"] = True
    steps: list[str] = []
    _cap_reference_edges(reduced)

    def under_budget() -> bool:
        return measure(reduced) <= _TRUNCATE_BYTES

    # Step 1: drop the per-item reading body (the dominant cost).
    _strip_bodies(reduced)
    steps.append("bodies")
    if under_budget():
        reduced["generator"]["reducedSteps"] = steps
        return reduced
    # Step 2: cap (not blank) summaries.
    _cap_summaries(reduced, _TRUNCATED_SUMMARY_CHARS)
    steps.append("summaries-capped")
    if under_budget():
        reduced["generator"]["reducedSteps"] = steps
        return reduced
    # Step 3: drop the search body slice (names + paths stay searchable).
    _strip_search_body(reduced)
    steps.append("search-body")
    if under_budget():
        reduced["generator"]["reducedSteps"] = steps
        return reduced
    # Step 4 (last resort): blank summaries entirely.
    _blank_summaries(reduced)
    steps.append("summaries-blanked")
    reduced["generator"]["reducedSteps"] = steps
    return reduced


def generate(root: Path, out_dir: Path | None = None, owner: str | None = None,
             repo_name: str | None = None) -> Path:
    """Generate the dashboard and return its path (back-compat thin wrapper)."""
    return generate_result(root, out_dir, owner, repo_name).path


def _assemble(root: Path, out_dir: Path | None = None, owner: str | None = None,
              repo_name: str | None = None) -> tuple[dict, Path, int]:
    """Scan -> normalize -> redact -> validate into the island data dict.

    Returns (data, dashboard_path, scanned_file_count) WITHOUT rendering, writing,
    or creating directories. This is the read-only core shared by generate_result
    and `acc doctor`, so the doctor inspects exactly what the dashboard would show.
    """
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
    project["openTodos"].sort(key=lambda t: (t["path"], t.get("lineNumber", 0), t["text"]))
    parts.append(gpart)
    provider_summaries.append({"id": "generic", "displayName": "Generic",
                               "root": ".", "detected": True})

    inv, docs = _merge_parts(parts)
    _escape_text_fields(inv, docs, gpart["project"])  # escape titles/summaries for the island
    search = _build_search(inv, docs, project["openTodos"])
    relationships = _build_relationships(inv, docs)  # reads docs' _refScanBody
    # Drop the private slice keys so they never reach the serialized island.
    for bucket in (inv, docs):
        for items in bucket.values():
            for it in items:
                it.pop("_searchBody", None)
                it.pop("_refScanBody", None)
                it.pop("_rawBody", None)

    digest = source_digest(files, root)
    data = {
        "schemaVersion": SCHEMA_VERSION,
        "generator": {"name": "agent-context-center", "version": __version__,
                      "rendererDigest": "", "truncated": False},
        "source": {
            "repoName": _resolve_repo_name(root, repo_name),
            "pathPrefix": _path_prefix(root, out_dir),
            "dashboardPath": (
                dashboard.relative_to(root).as_posix()
                if dashboard.is_relative_to(root) else str(dashboard)
            ),
            "sourceDigest": digest,
            "vcs": {"kind": "none"},
        },
        "providers": provider_summaries,
        "project": gpart["project"],
        "inventory": inv,
        "docs": docs,
        "relationships": relationships,
        "search": search,
    }
    _redact_paths(data)
    validate(data)
    return data, dashboard, len(files)


def generate_result(root: Path, out_dir: Path | None = None,
                    owner: str | None = None,
                    repo_name: str | None = None) -> GenerateResult:
    data, dashboard, scanned = _assemble(root, out_dir, owner, repo_name)
    dashboard.parent.mkdir(parents=True, exist_ok=True)
    html = render_html(data)
    size = len(html.encode("utf-8"))
    truncated = False
    if size > _TRUNCATE_BYTES:
        truncated = True

        def _measure(candidate: dict) -> int:
            return len(render_html(candidate).encode("utf-8"))

        reduced = _reduce_for_size(data, _measure)
        validate(reduced)
        html = render_html(reduced)
        rsize = len(html.encode("utf-8"))
        logger.warning("dashboard %d bytes exceeds %d; reduced to %d bytes (steps: %s)",
                       size, _TRUNCATE_BYTES, rsize,
                       ",".join(reduced["generator"].get("reducedSteps", [])))
        if rsize > _TRUNCATE_BYTES:
            logger.warning("reduced dashboard still %d bytes (over budget)", rsize)
    elif size > _WARN_BYTES:
        logger.warning("dashboard %d bytes exceeds %d", size, _WARN_BYTES)
    dashboard.write_text(html, encoding="utf-8")
    return GenerateResult(
        path=dashboard,
        source_digest=data["source"]["sourceDigest"],
        scanned_file_count=scanned,
        providers=[p["id"] for p in data["providers"]],
        truncated=truncated,
    )
