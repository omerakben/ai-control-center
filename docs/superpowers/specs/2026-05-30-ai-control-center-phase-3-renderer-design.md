# AI control center — Phase 3 (renderer: Overview + Inventory) design

Date: 2026-05-30
Status: approved for planning
Project: html-dash (AI Control Center)
Builds on: `2026-05-29-ai-control-center-design.md` (v1 design), Phase 1 and Phase 2 (merged)

## Scope

Phase 3 builds the human-facing views over the data that Phases 1 and 2 already put in the JSON island. Today the renderer shows Docs and TODOs and leaves an empty Overview; the inventory the adapters produce is in the island but never drawn. Phase 3 adds two views — a bento Overview and an Inventory view grouped by type — wires path links to source files, and adds the output size budget that Phase 2 parked here.

Phase 3 is render-first. The one data change is a small `source.pathPrefix` field that path links need, plus a `generator.truncated` flag for the size budget. No adapter behavior changes.

Locked decisions from brainstorming:

1. Inventory view groups by type (one block per non-empty bucket), with a provider chip and the native type label on every row. Empty buckets hide. Bucket order is a fixed constant.
2. Overview is a bento grid of cards built from real data only: providers detected, inventory counts, open TODOs, docs count. Cards with no data do not render. The spec's milestone and last-decision cards stay out — no source produces them yet.
3. Items are rows, not expandable panels. The path is a clickable relative link to the source file. No inline markdown rendering, so no HTML-injection path enters in this phase.
4. Tests are Python HTML-string assertions, consistent with Phases 1 and 2. No JS or browser test toolchain is added. A Playwright screenshot is the manual visual check, outside the automated suite.
5. The full size budget lands here: warn over 1 MB, switch to a summary-only island over 2 MB.

## Hard constraints carried from v1

- Stdlib only at runtime. No new dependencies in the generator or the renderer.
- The renderer is classic inline JavaScript in one IIFE. No ES modules (they fail over `file://`), no CDN, no framework.
- `textContent` for all author-derived text. The only attribute set from data is the path link `href`, and it is `encodeURI`'d. No `innerHTML`, so the stored-XSS posture is unchanged.
- Deterministic output: fixed section and bucket order, the island stays canonical and sorted, no timestamps or mtimes.
- One self-contained HTML file under the owning provider folder.

## Architecture

### Renderer (`src/acc/templates/`)

**`app.js`** grows from four render functions to six, plus one shared row builder. The existing IIFE, `el()` helper, and `wireSearch()` stay.

- `itemRow(opts)` — the shared DOM builder. `opts` is `{provider?, typeLabel?, title, path, summary?}`. It builds a row with an optional provider chip (`.acc-chip`), an optional type-label badge (`.badge`), the title, an optional summary line, and the path rendered as `<a class="path" href="…">`. The `href` is `encodeURI(prefix + "/" + path)` where `prefix` is `data.source.pathPrefix`. It sets `row.dataset.search` from the row's own text (title, path, summary), so search keeps working without the island's `search` array. `renderDocs`, `renderTodos`, and `renderInventory` all route through it, removing the row-building duplication that exists today.
- `renderOverview()` — builds an `.acc-bento` grid. One card per data category that has content:
  - Providers — a chip per detected provider (`displayName`).
  - Inventory — a count per non-empty bucket ("1 agent", "2 commands", …). The card hides if every bucket is empty.
  - Open TODOs — the count plus up to the first three texts. Hides if none.
  - Docs — the count. Hides if none.
  Each card scroll-links to its section. A card with no data is not appended.
- `renderInventory()` — iterates the buckets in a fixed order (`agents`, `commands`, `skills`, `hooks`, `mcpServers`, `rules`). For each non-empty bucket it appends a labeled block ("Agents (1)") and one `itemRow` per item. Items arrive already sorted from the generator. Empty buckets are skipped.
- Truncation notice — if `data.generator.truncated` is true, a banner at the top of the body states that the dashboard was reduced to a summary for size, built with `textContent`.

**`dashboard.html.tmpl`** adds an `Inventory` nav link and a `<section id="inventory">` with a host div, between Overview and Docs. The `#acc-overview` host already exists.

