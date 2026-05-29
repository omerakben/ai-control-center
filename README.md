# AI Control Center

One self-contained HTML file that turns a repo's scattered AI markdown into a control center a human can actually navigate.

> Status: design stage. The [design spec](docs/superpowers/specs/2026-05-29-ai-control-center-design.md) is complete; implementation has not started. This README describes where it is headed.

## The problem

Markdown is the right format for AI agents. Config, intent, decisions, and capability definitions live in `CLAUDE.md`, `AGENTS.md`, Cursor rules, skills, agents, hooks, commands, MCP config, PRDs, and ADRs. Agents read and write it well.

Humans don't. Once a repo holds dozens of markdown files spread across `.claude/`, `docs/`, and the tree, you lose track of what exists, how it connects, what was decided, and where the project stands.

## The idea

Keep markdown as the source of truth for the machine. Add one layer for the human: a single HTML dashboard that mirrors the markdown and makes it navigable. You open one file and see scope, the inventory of skills/agents/hooks/commands/MCP/rules, PRDs, decisions, the doc index, project state, and how the pieces relate.

## What makes it different

- One standalone HTML file. Opens from `file://` with no server, no build, no framework, and nothing added to your repo at runtime.
- Lives under the AI-provider folder (`.claude/`, `.codex/`, `.cursor/`), so it stays inert to any web build instead of colliding with it.
- Committed and shared, treated like `CLAUDE.md`, so it travels with the repo.
- Deterministic output, so re-stamping does not churn your diffs.
- Redaction at extraction, so MCP tokens and other secrets never get baked into a file you push.
- Multi-provider: first-class support for Claude Code, Codex, and Cursor, with a generic fallback for any other repo.

## How it works

A bundled, offline `python3` generator scans the repo, runs a per-provider adapter to map native conventions into one schema, redacts secrets, and stamps a single HTML file with the data inlined as a JSON island. The renderer builds the view from that island and gives you client-side search. Refresh runs three ways: an explicit command, an automatic re-stamp when an agent edits markdown, and an optional git or CI hook.

Read the [full design spec](docs/superpowers/specs/2026-05-29-ai-control-center-design.md) for the schema, adapter interface, generation pipeline, and security model.

## Roadmap

v1: deterministic inventory, doc index, relationship list, project facts, three-tier refresh, redaction, sanitized rendering, three first-class adapters plus the generic fallback, project level only.

Later: a global cross-repo view, an interactive relationship graph, and richer interpretation of workflows.

## Distribution

Ships as a standalone skill plus a marketplace plugin. The skill, the generator, and the HTML it produces are the whole product.
