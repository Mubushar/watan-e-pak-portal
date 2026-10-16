"""Command-line front end for the PostgreSQL migration toolkit.

Examples
--------
    # Show what will be migrated (no files written)
    uv run python migrate_to_postgres.py report

    # Write db/schema.sql, db/data.sql, db/load.sql, db/postgis.sql, db/data/*.csv
    uv run python migrate_to_postgres.py all

    # Inspect environment readiness (psql / docker / drivers / server reachable)
    uv run python migrate_to_postgres.py doctor

    # Create the schema + load the data into a running PostgreSQL
    uv run python migrate_to_postgres.py apply --dsn "postgresql://postgres:postgres@localhost:5432/arzepak"

    # Re-check row counts against the manifest
    uv run python migrate_to_postgres.py verify --dsn "postgresql://postgres:postgres@localhost:5432/arzepak"

The writer is framework-free and stdlib-only. Applying to PostgreSQL uses ``psycopg``
if installed, otherwise it shells out to ``psql``; if neither exists it returns a
``requires_optional_dependency`` descriptor instead of failing obscurely.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import db_migration  # noqa: E402


def _default_out() -> str:
    return os.path.join(REPO_ROOT, "db")


# ------------------------------------------------------------
# subcommands
# ------------------------------------------------------------


def cmd_report(args: argparse.Namespace) -> int:
    plan = db_migration.build_plan(include_transient=args.include_transient)
    tables = plan["tables"]
    print("PostgreSQL migration plan")
    print("  schema : %s" % db_migration.SCHEMA)
    print("  tables : %d" % len(tables))
    print("  rows   : %d" % plan["row_count"])
    print("  fks    : %d accepted, %d skipped"
          % (len(plan["fks"]), len(plan["warnings"])))
    print()
    print("  %-38s %-22s %6s  %s" % ("TABLE", "MODEL", "ROWS", "PRIMARY KEY"))
    print("  " + "-" * 88)
    for table in tables:
        print("  %-38s %-22s %6d  %s" % (
            table.name, table.model or table.kind, len(plan["rows_map"][table.name]),
            ",".join(table.pk) or "-"))
    if plan["warnings"]:
        print()
        print("Warnings")
        for warning in plan["warnings"]:
            print("  ! %s" % warning)
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    summary = db_migration.write_bundle(
        args.out, include_transient=args.include_transient, drop=not args.no_drop,
        write_csv=False)
    print("wrote %s (schema.sql, postgis.sql, manifest.json)" % summary["out_dir"])
    print("  tables: %d  rows: %d" % (summary["table_count"], summary["row_count"]))
    return 0


def cmd_dump(args: argparse.Namespace) -> int:
    summary = db_migration.write_bundle(
        args.out, include_transient=args.include_transient, drop=not args.no_drop,
        write_csv=not args.no_csv)
    print("wrote dump to %s" % summary["out_dir"])
    print("  files: %s" % ", ".join(summary["files"][:6]))
    print("  tables: %d  rows: %d" % (summary["table_count"], summary["row_count"]))
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    summary = db_migration.write_bundle(
        args.out, include_transient=args.include_transient, drop=not args.no_drop,
        write_csv=not args.no_csv)
    print("Migration bundle written to %s" % summary["out_dir"])
    print("  tables        : %d" % summary["table_count"])
    print("  rows          : %d" % summary["row_count"])
    print("  foreign keys  : %d" % len(summary["foreign_keys"]))
    print("  files         : %d" % len(summary["files"]))
    if summary["foreign_key_warnings"]:
        print("  warnings      : %d (see manifest.json)" % len(summary["foreign_key_warnings"]))
    print()
    print("Next:")
    print("  psql \"$DSN\" -f %s" % _rel(os.path.join(args.out, "schema.sql")))
    print("  psql \"$DSN\" -f %s" % _rel(os.path.join(args.out, "data.sql")))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    print("Environment check")
    print("  python        : %s" % sys.version.split()[0])
    driver, name = db_migration.load_driver()
    print("  db driver     : %s" % (name or "none (psql fallback will be used)"))
    for tool in ("psql", "pg_isready", "docker"):
        path = shutil.which(tool)
        print("  %-13s : %s" % (tool, path or "not found"))
    if shutil.which("pg_isready"):
        try:
            out = subprocess.run(["pg_isready"], capture_output=True, text=True, timeout=10)
            print("  pg_isready    : %s" % (out.stdout.strip() or out.stderr.strip()))
        except Exception as exc:  # pragma: no cover
            print("  pg_isready    : error (%s)" % exc)
    if args.dsn:
        ok, message = _probe(args.dsn)
        print("  dsn           : %s -> %s" % (args.dsn, message))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    out = args.out
    schema = os.path.join(out, "schema.sql")
    data = os.path.join(out, "data.sql")
    if not os.path.exists(schema):
        print("No schema at %s - run `migrate_to_postgres.py all` first." % schema)
        return 2

    driver, name = db_migration.load_driver()
    if driver is not None:
        with open(schema, encoding="utf-8") as fh:
            schema_text = fh.read()
        statements = [s for s in schema_text.split(";\n") if s.strip()]
        result = db_migration.apply_sql(args.dsn, statements)
        if result.get("status") != "ok":
            print(json.dumps(result, indent=2))
            return 3
        if os.path.exists(data):
            with open(data, encoding="utf-8") as fh:
                data_text = fh.read()
            result2 = db_migration.apply_sql(args.dsn, [data_text])
            if result2.get("status") != "ok":
                print(json.dumps(result2, indent=2))
                return 4
        print("Applied schema + data via %s to %s" % (name, _redact(args.dsn)))
        return 0

    psql = shutil.which("psql")
    if psql is None:
        print(json.dumps(db_migration._requires_driver(), indent=2))
        return 5
    for path in (schema, data):
        if not os.path.exists(path):
            continue
        proc = subprocess.run(
            [psql, args.dsn, "-v", "ON_ERROR_STOP=1", "-f", path],
            capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr)
            return proc.returncode
        print("psql -f %s : ok" % os.path.basename(path))
    print("Applied to %s via psql" % _redact(args.dsn))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    expected = None
    manifest_path = os.path.join(args.out, "manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as fh:
            doc = json.load(fh)
        expected = {entry["table"].split(".", 1)[1]: entry["rows"] for entry in doc["tables"]}
    if expected is None:
        plan = db_migration.build_plan(include_transient=args.include_transient)
        expected = db_migration.expected_counts(plan)
        print("(no manifest.json - comparing against the live in-memory seeding)")

    result = db_migration.verify_counts(args.dsn, expected)
    if result.get("status") == "requires_optional_dependency":
        result = _verify_via_psql(args.dsn, expected)
    if result.get("status") == "requires_optional_dependency":
        print(json.dumps(result, indent=2))
        return 5
    ok = result["status"] == "ok"
    print("Verification: %s  (driver=%s)" % ("OK" if ok else "FAILED", result.get("driver")))
    if not ok:
        for mismatch in result["mismatches"]:
            print("  ! %s" % mismatch)
    total = sum(v["actual"] for v in result["tables"].values())
    print("  tables: %d   rows: %d" % (len(result["tables"]), total))
    return 0 if ok else 1


def _verify_via_psql(dsn: str, expected: dict) -> dict:
    """Fallback verifier that uses the ``psql`` client when no driver is installed."""
    psql = shutil.which("psql")
    if psql is None:
        return db_migration._requires_driver()
    result = {"status": "ok", "driver": "psql", "tables": {}, "mismatches": []}
    for table, want in sorted(expected.items()):
        query = 'SELECT count(*) FROM %s.%s;' % (db_migration.SCHEMA, db_migration._q(table))
        proc = subprocess.run([psql, dsn, "-t", "-A", "-c", query],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            result["mismatches"].append("%s.%s: query failed (%s)"
                                        % (db_migration.SCHEMA, table, proc.stderr.strip()))
            continue
        try:
            got = int(proc.stdout.strip())
        except ValueError:
            result["mismatches"].append("%s.%s: unexpected output %r"
                                        % (db_migration.SCHEMA, table, proc.stdout.strip()))
            continue
        result["tables"][table] = {"expected": want, "actual": got, "ok": want == got}
        if want != got:
            result["mismatches"].append(
                "%s.%s: expected %d, found %d" % (db_migration.SCHEMA, table, want, got))
    result["status"] = "ok" if not result["mismatches"] else "mismatch"
    return result


# ------------------------------------------------------------
# helpers
# ------------------------------------------------------------


def _rel(path: str) -> str:
    try:
        return os.path.relpath(path, os.getcwd())
    except Exception:  # pragma: no cover
        return path


def _redact(dsn: str) -> str:
    if "@" not in dsn:
        return dsn
    head, tail = dsn.rsplit("@", 1)
    if ":" in head.split("//")[-1]:
        scheme, rest = head.split("//", 1)
        user = rest.split(":", 1)[0]
        return "%s//%s:***@%s" % (scheme, user, tail)
    return dsn


def _probe(dsn: str) -> tuple:
    """Cheap reachability probe using pg_isready when available."""
    if shutil.which("pg_isready") is None:
        return False, "pg_isready not available"
    proc = subprocess.run(["pg_isready", "-d", dsn], capture_output=True, text=True)
    return proc.returncode == 0, proc.stdout.strip() or proc.stderr.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate_to_postgres.py",
        description="Generate and apply the Arz-e-Pak portal PostgreSQL migration.")
    parser.add_argument("--out", default=_default_out(),
                        help="output directory (default: <repo>/db)")
    parser.add_argument("--include-transient", action="store_true",
                        help="also migrate caches / rate limiters / ephemeral stores")
    parser.add_argument("--no-drop", action="store_true",
                        help="do not emit DROP/DELETE statements (additive only)")
    parser.add_argument("--no-csv", action="store_true",
                        help="skip the per-table CSV files")

    subs = parser.add_subparsers(dest="command")

    subs.add_parser("report", help="print the migration plan (no files)")
    subs.add_parser("schema", help="write schema.sql + postgis.sql + manifest.json")
    subs.add_parser("dump", help="write data.sql + CSV + load.sql")
    subs.add_parser("all", help="write the full bundle (default)")

    doctor = subs.add_parser("doctor", help="report environment readiness")
    doctor.add_argument("--dsn", default=None)

    for name in ("apply", "verify"):
        sub = subs.add_parser(name, help="%s the migration against a database" % name)
        sub.add_argument("--dsn", required=True,
                         help="PostgreSQL DSN, e.g. postgresql://postgres:postgres@localhost:5432/arzepak")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        args.command = "all"
    handlers = {
        "report": cmd_report,
        "schema": cmd_schema,
        "dump": cmd_dump,
        "all": cmd_all,
        "doctor": cmd_doctor,
        "apply": cmd_apply,
        "verify": cmd_verify,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
