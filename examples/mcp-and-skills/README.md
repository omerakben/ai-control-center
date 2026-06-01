# mcp-and-skills

A config-heavy repo: a hooks block, two MCP servers, and a skill. Shows how `acc` reads
`.claude/settings.json` and `.mcp.json`, and that `${ENV}` placeholders never reach the
output.

## Run it

```bash
acc --root .
```

The dashboard lands at `.claude/dashboard.html`. Open it in a browser.

## What to look for

- **Hooks**: one `PostToolUse (Edit)` hook from `.claude/settings.json`, with its command
  `npm run lint --silent`.
- **MCP servers**: `postgres` from `.claude/settings.json` and `filesystem` from
  `.mcp.json`. Each shows its `command` and `args`.
- **Skills**: `seed-db`, from `.claude/skills/seed-db/SKILL.md`, with its frontmatter name
  and description.

## On the `${PGPASSWORD}` placeholder

`.claude/settings.json` lists an `env` block with `"PGPASSWORD": "${PGPASSWORD}"` — an
environment-variable name, not a value. The generator allowlists MCP config to `command`,
`args`, `type`, and `url`. The whole `env` block is dropped before rendering: open the
`postgres` MCP server in the dashboard and you see only its `command` and `args`. The `env`
keys and the `${PGPASSWORD}` placeholder are not in the rendered config.

This holds for any value placed in a dropped config field, real or placeholder. It is a
property of the allowlist, not a full secret scanner. Free-form prose runs through a
separate high-precision scanner that favors precision over recall, so review a generated
dashboard before publishing one from a repo with unusual secrets.

## Files

```
CLAUDE.md
.claude/settings.json
.claude/skills/seed-db/SKILL.md
.mcp.json
```
