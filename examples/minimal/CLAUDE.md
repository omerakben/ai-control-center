# Notes service

A small HTTP service for personal notes. Python 3.12, FastAPI, SQLite.

## Rules

- Run `pytest` before every commit; do not commit on a red suite.
- Keep request handlers thin. Validation goes in `schemas.py`, storage in `store.py`.
- Use parameterized SQL only. No string-built queries.
- Read `docs/storage.md` before changing the database layer.
