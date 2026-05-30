# Phase 4b — Relationships (cross-references)

> Status: SPEC, hardened by a 5-lens adversarial design review (18 findings) and a Codex
> debate (gpt-5.5, run thread `019e7ad1`). Splits the "relationships" half out of the
> Phase 4 roadmap, after Phase 4a (Find) shipped and merged (PR #4, merge commit
> `e76c0df`). Ordered workflow chains, a multi-view router, and packaging stay in later
> phases.

Phase 3 shipped a deterministic single-file dashboard; Phase 4a turned the dead search
index into a global omnibox and built the reusable **id → row jump** infrastructure
(per-item ids, an `id → row` map, `jumpTo`).

The `relationships` field has been a required top-level key since Phase 1 (`schema.py`)
but has always shipped empty (`generate.py` sets `"relationships": []`). Phase 4b fills it
with deterministic edges and surfaces them two ways: an inline "Related" block on every
item/doc row, and a dedicated "Cross-references" view. It consumes 4a's jump infra rather
than building anything new for navigation.

## Decisions (locked)

1. **Two deterministic edge kinds only.** `reference` (a doc body mentions an inventory
   item's exact path) and `declares` (a provider config file → the MCP servers and hooks
   it declares). No inference, no scoring.
2. **Body-mentions-name is deferred.** Matching an item by its title/name (not its path)
   has a high false-positive rate and waits for a later slice.
3. **Reference matching is exact-path, boundary-checked, unique-path-only, and targets
   inventory items.** Match an inventory item's exact repo-relative path as a
   boundary-delimited token (not a bare substring), only for paths that resolve to exactly
   one id, and never the four provider config files. Docs are reference **sources**, not
   targets (doc→doc graphing is deferred). Shared config paths are excluded — they are the
   `declares` channel.
4. **`declares` source = a config-file node, not an instruction doc.** A `.claude/settings.json`,
   `.mcp.json`, `.codex/config.toml`, or `.cursor/mcp.json` is the thing that declares an
   MCP server or hook, so it is the edge source — not `CLAUDE.md`. Config-file nodes are
   synthetic: they appear as Cross-references source-group headers and as an inline
   "declared in" label, but they are **not** inventory rows and are not jump targets. This
   gives correct provenance and covers cursor (which has MCP servers but no instruction
   doc).
5. **`declares` targets = MCP servers and hooks only.** Commands are file-discovered
   (`.claude/commands/*.md`, `.codex/prompts/*.md`), not config declarations, so they are
   out of `declares`.
6. **Evidence is a generator-controlled path, not author text.** `evidence` is the
   salient path of the edge (the referenced item path for `reference`, the config file
   path for `declares`). It carries no doc-body text, so relationships hold no
   author-derived content and need no `html.escape` / `htmlUnescape`; like every other
   path field it reaches the DOM via `textContent` and is inert.
7. **textContent only.** Edges render through `el()` / `textContent`; no new
   `innerHTML` / `outerHTML` / `insertAdjacentHTML`. The CI guard still holds.
8. **Jump controls are not rows.** Inline Related entries and Cross-references endpoints
   are real `<button type="button">` / `<a href="#…">` controls with keyboard behavior,
   but they are **not** `.acc-item` and carry **no** `data-id`. The `.acc-item[data-id]`
   namespace stays reserved for the one canonical row per id, so `buildRowIndex` resolves
   each id to its real row, never to a jump control.
9. **Edges are stored directed, rendered bidirectionally.** One stored edge (`from → to`)
   shows on both endpoints with a direction-aware verb (where both endpoints have a row).
10. **The view is "Cross-references," grouped by source, display-sorted by path/title.**
    Ordered chains ("Workflows") stay deferred, so the name avoids implying sequence.

## Scope

- `generate.py`: a new `_build_relationships(inv, docs)` that emits the edge list and the
  synthetic config-file nodes; wire it into `data["relationships"]`. Adapters carry a
  private `_refScanBody` on each doc so the reference scan sees full doc text **without**
  disturbing the search slice; drop it (and `_searchBody`) before serialization.
  `_reduce_for_size` keeps `declares` edges and caps `reference` edges.
- `schema.py`: validate the edge shape, the `type` enum, and type-aware referential
  integrity.
- `app.js`: build an `id → edges` adjacency index and an `id → {title, typeLabel, path}`
  label map from canonical inventory/docs/todos; render an inline "Related" block per row;
  add `renderCrossReferences()`; wire the nav anchor and an Overview card; pin the init
  sequence.
