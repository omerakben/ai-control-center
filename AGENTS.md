# html-dash

HTML dashboard. Greenfield — stack not yet fixed.

## What this is

A dashboard UI delivered as HTML. Framework and data sources are undecided; default to vanilla HTML/CSS/JS until a choice is made.

## Codex setup

- Model: `gpt-5.5`, reasoning effort `xhigh` (see `.codex/config.toml`).
- Sandbox: `workspace-write`. Approvals: `on-request`.
- MCP servers are disabled by default. Enable with `/codex-config enable-mcp <name>` (context7 for docs, playwright for UI testing).

## Conventions

- No secrets in the repo. Use a local `.env` and gitignore it.
- Verify changes in a browser before claiming the UI works.

## Open decisions

- [ ] Framework: vanilla vs light framework (Alpine, htmx, lit) vs React.
- [ ] Data source for dashboard widgets.
- [ ] Build/serve approach (static files vs dev server).