**`styles.css`** adds `.acc-bento` (a responsive grid via `grid-template-columns: repeat(auto-fill, minmax(200px, 1fr))`), `.acc-card`, and `.acc-chip`, reusing the existing color tokens. No new color scheme.

### Generator (`src/acc/generate.py`)

- `source.pathPrefix` — the posix relative path from the dashboard's output directory to the repo root, computed with `os.path.relpath(root, out_dir)` and normalized to posix separators. For the standard provider-folder owner (`.claude/`, `.codex/`, `.cursor/`, `.ai-control-center/`) it is `".."`. The renderer joins it with each item path to resolve links over `file://`.
- Size budget — after the full HTML is rendered, measure its UTF-8 byte length:
  - over 2 MB (`_TRUNCATE_BYTES = 2_000_000`): rebuild the island in summary-only form and re-render. The reduced island keeps the navigable skeleton (providers, every inventory item's `provider`/`type`/`typeLabel`/`title`/`path`, inventory counts, project title, open-TODO texts, and the doc index titles and paths) and drops the heavy free text: every inventory and doc `summary` string, `docs[].html` bodies, and the `search` array. It sets `generator.truncated = true`. The re-rendered HTML is the output.
  - over 1 MB (`_WARN_BYTES = 1_000_000`) and not truncated: log a warning with the byte size and keep the full island.
  Both thresholds key off the same measured size, so the mode is a deterministic function of the input.

### Schema (`src/acc/schema.py` and the data dict)

- `source` gains `pathPrefix` (string).
- `generator` gains `truncated` (bool, default `false`).
- No bucket or item shape changes. The required-top-level-key set is unchanged. `validate()` and the `assert_no_secrets` tripwire are untouched; the reduced island only removes fields, so it cannot introduce a leak.

### Data flow

`island JSON → parse → renderHead · renderOverview · renderInventory · renderDocs · renderTodos → wireSearch`. The renderer is a pure function of the island, runs offline, and adds no network calls. The size-budget branch runs entirely in the generator before the file is written.

## Security and determinism

- XSS posture is unchanged. Every author-derived value goes through `textContent`. The single `href` is `encodeURI`'d and built only from `item.path` (a real, already-escaped repo-relative path) and the generator-computed `pathPrefix`. No `innerHTML`.
- The reduced island removes fields only, never adds, so the redaction guarantees and the `assert_no_secrets` tripwire still hold in both modes.
- Determinism holds: section and bucket order are fixed constants, `pathPrefix` is a pure function of `(root, out_dir)`, and the truncation mode is a pure function of the measured size. Two runs on the same input produce byte-identical output.

## Testing

TDD, stdlib `pytest`, Python HTML-string assertions over `render_html` and `generate` output.

- `tests/test_render.py` (extended) — the template carries the `Inventory` section and nav link; `app.js` defines `renderOverview`, `renderInventory`, and `itemRow`; `styles.css` carries the bento classes; given data with inventory, the island carries each item's `provider`/`typeLabel`/`title`/`path`; the bento and inventory hosts exist.
- `tests/test_generate.py` (extended) — `source.pathPrefix == ".."` for a provider-folder owner and the correct value for the `.ai-control-center` fallback; path strings in the island are unchanged (links are built in the renderer); determinism across two runs still holds.
- `tests/test_generate.py` size budget — a large in-test fixture pushes the island over each threshold: between 1 and 2 MB logs a warning (via `caplog`) and keeps the full island; over 2 MB sets `generator.truncated` and drops `summary`, `docs[].html`, and `search`; under 1 MB does neither.
- `tests/test_schema.py` (extended) — the new `source.pathPrefix` and `generator.truncated` fields are accepted and the existing validation still passes.
- `tests/builders.py` (extended) — `make_large_repo(root, n)` stamps enough sizable markdown to exceed the budget thresholds.
- Determinism and packaging tests stay green; templates still ship as package data.

## What Phase 3 leaves for later

- Expandable item detail and inline rendering of the sanitized markdown `html` field.
- The relationship Map (`relationships` stays `[]`).
- Data sources for `recentDocs`, current milestone, and last decision, and the Overview cards that would show them.
- Wiring `generator.rendererDigest` (still an empty string) to a hash of the renderer assets.
- The three-tier refresh, the `/dashboard` command, and the skill and plugin packaging (Phase 4).