- `dashboard.html.tmpl`: a `#crossref` section and its nav anchor.
- `styles.css`: `.acc-related` and Cross-references styles.

## Non-goals (Phase 4b)

- Body-mentions-name edges (deferred, decision 2).
- doc → doc references and a general documentation graph (decision 3); revisit with its
  own filtering and budget.
- Markdown-link destination resolution (`./x.md`, `/x.md`, URL-encoded, sibling-relative).
  Reference matching is exact repo-relative path only this slice; relative-link recall is
  a later enhancement.
- Commands in `declares` (decision 5); a `provides`/`contains` edge kind is a later slice.
- Inventory-item bodies as reference **sources**. Only doc bodies are scanned. Codex
  prompt commands (`.codex/prompts/*.md`) carry markdown bodies but live in
  `inventory["commands"]`; promoting all body-bearing command artifacts to reference
  sources is deferred (and should be provider-agnostic, not codex-only).
- The two latent Phase 3 items (`markdown.py` `_safe_link` attribute-escaping,
  `render.py` `__SCHEMA_VERSION__` ordering) stay deferred — 4b routes no `doc.html`
  through `innerHTML`.

## Data contract (changes)

`relationships` grows from `[]` to a sorted, deduped list of directed edges:

```
{ "from": "<id>", "to": "<id>", "type": "reference" | "declares", "evidence": "<path>" }
```

- `from` / `to` / `type` / `evidence` are all generator-controlled. `from` is a doc id
  (`reference`) or a synthetic config-node id (`declares`); `to` is an inventory item id.
- `evidence` is the salient path: the referenced item's canonical path (`reference`) or
  the config file path (`declares`). It is treated like every other path field — not
  escaped, displayed via `textContent`. No author-derived text enters `relationships`.
- **`SCHEMA_VERSION` stays `"1.0"`.** This is a compatible population of an
  already-required field plus stricter validation, not a breaking shape change; no
  external consumer reads the island independently of the renderer shipped with it.
- **Order and dedup.** Dedup on `(from, to, type)`; sort the stored list on
  `(from, to, type)`. ids are hashes, so this order is deterministic but not
  human-meaningful — the **renderer** display-sorts by path/title (see Rendering).
  `render.py`'s `json.dumps(sort_keys=True)` fixes dict-key order but not list order, so
  the explicit sort is load-bearing (same as `_build_search`).

### Reference matching (the precise part)

- **Build `path → set(ids)`** over inventory items only (docs are sources, not targets),
  iterating a deterministically sorted item list (`_merge_parts` already sorts each bucket
  by `(path, title, id)`; concatenate buckets in a fixed order). Keep a path only if
  `len(ids) == 1` — never first-wins. A path on two or more ids is dropped.
- **Exclude the provider config paths** (`.claude/settings.json`, `.mcp.json`,
  `.codex/config.toml`, `.cursor/mcp.json`) from the lookup regardless of id count. They
  are the `declares` channel; otherwise a single-server config (one id) would become a
  unique reference target and produce a stray `reference` edge alongside its `declares`.
- **Boundary match, not bare substring.** For each doc, scan its `_refScanBody` for each
  remaining unique path with
  `re.compile(r'(?<![\w./-])' + re.escape(path) + r'(?![\w./-])')`. A bare `path in body`
  produces phantom edges: `.claude/agents/x.md` matches inside `.claude/agents/x.md.bak`,
  and a short generic doc `API.md` matches inside `legacy_API.md.old` or prose. The
  boundary rule rejects a hit unless the chars on both sides are not path-continuation
  characters (`[\w./-]`) or string ends. A markdown link `[x](.claude/agents/x.md)` still
  matches because the path appears as a delimited token.
- On a match, emit `{from: doc.id, to: item.id, type: "reference", evidence: item.path}`.
  Skip self-edges (`from == to`) defensively. Repeated mentions collapse to one edge
  (dedup on the triple); evidence is the item's canonical path, so it is fixed regardless
  of which occurrence matched.

### `declares` (config-file nodes)

- Group inventory items of type `mcpServer` and `hook` by their `path` (which is always
  the declaring config file). Each distinct such path is a **config-file node** with a
  deterministic synthetic id: `stable_id("config", "configFile", config_path, "")`.
- For each config-file node, emit `{from: node.id, to: item.id, type: "declares",
  evidence: config_path}` for every MCP/hook item with that path.
- This covers all providers including cursor (`.cursor/mcp.json` → its MCP items), with
  correct provenance, and adds no inventory rows.

### `_refScanBody` lifecycle (and why not `_rawBody`)

