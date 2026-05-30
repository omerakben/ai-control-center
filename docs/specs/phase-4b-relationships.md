# Phase 4b — Relationships (cross-references)

> Status: SPEC, hardened by a multi-agent adversarial design review (5 lenses, 18
> findings — see "Review provenance"). Splits the "relationships" half out of the Phase 4
> roadmap, after Phase 4a (Find) shipped and merged (PR #4, merge commit `e76c0df`).
> Ordered workflow chains, a multi-view router, and packaging stay in later phases. A
> Codex debate runs before planning.

Phase 3 shipped a deterministic single-file dashboard; Phase 4a turned the dead search
index into a global omnibox and built the reusable **id → row jump** infrastructure
(per-item ids, an `id → row` map, `jumpTo`, the `htmlUnescape`-at-display pattern).

The `relationships` field has been a required top-level key since Phase 1 (`schema.py`)
but has always shipped empty (`generate.py` sets `"relationships": []`). Phase 4b fills it
with deterministic edges and surfaces them two ways: an inline "Related" block on every
item/doc row, and a dedicated "Cross-references" view. It consumes 4a's jump infra rather
than building anything new for navigation.

## Decisions (locked)

1. **Two deterministic edge kinds only.** `reference` (a doc body mentions an item or
   doc's exact path) and `declares` (a provider's instruction doc → the MCP servers,
   hooks, and commands that provider's config declares). No inference, no scoring.
2. **Body-mentions-name is deferred.** Matching an item by its title/name (not its path)
   has a high false-positive rate and waits for a later slice.
3. **Reference matching is exact-path, boundary-checked, unique-path-only.** Match an
   item/doc's exact repo-relative path as a **boundary-delimited** token (not a bare
   substring), and only for paths that resolve to exactly one id. Shared config paths
   (every hook and MCP server in `.claude/settings.json`) and the four provider config
   files are excluded from `reference` matching — they are the `declares` channel.
4. **Structural source = the provider instruction-doc hub, attributed by a tagged
   `provider` field.** `declares` edges run from a provider's `CLAUDE.md` / `AGENTS.md`
   doc to that provider's config-declared items. The adapters tag their instruction docs
   with `provider`; hub selection never relies on a path-suffix scan of the merged doc
   bucket. Providers with no instruction doc (cursor; or a repo with `.claude/settings.json`
   but no `CLAUDE.md`) produce no `declares` edges — a documented gap, not an error.
5. **textContent only.** Edges render through `el()` / `textContent`; no new
   `innerHTML` / `outerHTML` / `insertAdjacentHTML`. The CI guard still holds.
6. **Jump controls are not rows.** Inline Related entries and Cross-references endpoints
   are clickable, but they are **not** `.acc-item` and carry **no** `data-id`. The
   `.acc-item[data-id]` namespace stays reserved for the one canonical row per id, so
   `buildRowIndex` resolves each id to its real row, never to a jump control.
7. **Edges are stored directed, rendered bidirectionally.** One stored edge (`from → to`)
   shows on both endpoints' rows with a direction-aware verb.
8. **The view is named "Cross-references," laid out grouped by source.** Ordered chains
   ("Workflows") stay deferred, so the name avoids implying sequence.

## Scope

- `generate.py`: a new `_build_relationships(inv, docs)` that emits the edge list; wire it
  into `data["relationships"]`. Adapters carry a private `_refScanBody` on each doc so the
  reference scan sees full doc text **without** disturbing the search slice; drop it (and
  `_searchBody`) before serialization. `_reduce_for_size` keeps edges but blanks
  `evidence`.
- `schema.py`: validate the edge shape, the `type` enum, and referential integrity
  (every `from` / `to` resolves to a known id, computed as a set from the data object).
- `app.js`: build an `id → edges` adjacency index and an `id → {title, typeLabel}` label
  map; render an inline "Related" block per row; add `renderCrossReferences()`; wire the
  nav anchor and an Overview card; pin the init sequence.
- `dashboard.html.tmpl`: a `#crossref` section and its nav anchor.
- `styles.css`: `.acc-related` and Cross-references styles.

## Non-goals (Phase 4b)

- Body-mentions-name edges (deferred, decision 2).
- Ordered workflow chains and a multi-view sidebar router.
- `declares` edges from agents / skills / rules. The locked kind list is MCP / hook /
  command; agents and skills are reachable as `reference` targets when a doc cites them.
- **Inventory-item bodies as reference sources.** Only **doc** bodies are scanned for path
  references. Codex prompt commands (`.codex/prompts/*.md`) carry markdown bodies but live
  in `inventory["commands"]`, not `docs` — a prompt that cites another item produces no
  `reference` edge in this slice. Extending reference sources to body-bearing inventory
  items is deferred.
- New endpoint node types. Config files are not promoted to addressable nodes (the
  rejected "config-file nodes" alternative); the provider instruction doc is the hub.
- The two latent Phase 3 items (`markdown.py` `_safe_link` attribute-escaping,
  `render.py` `__SCHEMA_VERSION__` ordering) stay deferred — 4b routes no `doc.html`
  through `innerHTML`.

## Data contract (changes)

`relationships` grows from `[]` to a sorted, deduped list of directed edges:

```
{ "from": "<id>", "to": "<id>", "type": "reference" | "declares", "evidence": "<escaped>" }
```

- `from` / `to` are existing stable ids — the same ids `jumpTo` resolves. `from` is the
  doc for both kinds (the referencing doc, or the instruction-doc hub); `to` is the
  referenced item/doc, or the declared item.
- `type` is a generator-controlled constant (`reference` or `declares`), so it is **not**
  escaped, matching the `provider` / `typeLabel` convention.
- `evidence` is the only author-derived field, so it is html-escaped at build (Phase 1
  contract) and `htmlUnescape`-d at display (the 4a pattern):
  - For `reference`: a capped, escaped **context snippet** of the doc body around the
    matched path. The snippet is cut from the redacted scan body on **codepoint**
    boundaries — `start = max(0, idx - _EVIDENCE_BEFORE)`, `end = min(len, idx +
    len(path) + _EVIDENCE_AFTER)` where `idx` is the start of the **first boundary-valid
    match** (the regex match start, not a bare `body.find` that could point at an earlier
    non-boundary occurrence inside e.g. `x.md.bak`) — and then `_html.escape`-d. **Slice raw, then escape** (never escape-then-slice), so a
    window edge can never bisect an entity like `&amp;`. `_EVIDENCE_BEFORE = 40`,
    `_EVIDENCE_AFTER = 80` (named constants, codepoint-based, mirroring
    `_SEARCH_BODY_CHARS`).
    > Refinement note: the brainstorm presented `reference` evidence as "the matched path
    > string." A path is generator-controlled and would make "escape evidence" a no-op, so
    > this spec sharpens it to an author-derived snippet — which is what the locked "escape
    > evidence" / `htmlUnescape`-at-display requirement was for. Open to reverting to
    > path-only at spec review.
  - For `declares`: the declaring config file path (`.claude/settings.json`, `.mcp.json`,
    `.codex/config.toml`, `.cursor/mcp.json`). Generator-controlled, but escaped on the
    same pass for a uniform display path.
- **Order and dedup.** Dedup on `(from, to, type)`; sort on `(from, to, type)`. `evidence`
  is not in the key, so it must be pinned deterministically by construction: a reference
  edge always takes its snippet from the first boundary-valid match (lowest match start in
  document order), so a repeated path collapses to one edge with one fixed snippet. `render.py`'s
  `json.dumps(sort_keys=True)` fixes dict-key order but not list order, so the explicit
  sort is load-bearing (same as `_build_search`).

### Reference matching (the precise part)

- **Build `path → set(ids)`** over inventory items **and** docs, iterating a
  deterministically sorted item list (`_merge_parts` already sorts each bucket by
  `(path, title, id)`; concatenate buckets in a fixed order). Keep a path in the lookup
  only if `len(ids) == 1` — never first-wins. A path on two or more ids (shared config
  files, accidental duplicates) is dropped.
- **Exclude the provider config paths** (`.claude/settings.json`, `.mcp.json`,
  `.codex/config.toml`, `.cursor/mcp.json`) from the reference lookup **regardless** of
  how many ids they map to. They are the `declares` channel; otherwise a single-server
  config (one id) would become a unique reference target and a hub doc citing it would
  emit both a `declares` and a `reference` edge to the same server.
- **Boundary match, not bare substring.** For each doc, scan its `_refScanBody` for each
  remaining unique path with `re.compile(r'(?<![\w./-])' + re.escape(path) + r'(?![\w./-])')`.
  A bare `path in body` produces phantom edges: `.claude/agents/x.md` matches inside
  `.claude/agents/x.md.bak`, and a short generic doc `API.md` matches inside
  `legacy_API.md.old` or ordinary prose. The boundary rule rejects a hit unless the chars
  on both sides are not path-continuation characters (`[\w./-]`) or string ends. A
  markdown link `[x](.claude/agents/x.md)` still matches because the path appears as a
  delimited token.
- Skip self-edges (`from == to`) defensively.
- The doc body never enters `relationships` except as the capped, escaped snippet. The
  path being matched is generator-controlled, so a hostile body cannot inject an id.

### `_refScanBody` lifecycle (and why not `_rawBody`)

Docs persist only `summary` + `html` today, so the reference scan needs the full text.
**It must not reuse the `_rawBody` key.** `_escape_text_fields` (generate.py:166-168)
already has a live consumer: when an item carries `_rawBody`, it builds `_searchBody` from
`html.escape(raw[:_SEARCH_BODY_CHARS])` instead of the summary, for **both** inventory and
docs. No adapter sets `_rawBody` today, so docs fall back to the summary slice. Setting
`doc["_rawBody"]` in 4b would silently flip every doc's search slice to a 200-char body
slice and invalidate the `_SEARCH_BODY_CHARS` budget math — an unbudgeted search change 4b
never intends.

So the `claude`, `codex`, and `generic` adapters set `doc["_refScanBody"] = clean` (the
redacted raw markdown they already compute; cursor indexes no docs). The doc search slice
is unchanged. `_build_relationships` reads `_refScanBody`; `generate()` then pops it
**and** `_searchBody` from inventory and docs before assembling `data`.

**Pinned order** (the pop must precede serialization, because `_refScanBody` is redacted
but **unescaped** full markdown — leaving it on a doc dumps whole bodies into the
JSON-in-`<script>` island and blows the size budget):

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

`_refScanBody = clean` is post-`redact_text`. `redact_text` replaces a `keyword: value`
or url-with-creds match with `[redacted]`, so a doc line like `see token:
.claude/agents/x.md` becomes `see [redacted]` and that path reference is dropped. This is
an **accepted false negative**: a path immediately following a secret-keyword is rare, and
scanning the redacted body guarantees no secret can leak into an evidence snippet. A unit
test pins this behavior. (The alternative — scan the raw body, build evidence from the
redacted body — is logged as an open question for the Codex debate.)

### Structural `declares` (the hub rule)

- The `claude` and `codex` adapters **tag their instruction docs with `provider`** (mirror
  `make_item`): claude on `CLAUDE.md` / `.claude/**/CLAUDE.md`, codex on `AGENTS.md` /
  `.codex/**/AGENTS.md`. `_build_relationships` selects hub candidates by
  `doc.get("provider")`, never by a path-suffix test — so a generic, unclaimed
  `vendor/CLAUDE.md` (indexed by `GenericAdapter` into the same `docs["references"]`
  bucket, untagged) can never be mistaken for a hub.
- The hub for a provider is: the root marker doc (`CLAUDE.md` / `AGENTS.md`, `path` equal
  to the marker) when present; otherwise the tagged instruction doc with the smallest
  `(path, id)`. Total and tie-free.
- For each inventory item with `provider == hub provider` and
  `type in {mcpServer, hook, command}`, emit `{from: hub.id, to: item.id, type:
  "declares", evidence: item.path}`.
- No hub for a provider → no `declares` edges for it (cursor always; claude/codex when the
  instruction doc is absent).

## Rendering model

- **Adjacency + labels.** Build once from `data.relationships`:
  `edgesByEndpoint: id → [{ otherId, dir, type, evidence }]` (`dir` is `out` on the `from`
  side, `in` on the `to` side), and `metaById: id → { title, typeLabel }` sourced from the
  search records. The label map lets a Related entry name its target even when the target
  row is in a collapsed or empty bucket.
- **Inline "Related."** After a row renders, append an `.acc-related` block listing its
  edges. Each entry is a clickable control that calls `jumpTo(otherId)` — the target id
  lives in the handler closure (or a `data-jump` attribute), **never** as `data-id` on an
  `.acc-item`. Labeled with a direction-aware verb, the target's type chip, and the
  `htmlUnescape`-d target title (titles in `metaById` come from the escaped search
  records, so they are decoded at display exactly like `itemRow` and `evidence`).
  `evidence` shows as muted, `htmlUnescape`-d text. Verbs: `declares` out → "declares",
  `declares` in → "declared by", `reference` out → "references", `reference` in →
  "referenced by".
- **Cross-references view.** A `#crossref` section with `renderCrossReferences()`. Layout
  is grouped by source: each source row (a doc) listed once, its outgoing edges indented
  beneath, every endpoint a non-indexed jump control. An Overview card links to it with an
  edge count.

```
Cross-references (12)

CLAUDE.md  [doc]
  → declares     MCP server  github         (.claude/settings.json)
  → declares     Hook        PreToolUse     (.claude/settings.json)
  → references   Agent       code-reviewer  (.claude/agents/code-reviewer.md)

AGENTS.md  [doc]
  → declares     MCP server  context7       (.codex/config.toml)
```

- **Init sequence (pinned).** Render the canonical rows (inventory, docs, todos) and append
  each row's inline Related block during those passes; call `buildRowIndex()` exactly once
  after all canonical rows are in the DOM; then `renderCrossReferences()` (its controls are
  non-indexed, so order relative to `buildRowIndex` is safe); then wire interactions.
  `buildRowIndex` indexes only `.acc-item[data-id]` canonical rows.
- **Empty state.** No edges → the Cross-references section renders a one-line "No
  cross-references found" note; rows with no edges render no Related block (not an empty
  one).
