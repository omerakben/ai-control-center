# Storage

Notes live in a single SQLite file, `notes.db`, created on first write. One table:

| column     | type    | notes                         |
| ---------- | ------- | ----------------------------- |
| id         | INTEGER | primary key, autoincrement    |
| body       | TEXT    | note text, not null           |
| created_at | TEXT    | ISO 8601 timestamp, UTC       |

`store.py` owns the connection and all queries. Handlers never touch SQL directly.

## Open work

- [ ] Add a `created_at` index before the table grows past a few thousand rows.
