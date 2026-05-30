# Phase 4b — Relationships (cross-references)

> Status: SPEC. Splits the "relationships" half out of the Phase 4 roadmap, after
> Phase 4a (Find) shipped and merged (PR #4, merge commit `e76c0df`). Ordered workflow
> chains, a multi-view router, and packaging stay in later phases. To be hardened by a
> multi-agent adversarial design review and a Codex debate before planning — see "Review
> provenance" at the end.

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
3. **Reference matching is exact-path, unique-path-only.** Scan for an item/doc's exact
   repo-relative path as a literal substring, and only for paths that are unique in the
   corpus. Shared config paths (every hook and MCP server in `.claude/settings.json`) are
   excluded from `reference` matching — they are covered by `declares`.
4. **Structural source = the provider instruction-doc hub.** `declares` edges run from a
   provider's `CLAUDE.md` / `AGENTS.md` doc to that provider's config-declared items.
   Providers with no instruction doc (cursor; or a repo with `.claude/settings.json` but
   no `CLAUDE.md`) produce no `declares` edges. This is a documented gap, not an error.
5. **textContent only.** Edges render through `el()` / `textContent`; no new
   `innerHTML` / `outerHTML` / `insertAdjacentHTML`. The CI guard still holds.
6. **Edges are stored directed, rendered bidirectionally.** One stored edge (`from → to`)
   shows on both endpoints' rows with a direction-aware verb.
7. **The view is named "Cross-references," laid out grouped by source.** Ordered chains
   ("Workflows") stay deferred, so the name avoids implying sequence.

## Scope

- `generate.py`: a new `_build_relationships(inv, docs)` that emits the edge list; wire it
  into `data["relationships"]`. Adapters carry a private `_rawBody` on each doc so the
  reference scan sees full doc text; drop it before serialization (same lifecycle as
  `_searchBody`). `_reduce_for_size` keeps edges but blanks `evidence`.
- `schema.py`: validate the edge shape, the `type` enum, and referential integrity
  (every `from` / `to` resolves to a known id).
- `app.js`: build an `id → edges` adjacency index and an `id → {title, typeLabel}` label
  map; render an inline "Related" block per row; add `renderCrossReferences()`; wire the
  nav anchor and an Overview card.
- `dashboard.html.tmpl`: a `#crossref` section and its nav anchor.
- `styles.css`: `.acc-related` and Cross-references styles.

## Non-goals (Phase 4b)

- Body-mentions-name edges (deferred, decision 2).
- Ordered workflow chains and a multi-view sidebar router.
- `declares` edges from agents / skills / rules. The locked kind list is MCP / hook /
  command; agents and skills are reachable as `reference` targets when a doc cites them.
- New endpoint node types. Config files are not promoted to addressable nodes in this
  slice (that was the rejected "config-file nodes" alternative); the provider instruction
  doc is the structural hub instead.
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
    matched path (cap `_EVIDENCE_CHARS`, default 120, multibyte-safe like
    `_SEARCH_BODY_CHARS`). This shows *how* the doc refers to the item, and is the reason
    the locked design calls for escaped evidence.
    > Refinement note: the brainstorm presented `reference` evidence as "the matched path
    > string." A path is generator-controlled and would make "escape evidence" a no-op,
    > so this spec sharpens it to an author-derived snippet, which is what the locked
    > "escape evidence" / `htmlUnescape`-at-display requirement was for. Open to reverting
    > to path-only at spec review.
  - For `declares`: the declaring config file path (`.claude/settings.json`, `.mcp.json`,
    `.codex/config.toml`). Generator-controlled, but escaped on the same pass for a
    uniform display path.
- **Order and dedup.** Dedup on `(from, to, type)`; sort on `(from, to, type)`. A doc that
  cites the same path more than once collapses to one edge, with evidence taken from the
  first match in document order. `render.py`'s `json.dumps(sort_keys=True)` fixes dict-key
  order but not list order, so the explicit sort is load-bearing (same as `_build_search`).

### Reference matching (the precise part)

- Build `path → id` over inventory items **and** docs, then keep only paths that map to
  exactly one id. Paths that map to several ids (shared config files) are dropped from the
  reference lookup.
- For each doc, scan its `_rawBody` (full redacted pre-markdown text) for each unique path
  as a literal substring. A markdown link `[x](.claude/agents/x.md)` matches because the
  path appears literally; no markdown-link parser is needed.
- Skip self-edges (`from == to`) defensively.
- The doc body never enters `relationships` except as the capped, escaped snippet. The
  path being matched is generator-controlled, so a hostile body cannot inject an id.

### Structural `declares` (the hub rule)

- A provider's instruction docs are identified by path: claude — `CLAUDE.md` or
  `.claude/**/CLAUDE.md`; codex — `AGENTS.md` or `.codex/**/AGENTS.md`. Both land in
  `docs["references"]` via their adapters.
- The hub is the root marker (`CLAUDE.md` / `AGENTS.md`) when present, otherwise the
  instruction doc with the lexicographically smallest path. Deterministic.
- For each inventory item with `provider == hub provider` and
  `type in {mcpServer, hook, command}`, emit `{from: hub.id, to: item.id, type:
  "declares", evidence: item.path}`.
- No hub for a provider → no `declares` edges for it (cursor always; claude/codex when the
  instruction doc is absent).

### `_rawBody` lifecycle

Docs persist only `summary` + `html` today, so the reference scan needs the full text.
The `claude`, `codex`, and `generic` adapters set `doc["_rawBody"] = clean` (the redacted
raw markdown they already compute; cursor indexes no docs). `_build_relationships` reads
it; `generate()` then `pop`s `_rawBody` alongside `_searchBody` before assembling the
serialized `data`. `_rawBody` is never escaped and never serialized — it exists only for
the in-process scan. The pop must move to **after** `_build_relationships` runs.

## Rendering model

- **Adjacency + labels.** Build once from `data.relationships`:
  `edgesByEndpoint: id → [{ otherId, dir, type, evidence }]` (`dir` is `out` on the `from`
  side, `in` on the `to` side), and `metaById: id → { title, typeLabel }` sourced from the
  search records. The label map lets a Related entry name its target even when the target
  row is in a collapsed or empty bucket.
- **Inline "Related."** After a row renders, append an `.acc-related` block listing its
  edges. Each entry is a clickable control that calls `jumpTo(otherId)`, labeled with a
  direction-aware verb, the target's type chip, and the target title; `evidence` shows as
  muted, `htmlUnescape`-d text. Verbs: `declares` out → "declares", `declares` in →
  "declared by", `reference` out → "references", `reference` in → "referenced by".
- **Cross-references view.** A `#crossref` section with `renderCrossReferences()`. Layout
  is grouped by source: each source row (a doc) listed once, its outgoing edges indented
  beneath, every endpoint a jump control. An Overview card links to it with an edge count.

```
Cross-references (12)

CLAUDE.md  [doc]
  → declares     MCP server  github         (.claude/settings.json)
  → declares     Hook        PreToolUse     (.claude/settings.json)
  → references   Agent       code-reviewer  (.claude/agents/code-reviewer.md)

AGENTS.md  [doc]
  → declares     MCP server  context7       (.codex/config.toml)
```

- **Empty state.** No edges → the Cross-references section renders a one-line "No
  cross-references found" note; rows with no edges render no Related block (not an empty
  one).
