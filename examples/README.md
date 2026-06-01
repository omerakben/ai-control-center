# Examples

Three tiny, self-contained repos that show what `acc` picks up. Each one is safe to copy,
holds no real secrets, and works offline. Install the CLI once:

```bash
pip install "git+https://github.com/omerakben/ai-control-center"   # stdlib only, no deps
```

Then `cd` into any example and run:

```bash
acc --root .
```

`acc` prints the path it wrote, a source digest, the file count, and the providers it
detected. Open the generated `dashboard.html` in a browser — it needs no server.

## The three examples

- [`minimal/`](minimal/) — the smallest case: one `CLAUDE.md`, one docs note, one open
  TODO. Shows scope, the doc index, and the TODO list with nothing else in the way.
- [`claude-codex-cursor/`](claude-codex-cursor/) — three providers in one repo: Claude
  Code, Codex, and Cursor. Shows the per-provider inventory, a Claude agent, a Cursor rule
  with a frontmatter description, and a docs entry.
- [`mcp-and-skills/`](mcp-and-skills/) — config-heavy: a `.claude/settings.json` with a
  hooks block and an MCP server, a Claude skill, and a root `.mcp.json`. Shows how hooks
  and MCP servers land in the inventory and how `${ENV}` placeholders stay out of the
  output.

Each example folder has its own `README.md` with the same instructions and what to look
for.

## A note on the MCP example

`mcp-and-skills/.claude/settings.json` references a database password as
`"${PGPASSWORD}"` — an environment-variable placeholder, never a real value. The generator
allowlists MCP config to `command`, `args`, `type`, and `url`; the `env` block is dropped
before anything reaches the HTML. The placeholder is there to show that even a referenced
secret name does not appear in the dashboard.
