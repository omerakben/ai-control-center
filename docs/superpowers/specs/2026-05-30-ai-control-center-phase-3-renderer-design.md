# AI control center — Phase 3 (renderer: Overview + Inventory) design

Date: 2026-05-30
Status: approved for planning (revised after Codex design debate)
Project: html-dash (AI Control Center)
Builds on: `2026-05-29-ai-control-center-design.md` (v1 design), Phase 1 and Phase 2 (merged)

## Scope

Phase 3 builds the human-facing views over the data that Phases 1 and 2 already put in the JSON island. Today the renderer shows Docs and TODOs and leaves an empty Overview; the inventory the adapters produce is in the island but never drawn. Phase 3 adds two views — a bento Overview and an Inventory view grouped by type — wires path links to source files, and adds the output size budget that Phase 2 parked here.

Phase 3 is render-first. The data changes are two small fields: `source.pathPrefix` for path links and `generator.truncated` for the size budget. No adapter behavior changes.

Locked decisions from brainstorming:

1. Inventory view groups by type (one block per non-empty bucket), with a provider chip and the native type label on every row. Empty buckets hide. Display order is a fixed constant.
2. Overview is a bento grid of cards built from real data only: providers detected, inventory counts, open TODOs, docs count. Cards with no data do not render. The spec's milestone and last-decision cards stay out — no source produces them yet.
3. Items are rows, not expandable panels. The path is a clickable relative link to the source file. No inline markdown rendering, so no HTML-injection path enters in this phase.
4. Tests are Python HTML-string/contract assertions plus real DOM tests via Playwright in CI (decided after the Codex debate, which showed string-presence checks cannot catch runtime href/DOM breakage). Playwright is a test-only dependency; the generator and renderer stay dependency-free.
5. The full size budget lands here: warn over 1 MB, switch to a summary-only island over 2 MB.

## Hard constraints carried from v1

- Stdlib only at runtime. The generator and the rendered dashboard add no dependencies. Only the test layer gains Playwright.
- The renderer is classic inline JavaScript in one IIFE. No ES modules (they fail over `file://`), no CDN, no framework.
- `textContent` for all author-derived text. The only attribute set from data is the path link `href`, built by per-segment URL-encoding (below). No `innerHTML`, so the stored-XSS posture is unchanged.
- Deterministic output: fixed section and bucket order, the island stays canonical and sorted, no timestamps or mtimes.
- One self-contained HTML file under the owning provider folder.

## Architecture

### Renderer (`src/acc/templates/`)

**`app.js`** grows from four render functions to six, plus one shared row builder. The existing IIFE, `el()` helper, and `wireSearch()` stay.

- `itemRow(opts)` — the shared DOM builder. `opts` is `{provider?, typeLabel?, title, path, summary?}`. It builds a row with an optional provider chip (`.acc-chip`), an optional type-label badge (`.badge`), the title, an optional summary line, and the path. `renderDocs`, `renderTodos`, and `renderInventory` all route through it, removing the row-building duplication that exists today. It sets `row.dataset.search` from the row's own text (title, path, summary), so search keeps working independent of the island's `search` array.
- Path link — the path renders as `<a class="path">` when a usable prefix exists, else as plain text. The `href` is built by encoding the **combined** relative path (prefix and path together) segment by segment, preserving only `.` and `..` segments:

  ```js
  function encodedRelHref(prefix, path) {
    var raw = (prefix === "." ? path : prefix + "/" + path);
    return raw.split("/").map(function (seg) {
      return seg === "." || seg === ".." ? seg : encodeURIComponent(seg);
    }).join("/");
  }
  ```

  Encoding the whole combined path (not just `item.path`) matters because `pathPrefix` is a general `relpath` and, when the out dir sits outside the repo, can itself contain real directory names with spaces, `#`, `?`, or `:` — and a raw `javascript:repo/...` prefix would otherwise read as a scheme over `file://`. Per-segment `encodeURIComponent` escapes those while preserving the `/` separators and the `.`/`..` navigation. If `data.source.pathPrefix` is absent or empty, the renderer omits the link and shows the path as text, so a missing prefix never produces an `undefined/...` href.
- `renderOverview()` — builds an `.acc-bento` grid. One card per data category that has content:
  - Providers — a chip per provider in `data.providers`, but `generic` is included only when it is the sole provider, so a repo with a real provider does not show a redundant Generic chip.
  - Inventory — a count per non-empty bucket ("1 agent", "2 commands", …), derived from array lengths (there is no count field in the data). The card hides if every bucket is empty.
  - Open TODOs — the count plus up to the first three texts. Hides if none.
  - Docs — the count. Hides if none.
  Each card scroll-links to its section. A card with no data is not appended.
- `renderInventory()` — iterates the buckets in a fixed display order (`agents`, `commands`, `skills`, `hooks`, `mcpServers`, `rules`). This order is a deliberate display choice and differs from the `_INV_BUCKETS` storage order in `base.py` (which has `skills` before `commands`); the renderer owns its own order. For each non-empty bucket it appends a labeled block ("Agents (1)") and one `itemRow` per item. Items arrive already sorted from the generator. Empty buckets are skipped.
- Truncation notice — if `data.generator.truncated` is true, a banner states that the dashboard was reduced to a summary for size, built with `textContent`. It renders into a dedicated host placed immediately after `<nav>` (before Overview), so it never displaces the sticky header.

**`dashboard.html.tmpl`** adds an `Inventory` nav link, a `<section id="inventory">` with a host div between Overview and Docs, and a banner host right after `<nav>`. The `#acc-overview` host already exists.

**`styles.css`** adds `.acc-bento` (a responsive grid via `grid-template-columns: repeat(auto-fill, minmax(200px, 1fr))`), `.acc-card`, and `.acc-chip`, reusing the existing color tokens. No new color scheme.