- **Degraded mode.** `_reduce_for_size` keeps the edge list (ids + type are tiny) but
  blanks `evidence`. Related and Cross-references still render and jump, because labels
  come from the retained light search index, not from `evidence`.

## Architecture

- `generate.py`
  - `_build_relationships(inv, docs) -> list[dict]` — the reference pass (unique-path
    lookup + per-doc `_rawBody` scan + escaped snippet evidence) and the `declares` pass
    (hub resolution + config-declared items). Dedup and sort.
  - wire `data["relationships"] = _build_relationships(inv, docs)`; move the `_searchBody`
    pop to after this call and pop `_rawBody` in the same loop.
  - `_reduce_for_size` — blank `evidence` on each retained edge.
- adapters/`claude.py`, `codex.py`, `generic.py` — set `_rawBody = clean` on each doc dict.
- `schema.py` — `_validate_relationships(edges, known_ids)`: each edge has
  `{from, to, type, evidence}` as strings; `type in {reference, declares}`; `from` / `to`
  in `known_ids` (inventory ∪ docs ∪ todos). Called from `validate()`.
- `app.js` — `edgesByEndpoint` + `metaById`; the inline Related pass; `renderCrossReferences()`;
  nav wiring; the Overview card. Reuse `el`, `htmlUnescape`, `jumpTo`.
- `dashboard.html.tmpl` / `styles.css` — `#crossref` section + nav anchor; `.acc-related`
  and Cross-references styles.

## Acceptance criteria

- A doc that contains another item's exact path produces exactly one `reference` edge,
  even if the path appears several times; the item's row shows "referenced by" and the
  doc's row shows "references."
