---
name: seed-db
description: Load the local Postgres database with a small set of sample rows for development.
---

Seed the development database with sample data.

Steps:

1. Confirm the database connection variables are set in the local environment. Do not read
   or print their values.
2. Run `npm run db:reset` to drop and recreate the schema.
3. Run `npm run db:seed` to insert the sample rows.
4. Print the row count per table so the user can confirm the seed worked.

Stop and report if any step exits non-zero. Do not retry against a different database.