Docs persist only `summary` + `html` today, so the reference scan needs the full text.
**It must not reuse the `_rawBody` key.** `_escape_text_fields` (generate.py:166-168)
already promotes any `_rawBody` into the search slice `_searchBody` for both inventory and
docs; no adapter sets it today, so docs fall back to the summary. Setting `doc["_rawBody"]`
would silently flip every doc's search slice to a body slice and break the
`_SEARCH_BODY_CHARS` budget math.

So the `claude`, `codex`, and `generic` adapters set `doc["_refScanBody"] = clean` (the
redacted raw markdown they already compute; cursor indexes no docs). The doc search slice
is unchanged. `_build_relationships` reads `_refScanBody`; `generate()` then pops it and
`_searchBody` from inventory and docs before assembling `data`.

**Pinned order** (`_refScanBody` is redacted but unescaped full markdown — leaving it on a
doc would dump whole bodies into the island and blow the budget):

```
_merge_parts → _escape_text_fields → _build_search →
_build_relationships(reads _refScanBody) →
pop _searchBody and _refScanBody from inventory + docs →
assemble data → validate(data) → render_html
```

`data["docs"]` aliases the same dict objects the pop loop mutates, so popping before
assembly is sufficient; an acceptance test asserts neither `_refScanBody` nor `_rawBody`
appears in the rendered HTML.

### Reference scanning runs over the redacted body

`_refScanBody = clean` is post-`redact_text`. A doc line like `see token:
.claude/agents/x.md` redacts to `see [redacted]`, so that path reference is dropped. This
is an **accepted false negative** (rare; a path immediately after a secret keyword), kept
for defense-in-depth: even with path-only evidence, scanning the redacted body means a
mis-ordered pop can never leak a secret. A unit test pins it.

## Rendering model

- **Adjacency + labels.** Build once from `data.relationships`:
  `edgesByEndpoint: id → [{ otherId, dir, type, evidence }]` (`dir` is `out` on the `from`
  side, `in` on the `to` side), and `metaById: id → { title, typeLabel, path }` built from
  the **canonical** `inventory` / `docs` / `todos` (not from `search`, so labels do not
  depend on the search index's light-mode behavior; doc labels synthesize `typeLabel` from
  the bucket via the existing `doc_type_label`). Config-file node ids are not in
  `metaById`; their label is the config path carried in the edge `evidence`.
- **Inline "Related."** After a row renders, append an `.acc-related` block listing its
  edges. Each entry is a real `<button type="button">` (or `<a href="#…">`) with keyboard
  activation that calls `jumpTo(otherId)` — the target id lives in the handler closure (or
  a `data-jump` attribute), **never** as `data-id` on an `.acc-item`. A `declares` edge
  shown on an item renders "declared in `<evidence path>`" as a plain label (the config
  node has no row to jump to). Verbs: `declares` in → "declared in", `reference` out →
  "references", `reference` in → "referenced by".
- **Cross-references view.** A `#crossref` section with `renderCrossReferences()`. Grouped
  by source: each source listed once (a doc, labeled from `metaById`; or a config file,
  labeled by its path), its outgoing edges indented beneath, each item endpoint a
  non-indexed jump control. **Display order:** sort source groups and the targets within
  them by `(path, title)` — never by the hash-id storage order. An Overview card links to
  it with an edge count.

```
Cross-references (12)

.claude/settings.json  [config]
  → declares     MCP server  github         (.claude/settings.json)
  → declares     Hook        PreToolUse     (.claude/settings.json)

CLAUDE.md  [doc]
  → references   Agent       code-reviewer  (.claude/agents/code-reviewer.md)

.cursor/mcp.json  [config]
  → declares     MCP server  context7       (.cursor/mcp.json)
```

- **Init sequence (pinned).** Render the canonical rows (inventory, docs, todos) and
  append each row's inline Related block during those passes; call `buildRowIndex()`
  exactly once after all canonical rows are in the DOM; then `renderCrossReferences()`
  (its controls are non-indexed, so order relative to `buildRowIndex` is safe); then wire
  interactions. `buildRowIndex` indexes only `.acc-item[data-id]` canonical rows.
- **Empty state.** No edges → the Cross-references section renders a one-line "No
  cross-references found" note; rows with no edges render no Related block.
- **Degraded mode.** `_reduce_for_size` keeps every `declares` edge (bounded by the
  MCP+hook count) and caps `reference` edges to the first `_MAX_DEGRADED_REFERENCE_EDGES`
  (default 200) by the deterministic `(from, to, type)` sort, dropping the rest and
  logging the count. Related and Cross-references still render and jump, because labels
  come from `metaById` (canonical, retained).

