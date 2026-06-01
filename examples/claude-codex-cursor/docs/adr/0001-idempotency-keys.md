# 0001 — Idempotency keys on checkout

Status: accepted
Date: 2026-05-31

## Context

Clients retry the checkout request on network timeouts. Without a guard, a retry can charge
the cart twice.

## Decision

The checkout endpoint requires an `Idempotency-Key` header. The first request with a given
key runs and stores its result keyed by that value. Later requests with the same key return
the stored result instead of charging again. Keys expire after 24 hours.

## Consequences

- Clients must generate and reuse a key per checkout attempt.
- Storage needs an `idempotency_keys` table with a TTL sweep.
