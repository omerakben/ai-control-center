# AI control center — Phase 2 (first-class provider adapters) design

Date: 2026-05-29
Status: approved for planning
Project: html-dash (AI Control Center)
Builds on: `2026-05-29-ai-control-center-design.md` (v1 design), Phase 1 (merged)

## Scope

Phase 2 adds three first-class provider adapters — Claude Code, Codex, and Cursor — that map native conventions into the superset schema's inventory. It activates the allowlist redaction tier for structured config, and produces one merged dashboard across every detected provider folder via the owner rule. The generic adapter stays as the fallback for everything else.

Phase 2 is data-only. The renderer still shows docs and TODOs (Phase 1). The bento Overview and Inventory views that surface this data are Phase 3. After Phase 2 the JSON island is richer; the visible page is unchanged.

Locked decisions from brainstorming:

1. Inventory parity per provider — list standard artifacts (name, native type label, path, redacted summary). No relationship extraction; the Map is Phase 3.
2. Fixtures are built in-test with reusable builder helpers (no committed fixture trees).
3. Data-only — no renderer changes in this phase.
4. `validate()` gains an `assert_no_secrets` tripwire that re-scans the serialized output.
5. Codex saved prompts map into the existing `commands` bucket with a native label, not a new bucket.
6. Owner precedence is `.claude` > `.codex` > `.cursor`, then `.ai-control-center`.

## Hard constraints carried from v1

- Stdlib only at runtime. No PyYAML, no third-party parsers. Codex TOML uses stdlib `tomllib`.
- Deterministic output: sorted collections, stable IDs, repo-relative POSIX paths, no timestamps or mtimes.
- Redaction at extraction. Structured config is allowlisted (fail closed); prose runs the secret scanner.
- One self-contained HTML file under the owning provider folder.

## Architecture

### New shared modules

**`src/acc/frontmatter.py`** — `parse_frontmatter(text: str) -> tuple[dict, str]`.

A minimal reader for the YAML subset that real Claude and Cursor artifacts use. It handles a leading `---` fence, `key: value` pairs, single/double-quoted strings, inline lists `[a, b]`, block lists (`- item` under a key), and booleans (`true`/`false`). It does not handle nested maps or anchors. A line it cannot parse is skipped, never raised. Returns the parsed fields and the body after the fence. When there is no fence, fields are `{}` and the body is the whole text.

This is the stdlib-safe answer to reading frontmatter without PyYAML. The fields the adapters consume are shallow (`name`, `description`, `model`, `tools`, `argument-hint`, `globs`, `alwaysApply`), which this subset covers.

**`src/acc/config.py`** — safe structured-config loaders and the allowlists.

- `load_json(path) -> dict` for `.mcp.json`, `.claude/settings.json`, `.cursor/mcp.json`. Returns `{}` on missing or malformed input.
- `load_toml(path) -> dict` over stdlib `tomllib` for `.codex/config.toml`. Returns `{}` on missing or malformed input.
- `MCP_ALLOWED = {"command", "args", "type", "url"}` (`type` is the real MCP-config transport key — stdio/http/sse) and any other per-config-type allowlists. Loaders never raise on bad input, and `as_dict()` coerces a well-formed-but-wrong-shape container so a broken config yields an empty result, not a crash.

### Adapters

Each adapter implements `detect(ctx) -> list[ProviderRoot]` and `normalize(ctx, root) -> dict` (a schema partial), reusing `ids`, `redaction`, `frontmatter`, `config`, and `markdown`. Adapters never import each other. Every item keeps its native type label.

**`src/acc/adapters/claude.py` — `ClaudeAdapter`**

- detect: a `.claude/` directory, or a root `CLAUDE.md`.
- inventory:
  - agents — `.claude/agents/*.md`; frontmatter `name`, `description`, `model`, `tools`. Type label "Claude agent".
  - commands — `.claude/commands/**/*.md`; frontmatter `description`, `argument-hint`. Type label "Claude command".
  - skills — `.claude/skills/*/SKILL.md`; frontmatter `name`, `description`. Type label "Claude skill".
  - hooks — from the committed `.claude/settings.json` `hooks` block only. `settings.local.json` is personal and gitignored, so it is skipped (project-level state, not personal). One item per configured hook (event + matcher + command). Type label "Claude hook".
  - mcpServers — from `.mcp.json` (repo root) and `.claude/settings.json` `mcpServers`. Servers are deduplicated by name; `.mcp.json` wins on conflict. Each passes through `allowlist_config(server, MCP_ALLOWED)`. Type label "MCP server".
- docs: `CLAUDE.md` (root or `.claude/`) as the provider instructions doc.

**`src/acc/adapters/codex.py` — `CodexAdapter`**

- detect: `.codex/config.toml`, or a root `AGENTS.md`.
- inventory:
  - mcpServers — `[mcp_servers.*]` tables from `config.toml`, each through the allowlist. Type label "MCP server".
  - commands — `.codex/prompts/*.md` saved prompts, mapped into the `commands` bucket with type label "Codex prompt".