- `CLAUDE.md` / `AGENTS.md` shows "declares" edges to its provider's MCP servers, hooks,
  and commands; the items show "declared by." A cursor-only repo (no instruction doc)
  produces no `declares` edges and does not error.
- A doc mention of `.claude/settings.json` does **not** fan out to every hook and MCP
  server (shared paths are excluded from reference matching).
- Clicking any Related entry or any Cross-references endpoint scrolls that exact row into
  view and flashes it.
- A doc body containing `</script><img src=x onerror=alert(1)>` near a referenced path
  yields an inert, escaped evidence snippet — no script execution, no raw HTML.
- `grep -nE 'innerHTML|outerHTML|insertAdjacentHTML' app.js` returns nothing.
- Output is byte-identical across repeated runs and stays under the size budget; in
  degraded mode edges still render and jump with `evidence` blank.
- Schema rejects an edge with a dangling `from` / `to`, an unknown `type`, or a non-string
  field.

## Testing

- Unit (`_build_relationships`): reference dedup across repeated mentions; `declares` from
  the hub to MCP / hook / command items; cursor (no hub) yields no `declares`; the
  shared-path exclusion holds; self-edge guard; deterministic sort; evidence escaped
  (inject `</script><img onerror>` adjacent to a path and assert the stored snippet is
  escaped); the hub rule picks the root marker over a nested instruction doc.
- Unit (`_rawBody`): set on docs by the adapters, read by the builder, absent from the
  serialized island.
- Schema: dangling id, bad `type`, and non-string field each rejected; a valid edge set
  passes.
- Unit (`_reduce_for_size`): edges retained, `evidence` blanked, re-validates under budget.
- Playwright DOM (`page.set_content`): bidirectional Related with correct verbs; clicking
  Related jumps + flashes the exact row; the Cross-references view groups by source and
  every endpoint jumps; hostile-content evidence is inert; degraded/light mode still
  renders Related and Cross-references.
- CI guard: `app.js` stays free of `innerHTML` / `outerHTML` / `insertAdjacentHTML`.

## File-by-file plan

- `src/acc/generate.py` — `_build_relationships`; wire `relationships`; move/extend the
  private-field pop; `_reduce_for_size` evidence blanking.
- `src/acc/adapters/claude.py`, `codex.py`, `generic.py` — `_rawBody = clean` on docs.
- `src/acc/schema.py` — `_validate_relationships` (shape, enum, referential integrity).
- `src/acc/templates/app.js` — adjacency + label maps; inline Related; Cross-references
  view; nav + Overview card.
- `src/acc/templates/dashboard.html.tmpl` — `#crossref` section + nav anchor.
- `src/acc/templates/styles.css` — Related + Cross-references styles.
- `tests/` — unit + schema + Playwright DOM + the existing innerHTML guard.

## Reusable infra consumed from Phase 4a

- Per-row `id` + the `id → row` map + `jumpTo` → inline Related links and Cross-references
  endpoints jump with the existing mechanism.
- `type` / `typeLabel` on search records → the `metaById` label map for edge endpoints.
- The `htmlUnescape`-at-display pattern + `_html.escape` at build → reused verbatim for
  `evidence`.
- The `_SEARCH_BODY_CHARS` cap pattern → `_EVIDENCE_CHARS` follows it (named constant,
  multibyte-safe, budget-justified).

## Open questions (resolve during spec review / Codex debate)

1. **`reference` evidence shape** — escaped context snippet (this spec's choice) vs. the
   matched path string (simpler, but makes "escape evidence" a no-op). Default: snippet.
2. **`_EVIDENCE_CHARS`** — accept 120 or set another number.
3. **doc → doc references** — docs are included as reference targets (a doc citing another
   doc's path). Keep, or restrict targets to inventory items only? Default: keep docs as
   targets.
4. **command in the `declares` set** — file-based commands are "declared" loosely by the
   provider hub. Keep MCP / hook / command as locked, or narrow to MCP / hook? Default:
   keep all three.

## Out of scope → later phases

- Body-mentions-name edges (deferred for false-positive risk).
- Ordered workflow chains; a POC-style multi-view sidebar router.
- Config-file nodes as addressable endpoints (rejected alternative for this slice).
- Packaging (`/dashboard`, refresh tiers, plugin); latent Phase 3 hardening.

## Review provenance

To be filled after a multi-agent adversarial design review (lenses: XSS / island safety,
determinism, reference false positives, jump / render correctness, schema and referential
integrity, size budget) and the Codex debate. Confirmed findings get folded back into this
spec before planning.

# (end of spec)
