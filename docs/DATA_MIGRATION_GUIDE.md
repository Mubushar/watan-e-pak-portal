# Data Migration Guide

## Overview

This guide walks you through migrating the Arz-e-Pak real-estate portal's in-memory data stores to a PostgreSQL database. The portal stores everything in module-level containers (`*_db`, `GIS_LAYERS`, `image_storage`, etc.) that are seeded on startup. The goal is to preserve the exact state — including row counts, primary keys, and referential relationships — in a relational database that can be queried with standard SQL tools, connected to an ORM, or used as the backbone for future features (PostGIS spatial search, analytics, etc.).

> **Do you need this guide?** The running portal already saves its data: `backend/storage.py`
> writes every store to PostgreSQL (`DATABASE_URL`) or a SQLite file (`backend/data/portal.sqlite3`)
> and restores it on start — see [Security & Operations §3](SECURITY_AND_OPERATIONS.md#3-durable-storage).
> That live storage uses its own two-table layout (`portal_rows`, `portal_kv`, one JSON row per
> item). This toolkit is separate: it **exports** the current state into a typed relational
> schema (one table per store, foreign keys, optional PostGIS) for analytics, reporting, an
> ORM or a future rewrite. The portal does not read these tables back, and you can point both
> at the same PostgreSQL server as long as they use different databases or schemas. Both find
> the stores with the same reflection (`db_migration.discover_tables`).
>
> **Note:** `migrate_to_postgres.py` imports the modules in its own process and does not open
> durable storage, so it exports the **seed** data, not what the running portal has saved.
> Exporting the live data needs the saved rows loaded first (`storage.start()` in the same
> process) — the CLI doesn't do that yet.

The migration is **lossless**: nested models (`JournalEntry.lines`, `Transaction.milestones`, `AgentRun.steps`, `Invoice.lines`, `PmInspection.checklist`) are embedded as JSONB, and every Python type maps to a Postgres type (str → TEXT, int → BIGINT, float → DOUBLE PRECISION, bool → BOOLEAN, datetime → TIMESTAMPTZ, date → DATE). List-of-scalars become TEXT[] and list-of-models becomes JSONB.

## Prerequisites

- Python 3.11+ with the portal's dependencies installed (`uv sync`).
- PostgreSQL 12+ (the installed 18 on this machine works out of the box). The native `psql` and `pg_isready` binaries are on PATH.
- The script was designed and tested with **PostgreSQL 18** installed and running (`postgresql-x64-18` Windows service). If you have a different version or a Docker container, adapt the DSN accordingly.

## Step 1 — Generate the migration bundle

Run the CLI from the ``backend`` directory:

```bash
uv run python migrate_to_postgres.py all
```

This produces:

| File | Contents |
|------|----------|
| `db/schema.sql` | `CREATE TABLE IF NOT EXISTS` for all 78 tables, including PKs, indexes, and 71 curated foreign-key constraints (validated against the live seeded data). |
| `db/data.sql` | `INSERT INTO` statements for all 668 rows, with typed literals (timestamptz, jsonb, arrays). |
| `db/load.sql` | A `\\copy ... FROM ...` bulk-load script (fastest path; requires ``COPY`` permission). |
| `db/postgis.sql` | Optional PostGIS extension enable + geography column rewrite (lat/lon → ``geography(Point,4326)`` with a GiST index). Comment out if you only need plain PostgreSQL. |
| `db/data/*.csv` | One CSV per table, ready for ``\\copy`` or spreadsheet import. |
| `db/manifest.json` | Machine-readable summary: table definitions, row counts, FK list, warnings. |

### Output directory

The default output is ``<repo>/db`` (relative to the repo root). Override with ``--out <path>``:

```bash
uv run python migrate_to_postgres.py all --out ./my_db_export
```

### Skip transient caches

Runtime caches (rate-limit codes, ephemeral road-network lookups) are omitted by default. Include them with ``--include-transient`` if you really need them:

```bash
uv run python migrate_to_postgres.py all --include-transient
```

### Additive mode

By default the bundle ``DROP TABLE IF EXISTS ... CASCADE`` + ``DELETE FROM`` to start clean. For an additive migration (e.g. adding tables to an existing DB) pass ``--no-drop``:

```bash
uv run python migrate_to_postgres.py all --no-drop
```

## Step 2 — Load the data into PostgreSQL

You have two pathways:

### A. ``psql`` (no Python driver needed)

If you have ``psql`` on PATH (as you do with PostgreSQL 18), simply run:

```bash
psql "postgresql://postgres:***@localhost:5432/arzepak" -f db/schema.sql -f db/data.sql
```

The ``apply`` command in the CLI also supports this path automatically (it falls back to ``psql`` when no ``psycopg`` driver is installed).

### B. Python driver (``psycopg``)

Install ``psycopg[binary]`` if you prefer an all-Python route (it is the backend's optional
``postgres`` extra, also used by durable storage):

```bash
uv sync --extra postgres
uv run python migrate_to_postgres.py apply --dsn "postgresql://postgres:postgres@localhost:5432/arzepak"
```

## Step 3 — Verify

After loading, confirm the import succeeded:

```bash
uv run python migrate_to_postgres.py verify --dsn "postgresql://postgres:***@localhost:5432/arzepak"
```

The output will list per-table expected vs. actual row counts and any FK mismatches. If everything is ``ok`` you're done. If not, re‑run the generator and check that the PostgreSQL version and ``psql``/``COPY`` permissions match.

## Step 4 — (Optional) PostGIS migration

If your deployment uses the portal's GIS search features, enable the geography rewrite after step 2:

```bash
psql "postgresql://postgres:***@localhost:5432/arzepak" -f db/postgis.sql
```

This adds a ``geography(Point,4326)`` column to the core entities that have lat/lon, populates them from the plain ``DOUBLE PRECISION`` columns, and creates a GiST index. The column name is the original column name suffixed with ``_geog`` (e.g. ``core_properties.geog``). Keep the original columns so existing queries continue to work.

## Step 5 — Rollback / incremental update

The generated `db/schema.sql` starts with ``DROP TABLE IF EXISTS ... CASCADE``, so a repeat run starts from a clean state. For incremental updates:

1. Edit the generated schema to remove the ``DROP`` / ``DELETE FROM`` prefix, or pass ``--no-drop``.
2. Re‑run ``migrate_to_postgres.py all`` to apply only new/changed tables.
3. Manually reconcile any rows that were added or modified in the in-memory stores after the first export (the manifest.json checksum helps identify drifts).

## Appendices

### Type‑mapping table

| Python annotation | Postgres type | Kind |
|-------------------|---------------|------|
| ``str`` | ``TEXT`` | scalar |
| ``bool`` | ``BOOLEAN`` | scalar |
| ``int`` | ``BIGINT`` | scalar |
| ``float`` | ``DOUBLE PRECISION`` | scalar |
| ``datetime`` | ``TIMESTAMPTZ`` | scalar |
| ``date`` | ``DATE`` | scalar |
| ``list[str]`` | ``TEXT[]`` | array |
| ``list[scalar]`` | ``<scalar>[]`` | array |
| ``dict`` / ``list[dict]`` / ``list[model]`` / ``Any`` | ``JSONB`` | json |
| ``None`` | ``NULL`` | — |

### Curated foreign keys

The migration includes 71 relationships, each validated against the seeded data before emission. They cover:

* **Hierarchy**: ``core_cities`` → ``core_housing_schemes`` → ``core_block_zone_areas`` → ``core_properties`` → ``core_big_projects``. ``core_agents`` is the link from properties and leads.
* **CRM**: ``core_leads`` / ``core_deals`` / ``core_customers`` / ``core_appointments`` / ``core_tasks``.
* **Messaging**: ``messaging_conversations`` → ``messaging_memberships`` → ``messaging_messages`` → ``messaging_attachments`` / ``messaging_actions``. ``linked_task_id`` routes to ``core_tasks``.
* **PMO**: ``pmo_phases`` / ``pmo_tasks`` / ``pmo_milestones`` / ``pmo_allocations`` / ``pmo_cost_entries`` / ``pmo_risks`` / ``pmo_site_logs`` / ``pmo_change_requests`` / ``pmo_inspections`` / ``pmo_actions`` / ``pmo_progress_updates``.
* **Accounting**: ``accounting_invoices`` / ``accounting_leases`` / ``accounting_expenses`` / ``accounting_payments`` / ``accounting_journal``.
* **Content**: ``content_stories`` / ``content_pages`` / ``content_ads`` / ``content_contacts`` / ``content_history``.
* **Commerce**: ``transactions`` / ``transactions_offers`` / ``transactions_signatures`` / ``leasing_units`` / ``leasing_inquiries`` / ``leasing_applications`` / ``marketing_routes`` / ``commercial_payouts`` / ``commercial_subscriptions`` / ``commercial_meter_events``.
* **Agents**: ``auth_users`` referencing ``core_agents`` / ``core_customers``.
* **Tools**: ``tools_projects`` (SavedToolProject).

FKs that contain orphans in the seeded data are **skipped** with a warning (2 in the current data: ``core_properties.agent_id → core_agents`` due to one orphan, and ``commercial_payouts.transaction_id → transactions`` due to one orphan). This keeps the migration honest rather than asserting relationships that don't hold.

### Known orphan warnings (benign)

The 2 FKs that are intentionally omitted are:

1. ``core_properties.agent_id → core_agents`` — one seeded ``Property`` row has an agent identifier that does not match any ``Agent`` in the current data. The FK is skipped; the column remains ``NULL``‑able.
2. ``commercial_payouts.transaction_id → transactions`` — one ``Payout`` references a ``Transaction`` that was never seeded. Same treatment: column stays NULL‑able.

Both omissions are documented in the manifest.json warnings array.

### Walkthrough with the live data (what you just generated)

```text
$ uv run python migrate_to_postgres.py all
Migration bundle written to C:\Users\mubho\Desktop\alfaisal\arzepak\db
  tables        : 78
  rows          : 668
  foreign keys  : 71
  files         : 83
  warnings      : 2 (see manifest.json)

$ psql "postgres:postgres@localhost:5432/arzepak" -f db/schema.sql -f db/data.sql
psql -f schema.sql : ok
psql -f data.sql : ok

$ uv run python migrate_to_postgres.py verify --dsn "postgres:postgres@localhost:5432/arzepak"
Verification: OK  (driver=psql)
  tables: 78   rows: 668
```

That's it. The database now mirrors the portal's entire in-memory state, queryable via standard SQL, and ready for any downstream system (analytics, ORM, API layer, etc.).