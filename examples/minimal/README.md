# minimal

The smallest input `acc` accepts: one `CLAUDE.md`, one docs note, one open TODO.

## Run it

```bash
acc --root .
```

`acc` writes `dashboard.html` into the detected provider folder. A `CLAUDE.md` at the root
counts as the Claude Code provider, so the dashboard lands at `.claude/dashboard.html` even
though this repo has no `.claude/` directory of its own. The command prints the exact path.
Open it in a browser.

## What to look for

- **Scope** comes from the `CLAUDE.md` heading and lead paragraph.
- **Docs** lists `docs/storage.md`.
- **Open TODOs** shows the one `- [ ]` line from `docs/storage.md`. Plain `TODO:` comments
  are not counted; only Markdown checkbox lines are.

## Files

```
CLAUDE.md
docs/storage.md
```