### Generator (`src/acc/generate.py`)

- `source.pathPrefix` — the posix relative path from the dashboard's output directory to the repo root, computed with `os.path.relpath(root, out_dir)` and normalized to posix separators. It is the general relative path, not a hard-coded `".."`: a provider-folder owner yields `".."`, `--out .` yields `"."`, a nested out dir yields `"../.."`. If `os.path.relpath` raises (for example an out dir on a different Windows drive than the root), `pathPrefix` is set to `""` and the renderer falls back to plain-text paths. The value is `path` only — never used as HTML.
- Size budget — after the full HTML is rendered, measure its UTF-8 byte length:
  - over 2 MB (`_TRUNCATE_BYTES = 2_000_000`): rebuild the island in summary-only form and re-render. The reducer **deep-copies the full data and blanks only known heavy values, it does not delete keys or rebuild from a whitelist**: every inventory and doc `summary` becomes `""`, every `docs[].html` becomes `""`, and `search` becomes `[]`. Deep-copy-then-blank guarantees that every key and every optional field is preserved — inventory item shape (`{id, provider, type, typeLabel, title, path, summary}` plus the optional `config` MCP items carry), doc shape (`{id, title, path, summary, html}`), and TODO `{text, path}` — so `validate()` and `assert_no_secrets` still pass on the reduced object. `generator.truncated` is set to `true`. `validate()` is re-run on the exact reduced object before it is written. Log the final reduced byte size; if it is still over 2 MB, log a warning (the skeleton is the floor — there is no further truncation).
  - over 1 MB (`_WARN_BYTES = 1_000_000`) and not truncated: log a warning with the byte size and keep the full island.
  Both thresholds key off the same measured size, so the mode is a deterministic function of the input.

### Schema (`src/acc/schema.py` and the data dict)

- `source` gains `pathPrefix` (string).
- `generator` gains `truncated` (bool, default `false`).
- Item and bucket shapes are unchanged in both modes. Summary-only mode blanks values within the existing shapes; it never adds or removes a key. `_REQUIRED_TOP`, `validate()`, and `assert_no_secrets` are unchanged. Counts are renderer-derived from array lengths; no count field is added.
- The generator guarantees `source.pathPrefix` and `generator.truncated` on every render, so the renderer's missing-field guards are a safety net for older or hand-built islands rather than the normal path.

### Data flow

`island JSON → parse → renderHead · renderOverview · renderInventory · renderDocs · renderTodos → wireSearch`. The renderer is a pure function of the island, runs offline, and adds no network calls. The size-budget branch runs entirely in the generator before the file is written.

## Security and determinism

- XSS posture is unchanged. Every author-derived value goes through `textContent`. The single `href` is built from `item.path` and the generator-computed `pathPrefix` combined, with every segment of the combined path passed through `encodeURIComponent` (preserving only `.`/`..`), so neither a reserved character in a filename nor a scheme-looking directory name in the prefix can produce a `javascript:`/`data:` href. `item.path` is not HTML-escaped today (`_escape_text_fields` escapes only `title` and `summary`), which is correct here: `textContent` makes the displayed path safe, and segment URL-encoding makes the `href` safe. No `innerHTML`.
- The reduced island blanks values within existing shapes, so the redaction guarantees and the `assert_no_secrets` tripwire still hold in both modes.
- Determinism holds: section and bucket display order are fixed constants, `pathPrefix` is a pure function of `(root, out_dir)`, and the truncation mode is a pure function of the measured size. Two runs on the same input produce byte-identical output.

## Testing

TDD, stdlib `pytest` for the generator and contract layer, Playwright for DOM behavior.

Python HTML-string / contract assertions (`tests/test_render.py`, `tests/test_generate.py`, `tests/test_schema.py`):

- The template carries the `Inventory` section, the nav link, and the banner host; `app.js` defines `renderOverview`, `renderInventory`, and `itemRow`; `styles.css` carries the bento classes.
- `source.pathPrefix` is `".."` for a provider-folder owner, `"."` for `--out .`, and the right value for a nested out dir.
- A path with reserved characters (for example `docs/a#b.md`) survives into the island unmangled, so the renderer has the raw value to encode.
- Size budget: a large in-test fixture pushes the island over each threshold. Between 1 and 2 MB logs a warning (via `caplog`) and keeps the full island. Over 2 MB sets `generator.truncated`, blanks `summary`/`docs[].html`/`search`, keeps all keys and shapes, and the reduced object still passes `validate()`. Under 1 MB does neither.
- The new `source.pathPrefix` and `generator.truncated` fields pass validation; determinism and packaging tests stay green.

Playwright DOM tests (`tests/test_render_dom.py`):

- Load the rendered HTML with `page.set_content(html)` (no server, no `file://`), then assert real DOM behavior: the bento cards render with the right counts; the Inventory view shows the items grouped by type with provider chips; a path link's `href` attribute is the correctly per-segment-encoded relative URL (including the reserved-character case); typing in the search box filters the visible rows; a truncated island renders the summary banner.
- Playwright is declared as a test-only optional dependency (a `test` extra in `pyproject.toml`); CI installs the browser (`playwright install chromium`) and runs this file. Runtime packaging is untouched.

Manual acceptance: a Playwright screenshot of a multi-provider dashboard, as a final visual confirmation.

## What Phase 3 leaves for later

- Expandable item detail and inline rendering of the sanitized markdown `html` field.
- The relationship Map (`relationships` stays `[]`).
- Data sources for `recentDocs`, current milestone, and last decision, and the Overview cards that would show them.
- Wiring `generator.rendererDigest` (still an empty string) to a hash of the renderer assets.
- The three-tier refresh, the `/dashboard` command, and the skill and plugin packaging (Phase 4).
