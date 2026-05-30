# Phase 4a — Find (global omnibox)

> Status: SPEC. Splits the "search" half out of `phase-4-roadmap.md` workstream D.
> Phase 4b (Relationships) and the packaging work (refresh, `/dashboard`, plugin) are
> separate specs. Grounded in a 15-agent adversarial design review (run
> `wf_553ff185-c26`) — see "Review provenance" at the end.

Phase 3 shipped a deterministic single-file dashboard with an Overview bento and an
Inventory view grouped by type. The pain that started this product — "it's hard to see
where what I'm looking for is" — is still half-served: Inventory has a per-row filter,
but there is no way to search across everything at once and land on the hit.

The generator already builds a search index (`_build_search` → `data.search`) and ships
it in the data island, but the renderer never reads it (`app.js` filters rows by a
separate `dataset.search` blob and ignores `data.search` entirely). Phase 4a turns that
dead index into a real global omnibox, extends it just enough to be useful, and builds
the **reusable jump infrastructure** (per-item ids + an id→row map) that Phase 4b's
relationship surfaces will consume.

## Decisions (locked)

1. **Find leads.** Relationships → Phase 4b; packaging → a later phase.
2. **Split confirmed.** 4a is Find only; 4a owns the shared jump infra so 4b reuses it
   rather than duplicating it.
3. **Search = both.** A global omnibox consuming `data.search`, plus the existing
   per-view row filter (kept, with its role made distinct from the omnibox).
4. **Index depth = names + paths + summaries + a capped body slice.**
5. **textContent only.** Every value reaches the DOM via `textContent`; the path `href`
   (per-segment `encodeURIComponent`) stays the sole data-derived attribute.
6. **Highlighting is `createElement('mark')` + `textContent`, never `innerHTML`.**
7. **No view router in this phase.** "Jump" means scrollIntoView + a transient highlight
   on the item's row. The POC-style multi-view sidebar IA is worth doing, but as its own
   phase.

## Scope

- `generate.py` `_build_search`: add `type` + `typeLabel` per record (including docs);
  append a capped, escaped body slice to the indexed `text`; keep the deterministic sort.
- `generate.py` `_reduce_for_size`: rebuild a **light** index (names + paths) in
  summary-only mode instead of emptying `search`, so the omnibox still works on large repos.
- `generate.py` give every searchable item — including TODOs — a stable `id` so results
  can be jumped to.
- `schema.py`: enforce the search-record shape at build time.
- `app.js`: an omnibox reading `data.search` — type-grouped results with counts and a
  matched snippet, keyboard nav, focus via `/`, and jump via an `id → row` map built at
  render time. Add a per-row id in every render path (inventory, docs, todos).
- `dashboard.html.tmpl` + `styles.css`: omnibox markup; `<mark>`, type-chip, and
  highlight-flash styles.
- Keep the per-view filter; relabel the two inputs so they don't read as duplicates.

## Non-goals (Phase 4a)

- Relationships: `_build_relationships`, edges, inline "Related", the dedicated view —
  Phase 4b.
- A multi-view sidebar router — a later phase (jump is scrollIntoView here).
- Ordered workflow chains, refresh tiers, `/dashboard`, plugin packaging.
- The two latent Phase 3 items (`markdown.py` `_safe_link` attribute-escaping,
  `render.py` `__SCHEMA_VERSION__` ordering) stay deferred: 4a routes no `doc.html`
  through `innerHTML`, so they remain unreached.

## Data contract (changes)

Search record grows from `{id, title, path, text}` to:

```
{ id, type, typeLabel, title, path, text }
```

- `type` — the internal kind used as a stable group key (`skill`, `agent`, `command`,
  `mcpServer`, `hook`, `rule`, `reference`, `doc`, …).
- `typeLabel` — the human group heading (`Claude agent`, `MCP server`, …). Inventory
  items already carry both via `make_item` (`base.py`); **docs do not** — they are built
  by a separate path (`claude.py`/`codex.py`/`generic.py`) and grouped only by bucket
  name. `_build_search` must synthesize a `type`/`typeLabel` for doc records from their
  bucket key, or doc results land in an undefined group. `type`/`typeLabel` are
  generator-controlled constants (not author input), so they follow the existing
  `provider`/`typeLabel` convention and are not escaped.
