"""Copy the live SQLite storage tables into an empty PostgreSQL database.

Run with the backend stopped and PostgreSQL available. The target is intentionally required to be
empty so this tool cannot silently overwrite an existing portal database.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from typing import Iterable, List, Tuple

import storage


def _batches(cursor, size: int = 100) -> Iterable[List[Tuple]]:
    while rows := cursor.fetchmany(size):
        yield rows


def migrate(source_path: str, dsn: str) -> dict:
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"SQLite database not found: {source_path}")
    if not dsn.startswith(("postgres://", "postgresql://")):
        raise ValueError("Destination must be a postgres:// or postgresql:// DSN")

    source = sqlite3.connect(source_path)
    source.row_factory = None
    target = None
    try:
        table_names = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"portal_rows", "portal_kv"}.issubset(table_names):
            raise ValueError("Source is not a WatanePak live-storage SQLite database")
        has_assets = "portal_assets" in table_names

        import psycopg
        target = psycopg.connect(dsn)
        with target.cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS portal_rows (store TEXT NOT NULL, key TEXT NOT NULL, "
                        "ord INTEGER NOT NULL, data JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                        "PRIMARY KEY (store, key))")
            cur.execute("CREATE TABLE IF NOT EXISTS portal_kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            cur.execute("CREATE TABLE IF NOT EXISTS portal_assets (asset_key TEXT PRIMARY KEY, media_type TEXT NOT NULL, "
                        "data BYTEA NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now())")
            cur.execute("SELECT (SELECT COUNT(*) FROM portal_rows), (SELECT COUNT(*) FROM portal_kv), "
                        "(SELECT COUNT(*) FROM portal_assets)")
            counts = cur.fetchone()
            if any(counts):
                raise ValueError("PostgreSQL target is not empty; use a fresh database before migration")

            target.commit()  # commit table creation and the empty-target check
            target.execute("BEGIN")
            row_count = 0
            for batch in _batches(source.execute("SELECT store, key, ord, data, updated_at FROM portal_rows")):
                cur.executemany("INSERT INTO portal_rows (store, key, ord, data, updated_at) "
                                "VALUES (%s, %s, %s, %s::jsonb, %s)", batch)
                row_count += len(batch)

            kv_rows = source.execute("SELECT key, value FROM portal_kv").fetchall()
            if kv_rows:
                cur.executemany("INSERT INTO portal_kv (key, value) VALUES (%s, %s)", kv_rows)

            asset_count = 0
            if has_assets:
                for batch in _batches(source.execute("SELECT asset_key, media_type, data, updated_at FROM portal_assets"), 20):
                    cur.executemany("INSERT INTO portal_assets (asset_key, media_type, data, updated_at) "
                                    "VALUES (%s, %s, %s, %s)", batch)
                    asset_count += len(batch)
            target.commit()
            return {"portal_rows": row_count, "portal_kv": len(kv_rows), "portal_assets": asset_count}
    except Exception:
        if target is not None:
            target.rollback()
        raise
    finally:
        source.close()
        if target is not None:
            target.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-sqlite", default=os.getenv("PORTAL_DB_PATH") or os.path.join(os.path.dirname(__file__), "data", "portal.sqlite3"),
                        help="SQLite live-storage file (defaults to PORTAL_DB_PATH or backend/data/portal.sqlite3)")
    parser.add_argument("--to-postgres", default=os.getenv("DATABASE_URL"),
                        help="PostgreSQL DSN (defaults to DATABASE_URL)")
    args = parser.parse_args(argv)
    if not args.to_postgres:
        parser.error("set DATABASE_URL or pass --to-postgres")
    try:
        counts = migrate(args.from_sqlite, args.to_postgres)
    except Exception as exc:
        print(f"Migration failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print("SQLite storage copied to PostgreSQL:")
    for name, count in counts.items():
        print(f"  {name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