## Architecture

- `generate.py`
  - `_build_relationships(inv, docs) -> list[dict]` — the reference pass (sorted
    `path → set(ids)` over inventory items, uniqueness + config-path exclusion, boundary
    regex over each doc's `_refScanBody`) and the `declares` pass (config-file nodes over
    MCP/hook item paths). Dedup and sort on `(from, to, type)`.
  - wire `data["relationships"] = _build_relationships(inv, docs)`; pop `_searchBody` and
    `_refScanBody` after this call and before data assembly, per the pinned order.
  - `_reduce_for_size` — keep `declares`, cap `reference` to `_MAX_DEGRADED_REFERENCE_EDGES`.
- adapters/`claude.py`, `codex.py`, `generic.py` — set `_refScanBody = clean` on each doc.
  (No `provider` tag on docs is needed — `declares` no longer uses instruction docs.)
- `schema.py` — `_validate_relationships(edges, item_ids, doc_ids, config_node_ids)`:
  each edge has `{from, to, type, evidence}` as strings; `type in {reference, declares}`;
  `to in item_ids` always; `reference` `from in doc_ids`; `declares` `from in
  config_node_ids` (the set the builder derives from MCP/hook item paths). All sets are
  built from the data object so the call works identically on full and reduced data.
- `app.js` — `edgesByEndpoint` + `metaById` (from canonical sources); the inline Related
  pass (real buttons/anchors, non-indexed); `renderCrossReferences()` (source-grouped,
  path/title display-sort); the pinned init sequence; nav + Overview card. Reuse `el`,
  `jumpTo`.
- `dashboard.html.tmpl` / `styles.css` — `#crossref` section + nav anchor; `.acc-related`
  and Cross-references styles.

## Acceptance criteria

- A doc that contains an inventory item's exact path (as a delimited token) produces
  exactly one `reference` edge, even if the path appears several times; the item's row
  shows "referenced by" and the doc's row shows "references."
- `.claude/agents/x.md.bak`, or `API.md` inside `legacy_API.md.old`, produces **no** edge
  (boundary rule). `see token: .claude/agents/x.md` produces **no** edge (redaction) —
  pinned, accepted behavior. A doc citing another doc's path produces **no** edge
  (inventory-only targets).
- Each provider config file shows `declares` edges to its MCP servers and hooks, sourced
  from the **config file** node (not `CLAUDE.md`). A cursor repo's `.cursor/mcp.json`
  declares its MCP servers. No `declares` edge targets a command.
- Clicking any Related entry or any Cross-references item endpoint scrolls the **canonical**
  row for that id into view and flashes it (jump controls never shadow canonical rows; a
  `declares` config source is a label, not a jump target).
- Related entries and Cross-references endpoints are keyboard-activable controls
  (`<button>` / `<a>`), and the Cross-references view is display-sorted by path/title.
- `grep -nE 'innerHTML|outerHTML|insertAdjacentHTML' app.js` returns nothing.
- Output is byte-identical across repeated runs; the doc search slice is unchanged from
  4a; under the size budget; in degraded mode `declares` edges all survive and `reference`
  edges are capped deterministically.
- Neither `_refScanBody` nor `_rawBody` appears in the rendered HTML.
- Schema rejects an edge with a dangling `to` (not an item id), a `reference` `from` that
  is not a doc id, a `declares` `from` that is not a config-node id, an unknown `type`, or
  a non-string field.

## Testing

- Unit (`_build_relationships`):
  - reference dedup across repeated mentions; boundary rejection of `.md`-inside-`.md.bak`
    and filename-in-prose; the `path → set(ids)` uniqueness filter (a path on one item
    after iterating other buckets still matches; a path on two items matches nothing); the
    four config-path exclusions; docs are not reference targets; redaction false-negative
    (`token: <path>` → no edge).
  - `declares`: config-file node → its MCP/hook items; one node per distinct config path;
    cursor `.cursor/mcp.json` declares its MCP; no command is a `declares` target; the
    synthetic node id is deterministic.
  - deterministic sort; full edge list byte-identical across runs.
- Unit (`_refScanBody`): set on docs by the adapters, read by the builder, absent from the
  serialized island; the doc search slice (`_searchBody`) is unchanged vs. 4a.
- Schema: dangling `to`, wrong-kind `from`, bad `type`, non-string field each rejected;
  sets built from the data object; valid edges pass on full and reduced data.
