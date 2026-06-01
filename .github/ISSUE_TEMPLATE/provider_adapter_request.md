---
name: Provider adapter request
about: Ask for first-class support for an AI tool's context files
labels: adapter
---

## Which tool

<!-- e.g. Gemini CLI, GitHub Copilot, Aider, Continue, Windsurf, ... -->

## Which files should acc read

List the exact repo-relative paths and what each one declares. Examples:

- `GEMINI.md` — top-level instructions
- `.github/copilot-instructions.md` — repo instructions
- `<dir>/<file>` — agents / skills / commands / rules / hooks / MCP servers / config

## What should land in the dashboard

<!-- For each file above: is it an instruction doc, an agent, a skill, a command,
     a rule, a hook, an MCP server declaration, or generic docs? -->

## Notes

<!-- Format details that matter: YAML frontmatter keys, a TOML/JSON config shape,
     a description field to surface, anything that affects parsing or redaction.
     A link to the tool's own docs for these files helps a lot. -->

<!-- Status note: GEMINI.md and .github/copilot-instructions.md are picked up today
     as GENERIC markdown, not provider-classified. First-class adapters for them
     are Planned. -->
