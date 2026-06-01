# Checkout API

A REST API for cart and checkout. TypeScript, Node 22, Express, Postgres.

## Rules

- Money is integer cents. Never floats for currency.
- Every route validates its body with Zod before touching the database.
- One migration per pull request. Migrations are append-only; never edit a shipped one.
- Run the `.claude/agents/migration-reviewer.md` agent on every migration before merge.
- Read `docs/adr/0001-idempotency-keys.md` before changing the checkout endpoint.