- Unit (`_reduce_for_size`): `declares` retained, `reference` capped at
  `_MAX_DEGRADED_REFERENCE_EDGES`, re-validates under budget.
- Playwright DOM (`page.set_content`): bidirectional Related with correct verbs and
  keyboard activation; clicking Related / a Cross-references item endpoint jumps to and
  flashes the **canonical** row (not a jump control); a `declares` source renders as a
  label; the Cross-references view groups by source and display-sorts by path/title;
  degraded/light mode still renders Related and Cross-references; the init sequence leaves
  `buildRowIndex` indexing only canonical rows.
- CI guard: `app.js` stays free of `innerHTML` / `outerHTML` / `insertAdjacentHTML`.

## File-by-file plan

- `src/acc/generate.py` — `_build_relationships` (reference + config-file-node `declares`);
  wire `relationships`; the pinned pop-before-assembly order; `_reduce_for_size` reference
  cap; `_MAX_DEGRADED_REFERENCE_EDGES`.
- `src/acc/adapters/claude.py`, `codex.py`, `generic.py` — `_refScanBody = clean` on docs.
- `src/acc/schema.py` — `_validate_relationships` (shape, enum, type-aware referential
  integrity); endpoint id sets from the data object.
- `src/acc/templates/app.js` — adjacency + `metaById` from canonical sources; inline
  Related (non-indexed buttons/anchors); Cross-references view (source-grouped, path/title
  sort); pinned init sequence; nav + Overview card.
- `src/acc/templates/dashboard.html.tmpl` — `#crossref` section + nav anchor.
- `src/acc/templates/styles.css` — Related + Cross-references styles.
- `tests/` — unit + schema + Playwright DOM + the existing innerHTML guard.

## Reusable infra consumed from Phase 4a

- Per-row `id` + the `id → row` map + `jumpTo` → inline Related links and Cross-references
  item endpoints jump with the existing mechanism (and never pollute the index — decision 8).
- `type` / `typeLabel` + `doc_type_label` → the `metaById` label map for edge endpoints.

## Open questions (resolved in the Codex debate — listed for the record)

1. **`reference` evidence** — resolved to the matched path string (not a context snippet):
   simpler, no redaction/window/escape risk, and the edge already proves the connection.
2. **`declares` source** — resolved to config-file nodes (not the instruction-doc hub):
   correct provenance and cursor coverage.
3. **`declares` set** — resolved to MCP/hook only; commands are file-discovered.
4. **reference targets** — resolved to inventory items only; doc→doc deferred.
5. **redaction** — resolved to scan the redacted body, accept the rare false negative
   (defense-in-depth).
6. **codex prompt commands as reference sources** — deferred (Non-goal); promote all
   body-bearing command artifacts together later, provider-agnostic.

## Out of scope → later phases

- Body-mentions-name edges; doc→doc references; markdown relative-link resolution.
- Reference sources beyond doc bodies (command artifacts), provider-agnostic.
- Commands as `declares`/`provides` targets; ordered workflow chains; a multi-view router.
- Packaging (`/dashboard`, refresh tiers, plugin); latent Phase 3 hardening.

## Review provenance

5-lens adversarial design review (XSS / island safety, determinism, reference false
positives, jump / render correctness, schema / referential integrity), source-grounded;
run `wf_244234f2-95e`. 18 findings; verification interrupted at session suspend, so
findings were adjudicated against ground-truth source. Folded in: distinct `_refScanBody`;
boundary-checked path match; non-indexed jump controls; `path → set(ids)` uniqueness;
config-path exclusion; redacted-body scan; pinned pop-before-serialize order and init
sequence.

Codex debate (gpt-5.5 / xhigh, read-only, thread `019e7ad1`), verdict needs-rework, all
claims re-verified against source. Accepted and folded in: `declares` re-sourced from
config-file nodes instead of instruction-doc hubs (false provenance + dropped cursor);
commands removed from `declares` (file-discovered, not config-declared); reference targets
narrowed to inventory items (doc→doc deferred); `reference` evidence simplified to the
matched path (snippet machinery removed); a deterministic `reference` cap in degraded mode;
Cross-references display-sorted by path/title rather than hash id; `metaById` built from
canonical sources; Related controls specified as real buttons/anchors; the leftover
`body.find` wording removed; `SCHEMA_VERSION` documented as a compatible population.
Deferred against the debate: markdown relative-link resolution (kept exact-path for v1) and
a target-grouped Cross-references section (the bidirectional inline Related already answers
"what references this item").

# (end of spec)
