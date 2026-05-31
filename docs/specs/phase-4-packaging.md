# Phase 4 — packaging: skill + marketplace plugin (design brief)

Date: 2026-05-31
Status: locked for build (pending design-critique reconciliation)
Builds on: the approved v1 design (`docs/superpowers/specs/2026-05-29-ai-control-center-design.md`),
sections "Architecture → Components/Refresh" and "Distribution".

This is the second half of Phase 4. Phases 1–3, 4a (Find), 4b (Relationships) are
merged: the generator, adapters, renderer, search, and relationships are done and
green (209 tests). What remains is the **distribution and refresh** layer the design
always called for: ship the product as a public Claude Code **skill + marketplace
plugin**, with the three-tier refresh, and make the repo installable and shareable.

## Definition of done

A friend runs two commands and has a working tool, offline, no build step:

```
/plugin marketplace add omerakben/ai-control-center
/plugin install ai-control-center@ozzy-skills
```

Then `/dashboard` (or the agent, after editing AI markdown) stamps a deterministic,
redacted, self-contained `dashboard.html` under the project's provider folder.

## Hard invariants carried forward (non-negotiable, must survive packaging)

- Deterministic, byte-stable output (re-stamp produces no diff without content change).
- Redaction at extraction + the assembled-output tripwire (`assert_no_secrets`).
- `textContent`-only render; no `innerHTML`/`outerHTML`/`insertAdjacentHTML` (CI guard).
- Stdlib Python 3.12+ only at runtime; zero third-party deps; one self-contained file.
- Offline by default; no network in the generator or the install path.

## Layout decision — one repo is both the marketplace and the single plugin

The public repo `omerakben/ai-control-center` doubles as a single-plugin marketplace.
Both manifests live in `.claude-plugin/` (no conflict). The marketplace entry's
`source` is `"./"` (the repo root), so installing clones the whole repo into the
plugin cache — which is exactly why the generator at `src/acc` is available offline
at `${CLAUDE_PLUGIN_ROOT}/src/acc` with **no vendoring and no duplication**.

```
ai-control-center/                 # repo root == marketplace root == plugin root
├── .claude-plugin/
│   ├── plugin.json                # plugin manifest (name: ai-control-center)
│   └── marketplace.json           # marketplace catalog (name: ozzy-skills)
├── commands/
│   └── dashboard.md               # /dashboard — required refresh tier (active)
├── skills/
│   └── ai-control-center/
│       └── SKILL.md               # agent entry point (active)
├── templates/refresh/             # opt-in refresh tiers (NOT auto-active)
│   ├── README.md                  # what each template is + how to enable
│   ├── git-post-commit            # git hook: re-stamp + stage on commit
│   ├── claude-file-write-hook.json# PostToolUse(Write|Edit) snippet for settings.json
│   └── ci-drift-check.yml         # GitHub Actions: recompute sourceDigest, fail on drift
├── src/acc/…                      # the generator (already built); + new __main__.py
├── tests/ docs/ README.md LICENSE pyproject.toml
```

