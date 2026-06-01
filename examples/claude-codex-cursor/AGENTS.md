# Checkout API (Codex)

Same repo as `CLAUDE.md`, read by Codex. TypeScript, Node 22, Express, Postgres.

## Conventions

- Source in `src/`, tests in `tests/`, one test file per route.
- Run `npm run typecheck && npm test` before opening a pull request.
- Database access goes through `src/db.ts`. No raw `pg` calls in route handlers.