- **Degraded mode.** `_reduce_for_size` keeps the edge list (ids + type are tiny) but
  blanks `evidence`. Related and Cross-references still render and jump, because labels
  come from the retained light search index, not from `evidence`.

## Architecture

- `generate.py`
  - `_build_relationships(inv, docs) -> list[dict]` — the reference pass (sorted
    `path → set(ids)` lookup with the uniqueness + config-path exclusion, boundary regex
    over each doc's `_refScanBody`, `body.find` snippet evidence) and the `declares` pass
    (provider-tagged hub resolution + config-declared items). Dedup and sort on
    `(from, to, type)`.
  - wire `data["relationships"] = _build_relationships(inv, docs)`; move the `_searchBody`
    pop to after this call and pop `_refScanBody` in the same loop; keep the pop before
    data assembly per the pinned order.
  - `_reduce_for_size` — blank `evidence` on each retained edge.
- adapters/`claude.py`, `codex.py`, `generic.py` — set `_refScanBody = clean` on each doc
  dict; `claude.py` / `codex.py` also set `provider` on their instruction docs.
- `schema.py` — `_validate_relationships(edges, known_ids)`: each edge has
  `{from, to, type, evidence}` as strings; `type in {reference, declares}`; `from` / `to`
  in `known_ids`. `validate()` computes `known_ids` as a **set** from the data object it
  is validating — `data["inventory"]` item ids ∪ `data["docs"]` ids ∪
  `data["project"]["openTodos"]` ids — so the call works identically on the full and the
  reduced data (reduction keeps all ids). Todos stay in `known_ids` only so a hand-authored
  edge naming a todo validates rather than crashes; 4b never emits a todo edge (reference
  targets are items + docs, declares targets are items).
- `app.js` — `edgesByEndpoint` + `metaById`; the inline Related pass; `renderCrossReferences()`;
  nav wiring; the Overview card; the pinned init sequence. Reuse `el`, `htmlUnescape`,
  `jumpTo`.
- `dashboard.html.tmpl` / `styles.css` — `#crossref` section + nav anchor; `.acc-related`
  and Cross-references styles.

## Acceptance criteria

- A doc that contains another item's exact path (as a delimited token) produces exactly
  one `reference` edge, even if the path appears several times; the item's row shows
  "referenced by" and the doc's row shows "references."
- A doc containing `.claude/agents/x.md.bak` or the bare word `API.md` inside
  `legacy_API.md.old` produces **no** edge to `.claude/agents/x.md` / `API.md` (boundary
  rule).
- A doc line `see token: .claude/agents/x.md` produces **no** edge (redaction removes the
  path before scanning) — pinned, accepted behavior.
- `CLAUDE.md` / `AGENTS.md` shows "declares" edges to its provider's MCP servers, hooks,
  and commands; the items show "declared by." A cursor-only repo (no instruction doc)
  produces no `declares` edges and does not error. A `vendor/CLAUDE.md` generic doc is
  never treated as the claude hub.
- A single-server codex repo whose `AGENTS.md` cites `.codex/config.toml` yields one
  `declares` edge and zero `reference` edges (config-path exclusion).
- Clicking any Related entry or any Cross-references endpoint scrolls the **canonical** row
  for that id into view and flashes it (jump controls never shadow canonical rows).
- A doc body with `</script><img src=x onerror=alert(1)>` near a referenced path, and a
  body where the snippet window edge falls inside a bare `&`/`<` run, both yield inert,
  well-formed escaped evidence — no script execution, no raw HTML, no bisected entity.
- `grep -nE 'innerHTML|outerHTML|insertAdjacentHTML' app.js` returns nothing.
- Output is byte-identical across repeated runs (edge list including `evidence` bytes) and
  stays under the size budget; the doc search slice is unchanged from 4a; in degraded mode
  edges still render and jump with `evidence` blank.
- Neither `_refScanBody` nor `_rawBody` appears in the rendered HTML.
- Schema rejects an edge with a dangling `from` / `to`, an unknown `type`, or a non-string
  field.

## Testing

- Unit (`_build_relationships`):
  - reference dedup across repeated mentions; boundary rejection of `.md`-inside-`.md.bak`
    and filename-in-prose; the `path → set(ids)` uniqueness filter (a path on one item
    after iterating other buckets still matches; a path on two items matches nothing);
    the four config-path exclusions, incl. the single-server-codex double-edge case.
  - `declares` from the provider-tagged hub to MCP / hook / command items; cursor (no hub)
    yields none; a generic `vendor/CLAUDE.md` is not a hub; hub picks the root marker over
    a nested instruction doc; `(path, id)` tiebreak when no root marker.
  - redaction false-negative: `token: <path>` produces no edge.
  - evidence cut from `body.find` lowest index; `_EVIDENCE_BEFORE/AFTER` window;
    slice-raw-then-escape (inject `</script><img onerror>` adjacent to a path and a bare
    `&`/`<` straddling the window edge; assert escaped, well-formed, inert).
  - deterministic sort; full edge list (incl. evidence bytes) byte-identical across runs.
- Unit (`_refScanBody`): set on docs by the adapters, read by the builder, absent from the
  serialized island; the doc search slice (`_searchBody`) is unchanged vs. 4a.
- Schema: dangling id, bad `type`, non-string field each rejected; `known_ids` built as a
  set from the data object; a valid edge set passes on both full and reduced data.
- Unit (`_reduce_for_size`): edges retained, `evidence` blanked, re-validates under budget.
- Playwright DOM (`page.set_content`): bidirectional Related with correct verbs and
  `htmlUnescape`-d titles; clicking Related / a Cross-references endpoint jumps to and
  flashes the **canonical** row (not a jump control); the Cross-references view groups by
  source and every endpoint jumps; hostile-content evidence is inert; degraded/light mode
  still renders Related and Cross-references; the init sequence leaves `buildRowIndex`
  indexing only canonical rows.
- CI guard: `app.js` stays free of `innerHTML` / `outerHTML` / `insertAdjacentHTML`.

## File-by-file plan

- `src/acc/generate.py` — `_build_relationships`; wire `relationships`; the pinned
  pop-before-assembly order; `_reduce_for_size` evidence blanking; `_EVIDENCE_BEFORE/AFTER`.
- `src/acc/adapters/claude.py`, `codex.py`, `generic.py` — `_refScanBody = clean` on docs;
  `provider` tag on claude / codex instruction docs.
- `src/acc/schema.py` — `_validate_relationships` (shape, enum, referential integrity);
  `known_ids` as a set from the data object.
- `src/acc/templates/app.js` — adjacency + label maps; inline Related (non-indexed
  controls, `htmlUnescape`-d titles); Cross-references view; pinned init sequence; nav +
  Overview card.
- `src/acc/templates/dashboard.html.tmpl` — `#crossref` section + nav anchor.
- `src/acc/templates/styles.css` — Related + Cross-references styles.
- `tests/` — unit + schema + Playwright DOM + the existing innerHTML guard.

## Reusable infra consumed from Phase 4a

- Per-row `id` + the `id → row` map + `jumpTo` → inline Related links and Cross-references
  endpoints jump with the existing mechanism (and never pollute the index — decision 6).
- `type` / `typeLabel` on search records → the `metaById` label map for edge endpoints.
- The `htmlUnescape`-at-display pattern + `_html.escape` at build → reused verbatim for
  `evidence` and for Related/Cross-references titles.
- The `_SEARCH_BODY_CHARS` cap pattern → `_EVIDENCE_BEFORE/AFTER` follow it (named
  constants, codepoint-based, slice-raw-then-escape).

## Open questions (resolve during spec review / Codex debate)

1. **`reference` evidence shape** — escaped context snippet (this spec's choice) vs. the
   matched path string (simpler, but makes "escape evidence" a no-op). Default: snippet.
2. **`_EVIDENCE_BEFORE` / `_EVIDENCE_AFTER`** — accept 40 / 80 or set other values.
3. **Redaction false-negative** — scan the redacted body and accept dropped
   keyword-prefixed paths (this spec's choice, leak-proof) vs. scan the raw body and build
   evidence from the redacted body (no false negatives, but scans unredacted text).
   Default: scan redacted.
4. **doc → doc references** — docs are reference targets (a doc citing another doc's path).
   Keep, or restrict targets to inventory items only? Default: keep docs as targets.
5. **command in the `declares` set** — file-based commands are "declared" loosely by the
   provider hub. Keep MCP / hook / command as locked, or narrow to MCP / hook? Default:
   keep all three.
6. **codex prompt commands as reference sources** — kept as a Non-goal this slice (only
   doc bodies are scanned). Promote to a reference source later, or leave out? Default:
   Non-goal.

## Out of scope → later phases

- Body-mentions-name edges (deferred for false-positive risk).
- Reference sources beyond doc bodies (codex prompt commands and other body-bearing items).
- Ordered workflow chains; a POC-style multi-view sidebar router.
- Config-file nodes as addressable endpoints (rejected alternative for this slice).
- Packaging (`/dashboard`, refresh tiers, plugin); latent Phase 3 hardening.

## Review provenance

5-lens adversarial design review (XSS / island safety, determinism, reference false
positives, jump / render correctness, schema / referential integrity), source-grounded
against `generate.py`, `schema.py`, the adapters, and `app.js`; run
`wf_244234f2-95e`. 18 findings surfaced; the verification stage was interrupted at session
suspend (2 of N verdicts journaled), so findings were adjudicated against ground-truth
source and nearly all confirmed. Folded in: distinct `_refScanBody` (the dormant
`_rawBody → _searchBody` promotion would have silently changed the doc search slice and
broken the budget); boundary-checked path match (substring matched `x.md` inside
`x.md.bak`); provider-tagged hub docs (path-suffix attribution could let `vendor/CLAUDE.md`
shadow the hub); non-indexed jump controls (Related/crossref `data-id` would pollute
`buildRowIndex` first-wins); pinned evidence determinism (`body.find` + exact window,
slice-raw-then-escape); `path → set(ids)` uniqueness (never first-wins); config-path
exclusion incl. the single-server double-edge; redacted-body scan with a documented
false-negative; `known_ids` as a set from the data object; pinned pop-before-serialize
order and init sequence; `htmlUnescape`-d Related titles. Remaining choices logged as open
questions for the Codex debate.

# (end of spec)