Naming (genuine choice; chosen for extensibility, documented so it is trivially
renamable — `/plugin marketplace add` keys off the repo URL, not the marketplace
`name`, so a later rename does not break friends' installs):
- marketplace `name`: **`ozzy-skills`** (owner: Omer Akben) — a personal catalog that
  can hold more plugins later, matching "publish all our skills".
- plugin `name`: **`ai-control-center`**.
- install suffix therefore reads `ai-control-center@ozzy-skills`.

## Offline generator invocation (the load-bearing mechanism)

The command and skill run the bundled generator against the **user's project**, never
the plugin dir, with the plugin's own copy of the code on `PYTHONPATH`:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/src" python3 -m acc.cli --root "${CLAUDE_PROJECT_DIR}"
```

- `${CLAUDE_PLUGIN_ROOT}` → the cached plugin dir (expands in commands and hooks).
- `${CLAUDE_PROJECT_DIR}` → the repo the user is working in (the scan target).
- Add `src/acc/__main__.py` so `python3 -m acc` is equivalent to `python3 -m acc.cli`
  (ergonomic; `-m acc.cli` already works because `cli.py` has the `__main__` guard).
- No `pip install`, no editable install, no network. Stdlib only.
- Preflight: if `python3` is missing, fail with a one-line actionable message
  ("AI Control Center needs python3 (3.12+) on PATH"), never a stack trace.

## Refresh — three tiers, exactly as the design says

1. **Required (active): `/dashboard`** — `commands/dashboard.md`. Runs the invocation
   above, prints the written path + `sourceDigest` + scanned-file count, re-stamps an
   existing dashboard in place. `disable-model-invocation: false` so the agent can call
   it too. `allowed-tools: [Bash, Read]`.
2. **Default (active, behavioral): agent re-stamps** after it edits AI markdown —
   instructed in `SKILL.md`. No hook required.
3. **Optional (opt-in templates, NOT shipped active):**
   - `git-post-commit` — re-stamps and `git add`s the dashboard on commit.
   - `claude-file-write-hook.json` — a `PostToolUse` matcher on `Write|Edit` the user
     pastes into their own `settings.json`/project `.claude/settings.json` to re-stamp
     on markdown edits.
   - `ci-drift-check.yml` — recomputes `sourceDigest` in CI and fails if the committed
     dashboard is stale (drift guard for shared repos).
   Shipping these as files under `templates/` (not `hooks/hooks.json`) is deliberate:
   a plugin's `hooks/hooks.json` activates on enable, which would silently regenerate
   the dashboard on every edit. v1 keeps hooks opt-in (auto-install is a v2 item).

## SKILL.md — the agent entry point

`skills/ai-control-center/SKILL.md`. Description triggers on: generate/refresh/open an
"AI control center" or dashboard of the repo's AI config; after editing CLAUDE.md /
AGENTS.md / skills / agents / hooks / commands / MCP / rules. Body: run the offline
invocation; surface the path; re-stamp on markdown edits; the optional-summary rule
(the model may only write prose over **already-redacted** text and must never
re-introduce a secret-shaped value or raw HTML — redaction and textContent-only are
upstream guarantees the agent must not undo); point to `/dashboard` and the opt-in
templates. Keep it short and specific (writing-rules apply).

## Versioning

First stable public release: bump `0.1.0 → 1.0.0` in `src/acc/__init__.py`,
`pyproject.toml`, `plugin.json`, and the marketplace entry — kept in lockstep.
`generator.version` is embedded in output, so **regenerate the committed dogfood
`.claude/dashboard.html`** after the bump (expected, deterministic diff). The `"0.1.0"`
strings in `tests/test_schema.py` / `tests/test_render.py` are fixture literals, not
assertions on generator output, so the bump does not break them (verify in the gate).

## README + discoverability

The current README says "design stage … implementation has not started" — stale and
wrong. Rewrite to a shipped-v1 README: one-paragraph what-it-is, the two-command
install, `/dashboard` usage, the `acc` CLI alternative for non-plugin users, the four
guarantees (deterministic / offline / redaction / XSS-safe), the opt-in refresh
templates, the screenshot (`acc-dashboard-multi.png`), spec link, MIT. Link the root
`AGENTS.md` to `.claude/dashboard.html` so a human finds the file despite the dot-folder.
Writing-rules apply (flat, specific, no banned vocabulary, no rule-of-three padding).

## Reversibility / publish posture

- Distribution is git only: "publish" = push to the public repo; install keys off the
  repo URL. Fully revertable. **No PyPI release** in this pass (a version number on a
  public index is effectively irreversible; not needed for the plugin path).
- Ozzy has explicitly authorized finalize+publish for this session (take-ownership,
  "remote-control finalize", monitoring via GitHub). Process is still accountable:
  feature branch → full adversarial review gate (the step that caught Phase 1's XSS and
  Phase 2's secret leak) → comprehensive PR as the audit record → merge once green →
  tag `v1.0.0` → end-to-end install check as a friend would.

## Design-critique reconciliation (2026-05-31, before build)

Debated by an independent Codex review (gpt-5.5) + a 3-lens adversarial workflow.
Core structure validated sound (repo-root plugin, `source:"./"`, both manifests,
cache-layout offline invocation proven to scan `${CLAUDE_PROJECT_DIR}` with no install,
opt-in-templates claim, 1.0.0 bump). Changes folded in before build:

- **BLOCKER — version-blind preflight.** The generator uses PEP 604 `X | None`
  annotations with no `from __future__ import annotations`, so they evaluate at import.
  Stock macOS `python3` is 3.9.6 → import raises a raw `TypeError`, defeating the
  "never a stack trace" promise for the most common friend install (proven at runtime).
  Fix: the command/skill probe `python3.13 python3.12 python3`, select the first
  interpreter `>=3.12`, and on none-found print one actionable line (incl. a Homebrew
  hint) instead of running Python. Keep `requires-python = ">=3.12"` (honest: tested
  there); a packaging test imports every `acc` module so the floor is enforced.
- **BLOCKER — gitignored secret/local files feed `sourceDigest`.** `scan_files` filters
  only directory names, so `.env`, `.claude/settings.local.json`, and
  `.claude/scheduled_tasks.lock` are hashed into the committed, public `sourceDigest`
  even though no adapter renders them (claude adapter reads only `settings.json`/
  `.mcp.json`; generic reads only `.md`). A SHA-256 leaks nothing directly, but a public
  artifact's hash then depends on a developer's private files and churns across machines.
  Fix: hard-exclude these files in `scan_files` (name match: `.env`, `.env.*` except
  `*.example/sample/template`, `settings.local.json`, `scheduled_tasks.lock`, `.DS_Store`)
  + add `.serena`/`.playwright-mcp` to dir excludes. Tests: planted secret files neither
  render nor change `sourceDigest`.
- **CONCERN — `/dashboard` output contract.** CLI prints only the path. Add `--json`
  (and a richer human line) surfacing `dashboardPath`, `sourceDigest`, `scannedFileCount`,
  `providers`, `truncated` via a `generate_result()` (and keep `generate()->Path` for
  back-compat) so the command reports without re-parsing HTML.
- **CONCERN — SKILL summary path could bypass the tripwire.** `assert_no_secrets` only
  fires inside `generate()`. SKILL.md must state the agent's ONLY summary mechanism is to
  edit the **source markdown** and re-run the generator (redaction + tripwire re-fire);
  it must never hand-edit `dashboard.html`, and — because the prose matcher is
  high-precision, not an entropy scanner — must describe intent only and never copy,
  quote, or paraphrase a literal value from a config/env/header/URL.
- **CONCERN — version-bump diff scope.** The bump changes three committed things
  deterministically: `generator.version`, `sourceDigest` (because `pyproject.toml` +
  `__init__.py` are scanned inputs), and the rendered pyproject/`__init__` snippet blocks.
  The gate diffs the regenerated dogfood for exactly these + no reordering.
- **CONCERN — dogfood already stale on HEAD** (a doc changed post-`7c9fc0d` without a
  re-stamp). Regenerate the dogfood to match HEAD as part of this branch so the diff is
  clean; do it once after all source/doc edits land.
- **NIT — public artifact + docs embed the maintainer's absolute home path** (from
  shell snippets in the design docs). Scrub maintainer home paths from docs to
  repo-relative before regenerating, so the public dashboard does not carry the username.
- **NIT — README must not list redaction as a co-equal absolute guarantee.** Deterministic
  / offline / XSS-safe are firm; redaction is high-precision/best-effort on prose — phrase
  it honestly with a "review before publishing unusual repos" note.

## What the design-critique tried to break

1. Does `source:"./"` + repo-root plugin actually install and surface `/dashboard` and
   the skill? Any field wrong in either manifest that fails `/plugin` validation.
2. Does the offline invocation work from the *cache* layout (no PYTHONPATH preset, no
   editable install), scanning `${CLAUDE_PROJECT_DIR}` not the plugin dir?
3. Are the opt-in hooks truly inert until the user enables them (no `hooks/hooks.json`)?
4. Does shipping the whole repo leak anything? (`.claude/settings.local.json` is
   gitignored; fixtures hold only fake secrets already public.)
5. Does the 1.0.0 bump break determinism or the fixture tests; is the dogfood dashboard
   regenerated?
6. Is SKILL.md's trigger scoped (fires when wanted, not on every unrelated turn)?
7. Redaction + textContent-only + stdlib-only + single-file invariants all still hold.