- `text` — `summary` plus a capped slice of the item's raw body.
- **Order:** records stay sorted by `(path, title, id)` (already deterministic). Adding
  fields does not change ordering. `render.py` does `json.dumps(sort_keys=True)`, which
  fixes dict-key order but **not** list order, so the explicit sort is load-bearing.

### Escaping and matching (the subtle part)

The data island is JSON read via `JSON.parse(node.textContent)` — a JSON-in-`<script>`
context, not HTML. Island-breakout safety already comes from `render.py`'s
`.replace("</","<\/")` over the whole payload, and display safety comes from
`app.js` using `textContent` exclusively. Phase 1's field-level `html.escape` is a
defense-in-depth layer on top of that.

We **keep** that layer (do not weaken the hardening), but it has a side effect: a value
like `AT&T` is stored as `AT&amp;T`, so naive `textContent` display shows the entity and
a substring search for `AT&T` misses. Resolution:

- The capped body slice is escaped on the **same** path as `title`/`summary` (Phase 1
  contract), so the stored island stays uniformly escaped.
- `app.js` gains a small `htmlUnescape(s)` helper (decode `&amp; &lt; &gt; &quot; &#39;`).
  It is applied **only** at the `textContent` assignment for display and when building
  the omnibox match key. `textContent` makes the decoded value inert, so this restores
  correct display + search without reintroducing an HTML sink.

This resolves the review's "capped slice bypasses escape" and "escaping breaks the
omnibox for `& < > " '`" findings while preserving the island's defense-in-depth.

### `_SEARCH_BODY_CHARS` (the cap)

A module-level constant with a rationale comment tying it to the size budget
(`_WARN_BYTES = 1_000_000`): at ~500 indexable items, `500 × 200 = 100 KB` pre-escape —
an order of magnitude under the warn line; `_reduce_for_size` is the safety valve above
it. Default: **200**. A test asserts the cap boundary (including a clean cut on a
multibyte body) and that a large synthetic repo still truncates.

## Rendering model

- **Omnibox.** `input#acc-omnibox` in the header. `/` focuses it (unless a field is
  already focused); `Esc` clears and closes the result panel.
- **Matching.** On input (debounced ~60 ms), filter `data.search` by a literal,
  lowercased substring over `htmlUnescape(title + path + text)`. Build that match key
  once per record.
- **Results.** Group hits by `type` (heading = `typeLabel`), show a per-group count, cap
  rendered hits per group (e.g. 8) with a "+N more" line. Each hit row = `htmlUnescape`d
  title + a type chip + path + a matched snippet, all via `el()`/`textContent`.
- **Highlight.** Wrap the match by splitting the logical string on the query and
  appending text nodes and `createElement('mark')` nodes, each via `textContent`. No
  `innerHTML`, no string-built markup.
- **Jump.** Build an `id → rowElement` map while rendering the views. Enter/click on a
  hit scrolls its row into view and toggles a transient highlight class. The map degrades
  cleanly when an id has no rendered row (empty bucket skipped, or truncated mode). Item
  ids are the existing `stable_id` (`"i"+sha1hex`, fixed alphabet, DOM-safe); resolve
  through the map, never a selector concatenated from item text.
- **Keyboard.** `↑`/`↓` move the active hit, `Enter` jumps, `Esc` closes.
- **Empty states.** Empty query → panel hidden. No hits → "No matches". Light/degraded
  index → a one-line note that body search is off.

## Architecture

