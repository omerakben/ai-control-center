# Agent Context Center (acc)

A stdlib-Python tool that scans a repository's AI-assistant configuration (Claude Code,
Codex, Cursor) and generates a deterministic, single-file, offline HTML dashboard of what
the repo declares — agents, skills, hooks, commands, MCP servers, rules, docs, and open
TODOs. It maps and reviews the AI context; it does not run or control agents. Public repo:
`omerakben/agent-context-center` (the `acc` CLI stands for Agent Context Center).

> The generated dashboard for this repo is [`.claude/dashboard.html`](.claude/dashboard.html).
> Open it in a browser; run `/dashboard` (or `acc --root .`) to refresh it.

## What this is

- A generator (`src/acc/`) reads the repo, normalizes each provider through an adapter,
  and emits one self-contained `dashboard.html` with a JSON data island plus a vanilla-JS
  renderer. No build step, no runtime dependencies, no network.
- Output is **deterministic**: every list is explicitly sorted, so repeated runs are
  byte-identical.
- The renderer is **textContent-only**: no `innerHTML` / `outerHTML` / `insertAdjacentHTML`
  (a CI guard greps `app.js`). Author-derived text is `html.escape`-d at build and
  `htmlUnescape`-d at display.
- Secrets are redacted at extraction; a tripwire re-scans the assembled output.

## Architecture

- `src/acc/generate.py` — orchestration: scan, per-provider normalize, merge, escape,
  build the search index, build relationships, assemble + validate + render the island.
- `src/acc/adapters/` — `claude.py`, `codex.py`, `cursor.py`, `generic.py` over `base.py`.
- `src/acc/schema.py` — top-level shape + search-record + relationship validation; the
  redaction tripwire.
- `src/acc/templates/` — `dashboard.html.tmpl`, `app.js`, `styles.css`.
- `tests/` — flat pytest suite incl. a real-Chromium Playwright DOM test
  (`test_render_dom.py`) and the innerHTML CI guard (`test_appjs_guard.py`).

## Current state

- Phases 1–3 (schema/generator/adapters/renderer) and Phase 4a (Find omnibox) are merged
  to `main`. Phase 4b (Relationships / cross-references) is in progress on
  `feature/phase-4b-relationships` — spec at `docs/specs/phase-4b-relationships.md`.

## Codex setup

- Model `gpt-5.5`, reasoning effort `xhigh` (see `.codex/config.toml`). Sandbox
  `workspace-write`, approvals `on-request`.
- MCP servers are disabled by default. Enable with `/codex-config enable-mcp <name>`
  (context7 for docs, playwright for UI testing).

## Conventions

- Stdlib Python only (3.12+), type hints, no third-party runtime deps in the generator.
- Preserve the determinism and textContent-only invariants in every change.
- No secrets in the repo; use a local `.env` and gitignore it.
- Verify renderer changes in a browser (or the Playwright DOM test) before claiming the UI
  works.
