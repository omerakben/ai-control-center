# claude-codex-cursor

One repo, three providers: Claude Code, Codex, and Cursor.

## Run it

```bash
acc --root .
```

This repo has a `.claude/` directory, so the dashboard lands at `.claude/dashboard.html`.
The command prints the path and lists the providers it detected. Open the file in a
browser.

## What to look for

- **Providers**: `claude`, `codex`, and `cursor`, each detected from its own files.
- **Agents**: `migration-reviewer`, from `.claude/agents/migration-reviewer.md`. Its name
  and summary come from the frontmatter.
- **Rules**: the Cursor rule `style`, from `.cursor/rules/style.mdc`. Its summary is the
  `description` field in the frontmatter.
- **Docs**: the ADR at `docs/adr/0001-idempotency-keys.md`. It is indexed as generic
  Markdown and lands under references — `acc` does not classify ADRs as a distinct type
  yet, so it shows up as a doc entry, not a tagged decision.
- **Cross-references**: `CLAUDE.md` names the path `.claude/agents/migration-reviewer.md`,
  so the relationships view shows a reference edge from `CLAUDE.md` to that agent. Reference
  edges link a doc to an inventory item (agent, skill, hook, command, MCP server, rule) by
  its exact repo-relative path; doc-to-doc links are not built, so naming the ADR path does
  not create an edge.

## Files

```
CLAUDE.md
AGENTS.md
.cursor/rules/style.mdc
.claude/agents/migration-reviewer.md
docs/adr/0001-idempotency-keys.md
```