- `generate.py`
  - `_build_search(inv, docs)` → add `type` + `typeLabel` (synthesize for docs from the
    bucket key); append the escaped capped slice to `text`; keep the sort. The slice's
    raw source must be captured and escaped in the **same pass** that escapes
    `title`/`summary`, before `_build_search` reads it (preserve the "search reads escaped
    fields" contract). Note: doc bodies live in the separately-sanitized `html` field, so
    the slice source for docs needs an explicit decision — slice the doc `summary`, or
    carry a raw pre-markdown body. Default: slice `summary` for docs, raw body for
    inventory items that have one.
  - `_reduce_for_size(data)` → replace `reduced["search"] = []` with a light rebuild:
    keep `{id, type, typeLabel, title, path, text: ""}` per record. Re-validate stays
    under budget.
  - ensure TODO records carry a stable `id`.
- `schema.py` → `validate()` checks each `search` record has the required keys, string
  types, and a known `type`. A build-time backstop so a dropped field or wrong type fails
  loudly.
- `app.js` → omnibox build/consume/group/snippet/`<mark>`/keyboard/jump; the `htmlUnescape`
  helper; the `id → row` map; per-row id in inventory/docs/todos render paths; keep the
  per-view filter.
- `dashboard.html.tmpl` / `styles.css` → omnibox input + result panel + `<mark>` + flash.

## Acceptance criteria

- `/` focuses the omnibox; `Esc` closes it; `↑`/`↓` move the active hit; `Enter` jumps.
- Typing a skill's name shows it under its `typeLabel` group with a count; results from
  inventory **and** docs both group correctly (no undefined group).
- Enter on a hit scrolls that specific item's row into view and flashes it.
- Search matches name, path, summary, and capped body content.
- Typing `AT&T` finds and correctly displays an item named `AT&T` (logical text, not
  entities).
- A body containing `</script><img src=x onerror=alert(1)>` causes no script execution
  and no raw HTML — the text is inert. (XSS regression.)
- `grep -nE 'innerHTML|outerHTML|insertAdjacentHTML' app.js` returns nothing.
- Output is byte-identical across repeated runs; stays under the size budget; in
  light/degraded mode the omnibox still finds items by name and path.
- The per-view filter still works and reads as distinct from the omnibox.

## Testing

- Unit (`_build_search`): adds `type`+`typeLabel` to inventory and docs; caps the slice
  at `_SEARCH_BODY_CHARS` (multibyte-safe); escapes the slice (inject
  `</script><img onerror>` and assert escaped in `data.search`); records stay sorted.
- Unit (`_reduce_for_size`): keeps a non-empty light index, drops the body slice,
  re-validates under budget; a large synthetic repo crosses 1 MB and recovers.
- Unit: TODO records have ids.
- Schema: a malformed search record (missing key, wrong type, unknown `type`) is rejected.
- Playwright DOM (`page.set_content`): omnibox grouping + counts across inventory + docs;
  keyboard nav; jump scrolls + flashes the exact row; `<mark>` built via `textContent`;
  empty states; `AT&T` logical match + display; hostile-body inertness.
- CI guard: a test/lint step greps `app.js` for banned `innerHTML`/`outerHTML`/`insertAdjacentHTML`.

## File-by-file plan

- `src/acc/generate.py` — `_build_search` (type/typeLabel/escaped slice), `_reduce_for_size`
  (light rebuild), TODO ids.
- `src/acc/schema.py` — search-record validation.
- `src/acc/templates/app.js` — omnibox + `htmlUnescape` + id→row map + per-row ids.
- `src/acc/templates/dashboard.html.tmpl` — omnibox markup.
- `src/acc/templates/styles.css` — omnibox, `<mark>`, type chip, flash.
- `tests/` — unit + schema + Playwright DOM + the banned-`innerHTML` guard.

## Reusable infra handed to Phase 4b

- Per-row `id` on every item row + the `id → row` map → 4b's inline "Related" links and
  the dedicated Relationships view jump straight to items using the same mechanism.
- `type`/`typeLabel` on records → reused for edge endpoints.
- The `htmlUnescape`-at-display pattern → reused for any author-derived edge `evidence`.

## Open questions (resolve during spec review)

1. **Doc body-slice source** — slice the doc `summary` (simple, default) vs. carry a raw
   pre-markdown doc body to slice (deeper search, more plumbing). Default: `summary`.
2. **`_SEARCH_BODY_CHARS`** — accept 200 or set another number.

## Out of scope → later phases

- Phase 4b — Relationships (path-ref + structural edges first; body-mentions-name
  deferred; escape `evidence`; name the view "Cross-references" until ordered chains exist).
- A POC-style multi-view sidebar router.
- Packaging; ordered chains; latent Phase 3 hardening.

## Review provenance

15-agent adversarial review (5 lenses × source-reading agents, skeptic verification of
every high finding). All five lenses returned ship-with-changes. Confirmed findings folded
in: highlight-`innerHTML` trap → `<mark>`+CI guard; group-by-type impossible (records lack
`type`, docs lack it entirely) → `type`+`typeLabel` incl. docs; jump is net-new (no router,
no per-item id, todos lack ids) → scrollIntoView + id→row map + per-row ids + todo ids;
escaping breaks matching for `& < > " '` → keep escaping + `htmlUnescape` at display/match;
capped slice can exceed the budget → light-index rebuild in `_reduce_for_size`; cap
unjustified → named constant with budget math. Deferred to 4b: body-mentions-name edges
(high false-positive risk), `evidence` escaping, ordered-chain rename.

# (end of spec)