- provider summary: non-secret config facts (`model`, `model_reasoning_effort`, `sandbox`, `approval_policy`) attach to the `ProviderSummary`, not to inventory.
- docs: `AGENTS.md` as the provider instructions doc.

**`src/acc/adapters/cursor.py` — `CursorAdapter`**

- detect: a `.cursor/` directory, or a `.cursorrules` file.
- inventory:
  - rules — `.cursor/rules/**/*.mdc`; frontmatter `description`, `globs`, `alwaysApply`. Legacy `.cursorrules` (a single file) becomes one rule item. Type label "Cursor rule".
  - mcpServers — `.cursor/mcp.json`, each through the allowlist. Type label "MCP server".

**`src/acc/adapters/generic.py`** stays as the fallback. It runs over the markdown not claimed by any first-class provider (README, `docs/`, loose files), so provider files are never listed twice.

### Detection, file-claiming, and merge

`generate.py` orchestrates:

1. Run every first-class adapter's `detect`. Collect the providers present and their roots.
2. Each first-class adapter claims the files under its provider root and emits a schema partial.
3. The generic adapter runs over the unclaimed markdown — it supplies the doc index, `project.title` (from README), and open TODOs across all docs.
4. Merge: inventory buckets and `providers[]` accumulate across adapters; provider instruction docs (`CLAUDE.md`, `AGENTS.md`) join the doc index. Project facts come from the generic pass.

Determinism holds because every collection is sorted by a stable key (path, then title) and IDs are content-derived.

### Owner rule (merged dashboard)

`detect_out_dir` is replaced by `resolve_owner(root, detected_providers, owner_override=None) -> Path`:

- Scan known provider folders (`.claude`, `.codex`, `.cursor`, `.ai-control-center`) for an existing `dashboard.html`.
- 0 existing — create under the highest-precedence detected provider folder (`.claude` > `.codex` > `.cursor`; if none detected, `.ai-control-center`).
- 1 existing — that file is the owner; update it.
- 2 or more existing — raise `OwnerAmbiguousError` listing the candidates. The CLI prints them and exits non-zero. `--owner <dir>` picks one and proceeds.

The owner dashboard always carries all detected providers in `providers[]` and their merged inventory.

### Schema superset

- `Item` gains `provider` (adapter id), `type` (native kind), and `typeLabel` (display string such as "Cursor rule"). It keeps `id`, `title`, `path`, `summary`.
- The six inventory buckets are unchanged: `agents`, `skills`, `hooks`, `commands`, `mcpServers`, `rules`. Codex prompts live in `commands`.
- MCP items expose the `type` (transport) and `url` keys only; auth, `env`, and `headers` never appear.
- `ProviderSummary` = `{id, displayName, root, detected}` plus optional non-secret config facts for Codex.
- `validate()` extends with `assert_no_secrets(data)`: it serializes the assembled data and re-runs the prose secret scanner; any surviving match raises `ValueError`. This is a final tripwire over the new structured-config path, independent of each adapter remembering to redact.

### Redaction

- Structured config (all MCP servers) is allowlisted to `{command, args, type, url}`. Everything else is dropped before it can reach the output. This tier fails closed.
- Hook commands and every frontmatter text field pass through `redact_text`.
- The `assert_no_secrets` tripwire is the backstop if any path is missed.

## Testing

TDD, stdlib `pytest`, hybrid in-test builders.

- `tests/builders.py` — `make_claude_repo`, `make_codex_repo`, `make_cursor_repo`, `make_multi_provider_repo`, `make_brownfield_repo`. Each stamps a realistic provider layout into `tmp_path`. Every fixture is non-git by default (no `.git` is created), so the non-git path is the baseline rather than a separate builder.
- `tests/test_frontmatter.py` — the parser: fenced and unfenced, quoted values, inline and block lists, booleans, malformed lines skipped.
- `tests/test_claude_adapter.py`, `test_codex_adapter.py`, `test_cursor_adapter.py` — detection, inventory mapping, native labels, and that fake secrets in MCP config or prose do not leak.
- `tests/test_owner_rule.py` — 0, 1, and 2-or-more existing dashboards; precedence; `--owner` override; the ambiguous error.
- `tests/test_generate.py` (extended) — a multi-provider repo yields one merged dashboard with every provider; output stays byte-identical across two runs; allowlisted secrets never appear in the HTML, island, or search; generic does not re-list provider files; `assert_no_secrets` rejects a planted leak.
- `tests/test_schema.py` (extended) — the new `Item`/`ProviderSummary` fields and `assert_no_secrets`.

## What Phase 2 leaves for later

The full layout-B renderer with bento Overview and Inventory badges, the relationship-list Map, and client search over the new data are Phase 3. The size budget (warn at 1 MB, summary-only at 2 MB) is Phase 3. The three-tier refresh and the skill/plugin packaging are Phase 4.
