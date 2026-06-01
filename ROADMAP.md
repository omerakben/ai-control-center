# Roadmap

Agent Context Center maps a repo's scattered AI context files into one offline HTML
dashboard. This is the plan. Items beyond Now are planned, not promised, and carry no
dates.

## Now

Shipped and stable.

- Deterministic, byte-stable `dashboard.html` generation from `acc --root .`.
- First-class adapters for Claude Code, Codex, and Cursor, plus a generic markdown index
  for any other `.md`.
- Redaction before rendering: secret-shaped-string scanner, structured-config allowlist,
  and an output tripwire.
- Inline reading pane with a sanitized markdown subset rendered via `textContent`.
- Graduated truncation so large repos still produce a usable, bounded file.
- `acc doctor` findings report with `--strict` and `--json`.
- CI drift-check workflow template under `templates/refresh/`.
- TUEL theme (emerald, teal, navy).

## Next

Planned. Order is rough and may change.

- First-class adapters for `GEMINI.md` and `.github/copilot-instructions.md` (today these
  files land in the generic markdown index, not provider-classified).
- Richer `acc doctor` checks: broader broken-link detection and cross-file conflict
  detection.
- JSON export of doctor findings, shipped as the `doctor.v1` schema.
- A provider compatibility matrix in the docs.
- A published, reusable GitHub Action (today only a copyable workflow template exists).
- PRD and ADR classification (the schema has buckets, but generic markdown currently
  lands in `references`).

## Later

Exploratory. No commitment.

- Optional model-generated summaries, run only after redaction.
- Repo comparison over time.
- PR-comment summaries.
- VS Code integration.
- A local desktop wrapper.
