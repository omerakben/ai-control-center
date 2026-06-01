---
name: ai-control-center
description: Generate, refresh, or open this repo's Agent Context Center dashboard — a single self-contained offline HTML file that inventories the repo's AI configuration (agents, skills, hooks, commands, MCP servers, rules, docs, open TODOs). Use when the user asks to build, refresh, regenerate, or view that dashboard, and to re-stamp it after editing the repo's AI markdown when a dashboard.html already exists under a provider folder.
version: 1.0.0
---

# Agent Context Center

One committed HTML file mirrors a repo's AI markdown so a human can navigate it.
Markdown stays the source of truth for the machine; the dashboard is the read view for
the person. The generator is stdlib Python 3.12+, runs offline, and produces
byte-stable output.

## Generate or refresh

Run the `/dashboard` command. It selects a Python 3.12+ interpreter, runs the bundled
generator against the user's project with no install and no network, and reports the
written path, `sourceDigest`, and scanned-file count. The dashboard is written under the
owning provider folder (`.claude/`, `.codex/`, or `.cursor/`), never the source tree, so
it stays inert to web builds.

If more than one provider dashboard already exists, the generator stops and asks for an
owner; re-run with `--owner <dir>`.

## Keep it fresh (the default tier)

After you edit this repo's AI markdown (CLAUDE.md, AGENTS.md, an agent, skill, hook,
command, MCP config, or rule) **and a `dashboard.html` already exists** under a provider
folder, re-run `/dashboard` so the human view stays in sync. Refresh is manual by
design: a static `file://` page cannot tell it is stale. For automatic refresh, point
the user at the opt-in templates in the plugin's `templates/refresh/` (a git post-commit
hook, a file-write hook snippet, and a CI drift check).

## Enriching the dashboard — the only safe path

The generator writes every field, redacts secrets at extraction, and re-scans the
assembled output with a tripwire. To add or improve a summary, **edit the source
markdown and re-run `/dashboard`** so redaction and the tripwire re-fire over your text.

- Never hand-edit `dashboard.html` or any generated file. A value written straight into
  the output bypasses redaction and the tripwire entirely.
- When you write prose into source markdown, describe purpose and intent only. Never
  copy, quote, or paraphrase a literal value from a config file, an env block, a header,
  or a URL. The prose redactor is high-precision, not an entropy scanner, so a bare
  high-entropy token with no telltale prefix can slip through — do not rely on it to
  catch a value you pasted.

## Invariants you must not undo

Deterministic output (re-stamping a clean repo produces no diff), redaction at
extraction, and a `textContent`-only render are guarantees the generator enforces. Do
not disable them, post-process the HTML, or inject raw markup. If a change would weaken
any of them, stop and surface it instead.
