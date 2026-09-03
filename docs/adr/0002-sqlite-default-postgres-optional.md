# ADR-0002: SQLite by default, Postgres optional, no migration tool

- **Status:** Accepted
- **Date:** 2026-09-03
- **Deciders:** Ali Dousa

## Context

The demo has to run for someone who has just cloned it. Every prerequisite
between `git clone` and a working incident board loses reviewers: a database
server to install, a container to start, a connection string to configure, a
migration to apply.

At the same time, the repository makes claims about data integrity — an
append-only hash-chained audit log, a single mutation point for inventory. Those
claims should not quietly depend on a database engine nobody runs by default.

## Decision

- **SQLite is the default**, via `sqlite+aiosqlite`, in a file at `data/eoc.db`.
- **Postgres is supported and documented** by changing `DATABASE_URL`; the
  `postgres` extra installs `asyncpg`. Nothing in the schema is SQLite-specific.
- **Schema is created with `Base.metadata.create_all`.** There is no Alembic.
- Relative SQLite paths are resolved **against the repository root**, not the
  process working directory.

## Rationale

- Zero-ops default. No server, no container, no credentials. `make seed` and the
  board is populated.
- The schema uses no SQLite-specific types. `StrEnumType` stores enum *values*
  as strings, `JSON` columns are portable, and the one engine-specific concession
  — `PRAGMA foreign_keys=ON` — exists to make SQLite behave like every other
  database, not differently from them.
- **No migration tool, on purpose.** A reference slice has no deployed history to
  migrate from. Shipping Alembic would add a directory of empty ceremony and
  imply an operational maturity the repo does not have. A production system needs
  migrations on day one; this is not one, and saying so is more useful than
  pretending.
- Resolving the SQLite path against the repo root removes a real footgun:
  `make seed` runs from `apps/api` while `make reset` runs from the root, so a
  cwd-relative path would silently address two different files.

## Alternatives considered

**Postgres by default, in Docker Compose.** Rejected as the default because it
makes Docker mandatory for the fastest path. It remains fully supported, and
Compose is provided for reviewers who prefer it.

**Alembic from the start.** Rejected: see above. If this slice ever became a
product, the first migration would be generated from the current `create_all`
schema, and that is a five-minute job at the moment it is actually needed.

**An in-memory database.** Rejected: the demo's value is that a reviewer can
approve a request, restart the process, and see that the decision and its audit
row survived.

## Consequences

**Accepted:**

- SQLite serialises writes. Irrelevant at demo concurrency, and it happens to
  reinforce the audit chain's single-writer assumption (ADR-0004).
- `create_all` will not alter an existing table. Changing the schema during
  development means `make reset`. Acceptable when the data is fixtures.
- No point-in-time recovery, no replication, no connection pooling story. All
  are production concerns this slice explicitly does not address.

**Gained:**

- The whole demo is one file the reviewer can delete to start over.
- Tests get a throwaway database per test, which is what makes the
  count-based assertions ("exactly one inventory mutation") trustworthy.

## Implementation notes

- `Settings.sqlalchemy_url` performs the repo-root resolution and creates the
  parent directory. Absolute paths and non-SQLite URLs pass through untouched,
  so the Compose deployment's `sqlite+aiosqlite:////data/eoc.db` works unchanged.
- To use Postgres:

  ```bash
  cd apps/api && uv sync --extra postgres
  export DATABASE_URL="postgresql+asyncpg://eoc:eoc@localhost:5432/eoc"
  make seed
  ```

- `data/` is git-ignored. The database is always reproducible from
  `fixtures/` with `make reset`.
