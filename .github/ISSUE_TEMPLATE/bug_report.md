---
name: Bug report
about: Something in acc or the generated dashboard does the wrong thing
labels: bug
---

## What happened

<!-- The behavior you saw. If the dashboard rendered something wrong, say which
     section (agents, skills, commands, hooks, MCP, rules, docs, TODOs, cross-references). -->

## What you expected

<!-- The behavior you expected instead. -->

## Steps to reproduce

```
# the exact command you ran, e.g.
acc --root .
acc doctor --root . --json
```

## Environment

- acc version: <!-- `pip show ai-control-center` -->
- Python: <!-- `python3 --version` (3.12+ required) -->
- OS:
- Provider folders present: <!-- .claude / .codex / .cursor / none -->

## Output

<!-- Paste the relevant stdout. For generation issues, the `acc --root . --json`
     blob (dashboardPath, sourceDigest, scannedFileCount, providers, truncated)
     is the most useful thing you can attach.
     Scrub anything sensitive before pasting — acc redacts the dashboard, not your terminal. -->
