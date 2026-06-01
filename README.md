# Agent Context Center

AI agents have AGENTS.md. Humans need dashboard.html.

A repo's AI context lives in markdown: `CLAUDE.md`, `AGENTS.md`, Cursor rules, skills,
agents, hooks, commands, MCP config. Agents read that markdown fine. Humans lose the
thread once a repo holds dozens of these files. Agent Context Center scans the repo and
emits one self-contained HTML dashboard that mirrors what is there. Markdown stays the
source of truth; the dashboard is the human map.

![The dashboard rendered for a multi-provider repo](acc-dashboard-multi.png)

## Quickstart

Install the generator. It is stdlib Python 3.12+, no third-party dependencies.

```bash
pip install "git+https://github.com/omerakben/agent-context-center"
acc --root .
```

`acc --root .` writes `dashboard.html` into the auto-detected provider folder (e.g.
`.claude/dashboard.html`, or `.ai-control-center/` if no provider is found). It prints the
path, the source digest, the file count, and the providers. Open the printed path in a
browser. No server, no network.

Write the dashboard at the repo root instead:

```bash
acc --root . --out .
```

`--out` takes a directory, not a filename.

The dashboard header shows the repo name. It comes from the project manifest
(`pyproject.toml` `[project].name`, then `package.json` `name`) and falls back to the
directory name, so the committed output stays identical no matter what a clone directory
is called. Pin it explicitly with `--repo-name`:

```bash
acc --root . --repo-name my-repo
```

### Claude Code plugin

```text
/plugin marketplace add omerakben/agent-context-center
/plugin install ai-control-center@ozzy-skills
/dashboard
```

`/dashboard` runs the bundled generator. It needs `python3` 3.12+ on your PATH; if yours is
older (stock macOS ships 3.9), the command tells you instead of failing with a stack trace.

## What it finds

| Source | Status |
| --- | --- |
| Claude Code: `CLAUDE.md`, `.claude/agents`, `.claude/commands`, `.claude/skills` (SKILL.md), hooks + MCP from `.claude/settings.json` and `.mcp.json` | Supported today |
| Codex: `AGENTS.md`, `.codex/prompts`, `.codex/config.toml` (MCP + config facts) | Supported today |
| Cursor: `.cursorrules`, `.cursor/rules/*.mdc`, `.cursor/mcp.json` | Supported today |
| Generic markdown indexing for any other `.md` as docs | Supported today |
| Open TODOs (`- [ ]` checkbox lines only) | Supported today |
| Flat cross-references (a doc body naming an item's repo-relative path; config "declares" edges) | Supported today |
| Redaction before rendering (secret-shaped scanner + config allowlist + output tripwire) | Supported today |
| `GEMINI.md` and `.github/copilot-instructions.md` as first-class adapters | Planned (today: picked up as generic markdown) |
| PRD / ADR / decision / workflow classification | Planned (today: generic markdown lands in references) |
| Published, reusable GitHub Action | Planned (today: a copyable workflow template) |
| Health score | Planned (today: `acc doctor` reports findings, not a number) |
| JSON export beyond `doctor.v1` findings | Planned |

## Why this exists

AI tools read repo instruction files to do their work. Those files multiply across
`.claude/`, `.codex/`, `.cursor/`, and `docs/`, and no person tracks all of them. Humans
need one place to review what exists, what is stale, and what changed. The dashboard is a
single file you can open, read, diff, and commit alongside the markdown it describes.

## Guarantees

- Static HTML, offline, no network at runtime.
- No server, no database, no CDN dependency, no build step.
- No tracking, no telemetry.
- Redaction runs before rendering.
- Deterministic and byte-stable: re-stamping an unchanged repo produces identical HTML.
- `textContent`-only renderer — repo content cannot inject script into the file.
- Works air-gapped once installed locally.
- Stdlib Python 3.12+ only.

## What this is not

- Not an agent runtime or orchestrator.
- Not "control" of agents.
- Not a cloud service or SaaS.
- Not a replacement for markdown, Claude Code, Codex, Cursor, Copilot, or MCP.
- Not a full secret scanner.
- Not a policy engine or mission control.

It maps, inspects, summarizes, and source-links. It does not manage or run anything.

## acc doctor

`acc doctor` reads the repo and prints deterministic findings — no git history, no mtimes,
no network, no model judgment, so the same repo always yields the same report. It checks
for a stale dashboard (embedded digest differs from a fresh scan), a missing, unreadable,
or truncated dashboard, generator-version drift, weak metadata (an agent, skill, command,
or rule with no description), near-empty instruction files, large files, conservatively
detected broken relative markdown links, the count of redacted secret-shaped values, and
open `- [ ]` TODOs.

```bash
acc doctor --root .            # print findings
acc doctor --root . --strict   # exit 1 if any warning
acc doctor --root . --json     # a doctor.v1 report
```

Exit codes: `0` clean, or warnings without `--strict`; `1` warnings with `--strict`; `2`
execution error.

Sample text output:

```text
Agent Context Center — doctor
Root: /repo
Files scanned: 24 · providers: claude, codex
Dashboard: .claude/dashboard.html
Status: needs attention
Findings:
  ! [stale-dashboard] .claude/dashboard.html is stale (built from a1b2c3, current is d4e5f6) — re-run `acc --root .`.
  ! [weak-metadata] 2 agent/skill/command/rule file(s) have no description (e.g. .claude/agents/triage.md) — add a `description:` so humans and agents know the intent.
  · [open-todos] 5 open `- [ ]` TODO(s) found.
Next: run `acc --root .` to (re)generate the dashboard.
```

## For teams / CI

Commit `dashboard.html` next to the markdown it describes. A pull request then shows the
dashboard diff alongside the context changes, so a reviewer sees what moved without opening
each file.

A static `file://` page cannot tell it is stale, so refresh is explicit. Add a CI drift
check that regenerates the dashboard and fails if the committed copy fell behind:

```bash
acc --root .
git diff --exit-code -- '**/dashboard.html'
```

Or run `acc doctor --root . --strict`, which exits `1` on a `stale-dashboard` finding. A
copyable workflow lives at
[`.github/workflows/agent-context-dashboard.yml`](.github/workflows/agent-context-dashboard.yml).
It is a template you adapt; a published, reusable Action is planned.

## Security and redaction

Before anything reaches the file, structured provider config is allowlisted — only known
fields pass — and free-form prose runs through a high-precision secret-shaped-string
scanner. A tripwire re-scans the assembled output. This is not a full entropy scanner: a
high-entropy value with no telltale prefix can slip through. Review a generated dashboard
before publishing one from a repo with unusual secrets.

## Roadmap

See [ROADMAP.md](ROADMAP.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
