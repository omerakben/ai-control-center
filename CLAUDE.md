# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`AGENTS.md` is the companion brief and `CONTRIBUTING.md` has the full extension guide; this file is the working summary plus the gotchas that bite first.

## What this is

`acc` (Agent Context Center) scans a repo's AI-assistant config — Claude Code, Codex, Cursor, generic markdown — and emits one deterministic, offline, single-file `dashboard.html`. Markdown stays the source of truth; the dashboard is the human map. It maps and reviews; it does not run or control agents. The package id is `agent-context-center`; the CLI is `acc`.

Stdlib Python 3.12+ only. No third-party runtime dependencies. No network at runtime, no build step, no server.

## Commands

```bash
pip install -e ".[test]"      # editable install + pytest/pytest-playwright
playwright install chromium   # once, for the real-browser DOM test

python -m pytest                          # full suite
python -m pytest tests/test_scan.py       # one file
python -m pytest tests/test_scan.py::test_name   # one test
python -m pytest -k redaction             # by keyword

acc --root .                  # generate into the auto-detected provider folder; prints path + digest
acc --root . --out .          # write ./dashboard.html at repo root (--out is a DIRECTORY, not a filename)
acc --root . --json           # machine-readable: dashboardPath, sourceDigest, file count, providers
acc doctor --root .           # deterministic findings report (exit 0 unless execution error -> 2)
acc doctor --root . --strict  # exit 1 on any warning
acc doctor --root . --json    # doctor.v1 report
```

## Dogfood + CI (the thing that breaks first)

This repo runs `acc` on itself. `.claude/dashboard.html` is committed and `.github/workflows/agent-context-dashboard.yml` runs two jobs on every PR:

1. **freshness** — regenerates the dashboard and fails if the committed copy differs.
2. **doctor** — `acc doctor --root . --strict`, fails on any warning.

So after any change to scanning, adapters, schema, or templates, **regenerate and commit the dashboard** (`acc --root .` then commit `.claude/dashboard.html`) and keep `acc doctor --root . --strict` clean — passing tests are not enough. (`docs/demo/dashboard.html` is a separate GitHub-Pages demo, not the freshness target.)

## Architecture

The flow lives in `src/acc/generate.py::_assemble` (read-only core, shared by `generate_result` and `doctor`):

1. **scan** (`scan.py`) — walk the repo into a file list.
2. **detect + resolve owner** — `detect_providers` by precedence (claude → codex → cursor); `resolve_owner` picks the output folder (an existing dashboard, else the top detected provider's dir, else `.agent-context-center/`). Two committed dashboards raise `OwnerAmbiguousError` unless `--owner` is given.
3. **normalize** — each first-class adapter (`adapters/claude.py`, `codex.py`, `cursor.py`) maps native files into the shared `inventory` + `docs` schema; `generic.py` indexes only the markdown not claimed by a provider folder/marker.
4. **merge → escape → search → relationships** — `_merge_parts` concatenates and sorts; `_escape_text_fields` redacts-then-escapes every author-derived display field; `_build_search` and `_build_relationships` run; then transient `_searchBody` / `_refScanBody` / `_rawBody` keys are stripped so they never reach the island.
5. **redact paths → validate** — `_redact_paths` masks author-controlled paths/evidence; `schema.py::validate` checks shape and runs the secret tripwire.
6. **render** (`render.py`) — substitute CSS, `app.js`, schema version, and the canonical-JSON data island into `templates/dashboard.html.tmpl`. `generate_result` also runs `_reduce_for_size` (graduated trim: bodies → capped summaries → search body → blanked summaries) when output exceeds the byte budget.

Key modules: `schema.py` (shape + tripwire), `redaction.py` (secret-shaped scanner), `config.py` (allowlisting helpers `safe_mcp`/`load_toml`/`as_dict`), `ids.py` (`stable_id` = sha256 of raw path, so ids never leak paths), `digest.py` (`source_digest`), `doctor.py` (detectors → `Finding`s). The renderer is `templates/app.js` (vanilla JS, no framework).

Doctor finding codes: `stale-dashboard`, `missing-dashboard`, `truncated-dashboard`, `generator-version`, `weak-metadata`, `near-empty-instruction`, `large-file`, `broken-link`, `redactions`, `open-todos`.

## Load-bearing invariants (do not break)

- **Deterministic + byte-stable.** Sort every list explicitly — `canonical_json` uses `sort_keys=True`, which sorts dict keys but not list order. Re-stamping an unchanged repo must produce an identical file.
- **textContent-only renderer.** No `innerHTML` / `outerHTML` / `insertAdjacentHTML` in `app.js`; `tests/test_appjs_guard.py` greps for them and fails CI. Repo content must not be able to inject script into the committed HTML.
- **Redaction runs before render**, at extraction, through `redaction.py` and the `config.py` allowlist. The output tripwire in `schema.py` is a backstop, not the primary defense — display fields that bypass markdown rendering must be redacted+escaped centrally (`_redact_escape`).
- **Stdlib only.** No third-party runtime deps; test-only packages go in the `[test]` extra.
- **Honest classification.** Only label what an adapter actually parses; unrecognized files fall through to the generic markdown adapter, never mislabeled.

## Extending

- **New adapter** — implement the `ProviderAdapter` protocol in `adapters/base.py` (`id`, `display_name`, `detect`, `normalize`); build items with `empty_inventory()`/`empty_docs()`/`make_item()` (never hand-roll item dicts — `make_item` assigns the stable id + type label); read structured config via `config.py` helpers and prose via `redact_text`. Add a builder in `tests/builders.py` and a `tests/test_<provider>_adapter.py`.
- **New doctor detector** — add to `doctor.py`, yield `Finding`s, deterministic only (no git history, mtimes, network, or model judgment); `warn` only for something actionable (`--strict` exits 1 on any warning), `info` for counts. Test in `tests/test_doctor.py`.
- Test repos are built in code (`tests/builders.py`), not checked in as trees.

## Codex setup

`gpt-5.5`, reasoning effort `xhigh`, sandbox `workspace-write`, approvals `on-request` (`.codex/config.toml`). MCP servers are disabled by default; enable with `/codex-config enable-mcp <name>` (context7 for docs, playwright for UI testing).
