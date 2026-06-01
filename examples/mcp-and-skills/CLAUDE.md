# Reporting service

A service that reads Postgres and writes daily CSV reports. Node 22, Postgres.

## Rules

- All database connections come from environment variables. Never hardcode credentials.
- Reports write to `./out`, one file per day, named `YYYY-MM-DD.csv`.
- Use the `seed-db` skill to set up local data before running the report job.
