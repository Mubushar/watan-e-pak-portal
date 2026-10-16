"""
PostgreSQL migration toolkit for the Arz-e-Pak portal.

The portal stores everything in module-level in-memory containers that are seeded
on startup. This module turns that live state into a PostgreSQL database:

    * discovers every store (``*_db`` lists/dicts plus a few special stores),
    * derives a table schema from the pydantic models behind those stores,
    * emits DDL (``schema.sql``), data (``data.sql`` + per-table CSV),
      a ``manifest.json`` and a ``load.sql`` (COPY-based bulk load),
    * can apply the DDL/data through any DB-API driver (psycopg is optional),
    * can verify row counts and referential integrity after a load.

It is framework-free and stdlib-only, matching the rest of the codebase. The heavy
database *driver* is an optional dependency: if none is installed the loader returns a
``requires_optional_dependency`` descriptor instead of pretending to connect.

Because it reads the same modules the server serves from, the schema can never drift
from the live models. The mapping is deliberately simple and lossless:

    str -> TEXT, int -> BIGINT, float -> DOUBLE PRECISION, bool -> BOOLEAN,
    datetime -> TIMESTAMPTZ, date -> DATE,
    list[str] -> TEXT[], list[scalar] -> <scalar>[],
    dict / list[dict] / list[model] / Any -> JSONB

Nested models (``JournalEntry.lines``, ``Transaction.milestones``, ``AgentRun.steps``,
``PmInspection.checklist``, ``Invoice.lines``, ``Transaction.terms``) are embedded as
JSONB so the round-trip is exact; they can be normalised into child tables later.

Run the CLI instead of this module directly: ``uv run python migrate_to_postgres.py``.
"""

import csv
import io
import json
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

# ============================================================
# CONFIGURATION
# ============================================================

SCHEMA = "portal"
MIGRATION_VERSION = 1

# Every module that owns stores. Importing ``server`` first seeds the sample data,
# which in turn populates the accounting / gis / auth stores.
MODULES = [
    "server", "auth", "gis", "content", "accounting", "construction", "maintenance",
    "tools", "pmo", "messaging", "agents", "transactions", "intelligence", "leasing",
    "marketing", "commercial",
]

# Module -> table-name prefix. ``server`` becomes ``core`` because it owns the
# hierarchy; every other module keeps its own name.
MODULE_PREFIX = {"server": "core"}

# Stores whose element type cannot be inferred from the (empty) list at import time.
MODEL_OVERRIDES: Dict[Tuple[str, str], str] = {
    ("auth", "otps_db"): "OtpCode",
    ("auth", "sessions_db"): "SessionToken",
    ("auth", "notifications_db"): "Notification",
    ("marketing", "leads_db"): "MarketingLead",
    ("messaging", "reports_db"): "MessageReport",
}

# Stores that are not ``*_db`` containers, or whose shape is special.
# (module, store, model, kind, transient, table_base)
#   kind: rows | rows_generic | keyed_json | nested_keyed
EXTRA_STORES: List[Tuple[str, str, Optional[str], str, bool, str]] = [
    ("gis", "GIS_LAYERS", "GeoLayer", "rows", False, "layers"),
    ("server", "image_storage", None, "nested_keyed", False, "image_storage"),
    ("server", "near_memory_cache", None, "rows_generic", True, "near_memory_cache"),
    ("server", "long_term_memory", None, "keyed_json", True, "long_term_memory"),
]

# Runtime-only stores: rate limiters, ephemeral link codes, caches, the synthetic
# road network. Excluded unless ``--include-transient`` is passed.
TRANSIENT_STORES: set = {
    ("messaging", "link_codes_db"),
    ("messaging", "rate_db"),
    ("messaging", "muted_authors_db"),
    ("server", "road_networks_db"),
    ("server", "near_memory_cache"),
    ("server", "long_term_memory"),
}

# Preferred primary key per model, in order. Falls back to none (append-only table).
PK_PREFERENCE = ["id", "code", "name"]

# Models without a single-column ``id``. Keyed by model class name so the same
# model reflected from different stores resolves consistently.
MODEL_PK: Dict[str, List[str]] = {
    "Membership": ["conversation_id", "user_id"],
    "SessionToken": ["token"],
    "MsgProfile": ["user_id"],
    "TelegramLink": ["user_id"],
    "Role": ["name"],
    "Account": ["code"],
}

# Curated foreign keys. Each entry is validated against the live data before it is
# emitted: if the target table/column does not exist, or the source column contains
# values absent from the target, the constraint is skipped and reported. This keeps
# the migration honest instead of asserting relationships that do not hold.
RELATIONSHIPS: List[Tuple[str, str, str, str]] = [
    # Hierarchy
    ("core_housing_schemes", "city_id", "core_cities", "id"),
    ("core_block_zone_areas", "scheme_id", "core_housing_schemes", "id"),
    ("core_properties", "city_id", "core_cities", "id"),
    ("core_properties", "scheme_id", "core_housing_schemes", "id"),
    ("core_properties", "block_zone_area_id", "core_block_zone_areas", "id"),
    ("core_properties", "agent_id", "core_agents", "id"),
    ("core_big_projects", "city_id", "core_cities", "id"),
    ("core_big_projects", "scheme_id", "core_housing_schemes", "id"),
    ("core_big_projects", "block_zone_area_id", "core_block_zone_areas", "id"),
    ("core_pois", "city_id", "core_cities", "id"),
    ("core_pois", "scheme_id", "core_housing_schemes", "id"),
    ("core_pois", "block_zone_area_id", "core_block_zone_areas", "id"),
    ("core_aois", "city_id", "core_cities", "id"),
    ("core_aois", "scheme_id", "core_housing_schemes", "id"),
    # CRM
    ("core_leads", "city_id", "core_cities", "id"),
    ("core_leads", "scheme_id", "core_housing_schemes", "id"),
    ("core_leads", "assigned_agent_id", "core_agents", "id"),
    ("core_deals", "lead_id", "core_leads", "id"),
    ("core_deals", "property_id", "core_properties", "id"),
    ("core_deals", "agent_id", "core_agents", "id"),
    ("core_customers", "city_id", "core_cities", "id"),
    ("core_customers", "source_lead_id", "core_leads", "id"),
    ("core_customers", "assigned_agent_id", "core_agents", "id"),
    ("core_appointments", "lead_id", "core_leads", "id"),
    ("core_appointments", "customer_id", "core_customers", "id"),
    ("core_appointments", "property_id", "core_properties", "id"),
    ("core_tasks", "assigned_agent_id", "core_agents", "id"),
    ("core_news", "city_id", "core_cities", "id"),
    # Auth / content
    ("auth_users", "customer_id", "core_customers", "id"),
    ("auth_users", "agent_id", "core_agents", "id"),
    ("content_stories", "property_id", "core_properties", "id"),
    ("content_stories", "project_id", "core_big_projects", "id"),
    # Accounting
    ("accounting_leases", "property_id", "core_properties", "id"),
    ("accounting_invoices", "property_id", "core_properties", "id"),
    ("accounting_invoices", "lease_id", "accounting_leases", "id"),
    ("accounting_invoices", "counterparty_id", "core_customers", "id"),
    ("accounting_payments", "invoice_id", "accounting_invoices", "id"),
    ("accounting_expenses", "property_id", "core_properties", "id"),
    # PMO
    ("pmo_phases", "project_id", "pmo_projects", "id"),
    ("pmo_tasks", "project_id", "pmo_projects", "id"),
    ("pmo_milestones", "project_id", "pmo_projects", "id"),
    ("pmo_allocations", "project_id", "pmo_projects", "id"),
    ("pmo_allocations", "task_id", "pmo_tasks", "id"),
    ("pmo_allocations", "resource_id", "pmo_resources", "id"),
    ("pmo_cost_entries", "project_id", "pmo_projects", "id"),
    ("pmo_risks", "project_id", "pmo_projects", "id"),
    ("pmo_site_logs", "project_id", "pmo_projects", "id"),
    ("pmo_change_requests", "project_id", "pmo_projects", "id"),
    ("pmo_inspections", "project_id", "pmo_projects", "id"),
    ("pmo_actions", "project_id", "pmo_projects", "id"),
    ("pmo_progress_updates", "project_id", "pmo_projects", "id"),
    # Messaging
    ("messaging_profiles", "user_id", "auth_users", "id"),
    ("messaging_conversations", "property_id", "core_properties", "id"),
    ("messaging_memberships", "conversation_id", "messaging_conversations", "id"),
    ("messaging_memberships", "user_id", "auth_users", "id"),
    ("messaging_messages", "conversation_id", "messaging_conversations", "id"),
    ("messaging_messages", "parent_id", "messaging_messages", "id"),
    ("messaging_attachments", "conversation_id", "messaging_conversations", "id"),
    ("messaging_attachments", "message_id", "messaging_messages", "id"),
    ("messaging_actions", "conversation_id", "messaging_conversations", "id"),
    ("messaging_actions", "message_id", "messaging_messages", "id"),
    ("messaging_actions", "owner_id", "auth_users", "id"),
    ("messaging_actions", "linked_task_id", "core_tasks", "id"),
    ("messaging_notifications", "user_id", "auth_users", "id"),
    ("messaging_notifications", "conversation_id", "messaging_conversations", "id"),
    ("messaging_outbox", "user_id", "auth_users", "id"),
    ("messaging_telegram", "user_id", "auth_users", "id"),
    # Transactions / leasing / marketing / commercial
    ("transactions_offers", "transaction_id", "transactions", "id"),
    ("transactions_signatures", "transaction_id", "transactions", "id"),
    ("leasing_inquiries", "unit_id", "leasing_units", "id"),
    ("leasing_applications", "unit_id", "leasing_units", "id"),
    ("marketing_routes", "assign_to_agent_id", "core_agents", "id"),
    ("commercial_payouts", "transaction_id", "transactions", "id"),
]


# ============================================================
# SCHEMA DESCRIPTORS
# ============================================================


@dataclass
class Column:
    name: str
    sql_type: str
    nullable: bool = True
    kind: str = "scalar"          # scalar | array | json
    elem_sql: Optional[str] = None  # for arrays
    pk: bool = False

    @property
    def definition(self) -> str:
        bits = [_q(self.name), self.sql_type]
        if self.pk:
            bits.append("NOT NULL")
        elif not self.nullable:
            bits.append("NOT NULL")
        return " ".join(bits)


@dataclass
class Table:
    name: str                      # without schema prefix
    module: str
    store: str
    model: Optional[str]
    kind: str                      # rows | rows_generic | keyed_json | nested_keyed
    transient: bool
    columns: List[Column] = field(default_factory=list)
    pk: List[str] = field(default_factory=list)

    @property
    def qualified(self) -> str:
        return "%s.%s" % (SCHEMA, _q(self.name))

    @property
    def column_names(self) -> List[str]:
        return [c.name for c in self.columns]


# ============================================================
# IDENTIFIER + TYPE HELPERS
# ============================================================


def _q(identifier: str) -> str:
    """Quote a PostgreSQL identifier, lower-casing it for stability."""
    return '"%s"' % identifier.lower().replace('"', '""')


def _is_optional(annotation: Any) -> Tuple[Any, bool]:
    """Unwrap ``X | None`` / ``Optional[X]`` -> (X, True)."""
    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())
    if origin is None:
        return annotation, False
    # typing.Union and PEP 604 types.UnionType both land here.
    if str(origin) in ("typing.Union", "types.UnionType") and args:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0], True
        return annotation, True
    return annotation, False


def _sql_type(annotation: Any) -> Tuple[str, str, Optional[str]]:
    """Map a Python annotation to (sql_type, kind, element_sql_type)."""
    inner, _ = _is_optional(annotation)
    origin = getattr(inner, "__origin__", None)
    args = getattr(inner, "__args__", ())

    if inner is str:
        return "TEXT", "scalar", None
    if inner is bool:
        return "BOOLEAN", "scalar", None
    if inner is int:
        return "BIGINT", "scalar", None
    if inner is float:
        return "DOUBLE PRECISION", "scalar", None
    if inner is datetime:
        return "TIMESTAMPTZ", "scalar", None
    if inner is date:
        return "DATE", "scalar", None
    if origin is list:
        elem = args[0] if args else Any
        elem_type, elem_kind, _ = _sql_type(elem)
        if elem_kind == "scalar" and elem_type in (
            "TEXT", "BIGINT", "DOUBLE PRECISION", "BOOLEAN", "DATE", "TIMESTAMPTZ",
        ):
            return "%s[]" % elem_type, "array", elem_type
        return "JSONB", "json", None
    if origin is dict or inner is Any:
        return "JSONB", "json", None
    # Anything else (nested models, exotic unions) is stored losslessly as JSON.
    return "JSONB", "json", None


# ============================================================
# DISCOVERY
# ============================================================


def _load_modules() -> Dict[str, Any]:
    import importlib

    loaded: Dict[str, Any] = {}
    backend = os.path.dirname(os.path.abspath(__file__))
    if backend not in sys.path:
        sys.path.insert(0, backend)
    for name in MODULES:
        try:
            loaded[name] = importlib.import_module(name)
        except Exception:  # pragma: no cover - a module may need optional extras
            continue
    return loaded


def _table_name(module: str, store: str) -> str:
    prefix = MODULE_PREFIX.get(module, module)
    base = store
    if base.endswith("_db"):
        base = base[:-3]
    if base == prefix:
        return prefix
    return "%s_%s" % (prefix, base)


def _resolve_model(module: str, store: str, container: Any, modules: Dict[str, Any]) -> Optional[Any]:
    override = MODEL_OVERRIDES.get((module, store))
    if override:
        return getattr(modules.get(module), override, None)
    # list store: type of first row
    if isinstance(container, list) and container:
        return type(container[0])
    # dict store keyed by model instances
    if isinstance(container, dict) and container:
        first = next(iter(container.values()))
        if not isinstance(first, (dict, list, str, int, float, bool, type(None))):
            return type(first)
    return None


def _columns_for_model(model: Any) -> List[Column]:
    columns: List[Column] = []
    for fname, f in model.model_fields.items():
        annotation = f.annotation
        _inner, optional = _is_optional(annotation)
        sql, kind, elem = _sql_type(annotation)
        # A field with a non-None default is effectively optional too.
        nullable = optional or not f.is_required()
        columns.append(Column(name=fname, sql_type=sql, nullable=nullable, kind=kind, elem_sql=elem))
    return columns


def _pk_for(model: Any, columns: List[Column]) -> List[str]:
    names = [c.name for c in columns]
    if model is not None:
        explicit = MODEL_PK.get(model.__name__)
        if explicit and all(c in names for c in explicit):
            return list(explicit)
    for candidate in PK_PREFERENCE:
        if candidate in names:
            return [candidate]
    return []


def validate_primary_keys(tables: List[Table],
                          rows_map: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    """Drop any primary key that is not unique and non-null in the seeded data.

    A migration that fails on a duplicate key is worse than one that honestly
    records the store as append-only, so mismatches downgrade the table instead.
    """
    warnings: List[str] = []
    for table in tables:
        if not table.pk:
            continue
        rows = rows_map.get(table.name, [])
        if any(any(r.get(c) is None for c in table.pk) for r in rows):
            warnings.append("drop PK %s(%s): null key in seeded data"
                            % (table.name, ",".join(table.pk)))
            table.pk = []
        elif len({tuple(str(r.get(c)) for c in table.pk) for r in rows}) != len(rows):
            warnings.append("drop PK %s(%s): duplicate key in seeded data"
                            % (table.name, ",".join(table.pk)))
            table.pk = []
        for col in table.columns:
            col.pk = col.name in table.pk
    return warnings


def discover_tables(include_transient: bool = False, modules: Optional[Dict[str, Any]] = None) -> List[Table]:
    """Reflect every store into a :class:`Table` descriptor."""
    modules = modules if modules is not None else _load_modules()
    tables: List[Table] = []

    for module in MODULES:
        mod = modules.get(module)
        if mod is None:
            continue
        for store, container in sorted(vars(mod).items()):
            if not store.endswith("_db"):
                continue
            if not isinstance(container, (list, dict)):
                continue
            transient = (module, store) in TRANSIENT_STORES
            if transient and not include_transient:
                continue
            model = _resolve_model(module, store, container, modules)
            if model is not None and hasattr(model, "model_fields"):
                table = Table(
                    name=_table_name(module, store), module=module, store=store,
                    model=model.__name__, kind="rows", transient=transient,
                    columns=_columns_for_model(model),
                )
                table.pk = _pk_for(model, table.columns)
            elif isinstance(container, dict):
                table = Table(
                    name=_table_name(module, store), module=module, store=store,
                    model=None, kind="keyed_json", transient=transient,
                    columns=[
                        Column(name="key", sql_type="TEXT", nullable=False, pk=True),
                        Column(name="value", sql_type="JSONB", nullable=True, kind="json"),
                    ],
                )
                table.pk = ["key"]
            else:
                table = Table(
                    name=_table_name(module, store), module=module, store=store,
                    model=None, kind="rows_generic", transient=transient,
                    columns=[
                        Column(name="_row_id", sql_type="BIGINT", nullable=False, pk=True),
                        Column(name="payload", sql_type="JSONB", nullable=True, kind="json"),
                    ],
                )
                table.pk = ["_row_id"]
            for col in table.columns:
                col.pk = col.name in table.pk
            tables.append(table)

    # ---- special stores
    for module, store, model_name, kind, transient, table_base in EXTRA_STORES:
        if transient and not include_transient:
            continue
        mod = modules.get(module)
        if mod is None:
            continue
        container = getattr(mod, store, None)
        if container is None:
            continue
        name = "%s_%s" % (MODULE_PREFIX.get(module, module), table_base)
        if kind == "rows" and model_name:
            model = getattr(mod, model_name, None)
            if model is None:
                continue
            table = Table(name=name, module=module, store=store, model=model_name,
                          kind="rows", transient=transient, columns=_columns_for_model(model))
            table.pk = _pk_for(model, table.columns)
        elif kind == "nested_keyed":
            table = Table(
                name=name, module=module, store=store, model=None, kind="nested_keyed",
                transient=transient,
                columns=[
                    Column(name="entity_type", sql_type="TEXT", nullable=False, pk=True),
                    Column(name="entity_id", sql_type="TEXT", nullable=False, pk=True),
                    Column(name="images", sql_type="JSONB", nullable=True, kind="json"),
                ],
            )
            table.pk = ["entity_type", "entity_id"]
        elif kind == "keyed_json":
            table = Table(
                name=name, module=module, store=store, model=None, kind="keyed_json",
                transient=transient,
                columns=[
                    Column(name="key", sql_type="TEXT", nullable=False, pk=True),
                    Column(name="value", sql_type="JSONB", nullable=True, kind="json"),
                ],
            )
            table.pk = ["key"]
        else:  # rows_generic
            table = Table(
                name=name, module=module, store=store, model=None, kind="rows_generic",
                transient=transient,
                columns=[
                    Column(name="_row_id", sql_type="BIGINT", nullable=False, pk=True),
                    Column(name="payload", sql_type="JSONB", nullable=True, kind="json"),
                ],
            )
            table.pk = ["_row_id"]
        for col in table.columns:
            col.pk = col.name in table.pk
        tables.append(table)

    tables.sort(key=lambda t: (t.module, t.name))
    return tables


def _store_container(table: Table, modules: Dict[str, Any]) -> Any:
    return getattr(modules.get(table.module), table.store, None)


# ============================================================
# ROW EXTRACTION
# ============================================================


def _dump_row(obj: Any) -> Dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return dict(obj)
    return {"value": obj}


def extract_rows(table: Table, modules: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the current store contents as a list of column->value dicts."""
    container = _store_container(table, modules)
    if container is None:
        return []

    if table.kind == "keyed_json":
        return [{"key": str(k), "value": v} for k, v in container.items()]

    if table.kind == "nested_keyed":
        rows = []
        for entity_type, by_id in (container or {}).items():
            for entity_id, images in (by_id or {}).items():
                rows.append({"entity_type": entity_type, "entity_id": entity_id, "images": images})
        return rows

    if table.kind == "rows_generic":
        return [{"_row_id": i + 1, "payload": row} for i, row in enumerate(container or [])]

    # kind == "rows": list of models, or dict of models keyed by an internal id.
    if isinstance(container, dict):
        return [_dump_row(v) for v in container.values()]
    return [_dump_row(v) for v in container]


# ============================================================
# VALUE RENDERING
# ============================================================


def _quote(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def _float_literal(value: float) -> str:
    if isinstance(value, float) and not math.isfinite(value):
        return "NULL"
    return repr(value)


def _render_scalar(value: Any, sql_type: Optional[str] = None) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _float_literal(value)
    if isinstance(value, datetime):
        return "%s::timestamptz" % _quote(value.isoformat())
    if isinstance(value, date):
        return "%s::date" % _quote(value.isoformat())
    if isinstance(value, (dict, list)):
        return "%s::jsonb" % _quote(json.dumps(value, default=str, ensure_ascii=False))
    return _quote(str(value))


def _render_value(value: Any, column: Column) -> str:
    if column.kind == "json":
        if value is None:
            return "NULL"
        return "%s::jsonb" % _quote(json.dumps(value, default=str, ensure_ascii=False))
    if column.kind == "array":
        if value is None:
            return "NULL"
        elem_type = column.elem_sql or "TEXT"
        items = ", ".join(_render_scalar(v, elem_type) for v in value)
        return "ARRAY[%s]::%s[]" % (items, elem_type)
    return _render_scalar(value, column.sql_type)


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str, ensure_ascii=False)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


# ============================================================
# FOREIGN KEYS (curated + validated against the live data)
# ============================================================


def resolve_foreign_keys(
    tables: List[Table], rows_map: Dict[str, List[Dict[str, Any]]]
) -> Tuple[List[Tuple[str, str, str, str]], List[str]]:
    """Keep only relationships that exist and whose data is free of orphans."""
    by_name = {t.name: t for t in tables}
    accepted: List[Tuple[str, str, str, str]] = []
    warnings: List[str] = []

    for child, column, parent, parent_col in RELATIONSHIPS:
        ct = by_name.get(child)
        pt = by_name.get(parent)
        if ct is None or pt is None:
            warnings.append("skip %s.%s -> %s: table missing" % (child, column, parent))
            continue
        if column not in ct.column_names:
            warnings.append("skip %s.%s -> %s: column missing" % (child, column, parent))
            continue
        if parent_col not in pt.column_names:
            warnings.append("skip %s.%s -> %s.%s: target column missing"
                            % (child, column, parent, parent_col))
            continue
        if not pt.pk or parent_col not in pt.pk:
            warnings.append("skip %s.%s -> %s.%s: target is not a primary key"
                            % (child, column, parent, parent_col))
            continue

        parent_values = {
            r.get(parent_col) for r in rows_map.get(parent, []) if r.get(parent_col) is not None
        }
        orphans = 0
        for row in rows_map.get(child, []):
            val = row.get(column)
            if val is None:
                continue
            # Polymorphic/punctuation: only compare scalars.
            if isinstance(val, (dict, list)):
                continue
            if str(val) not in {str(p) for p in parent_values}:
                orphans += 1
        if orphans:
            warnings.append("skip %s.%s -> %s: %d orphan(s) in seeded data"
                            % (child, column, parent, orphans))
            continue
        accepted.append((child, column, parent, parent_col))
    return accepted, warnings


def insert_order(tables: List[Table], fks: List[Tuple[str, str, str, str]]) -> List[Table]:
    """Topologically sort so parents are inserted before children."""
    by_name = {t.name: t for t in tables}
    deps: Dict[str, set] = {t.name: set() for t in tables}
    for child, _column, parent, _pc in fks:
        if parent != child:
            deps[child].add(parent)
    ordered: List[Table] = []
    remaining = dict(deps)
    while remaining:
        ready = [n for n, d in remaining.items() if not (d - {t.name for t in ordered})]
        if not ready:  # cycle: emit the rest in stable order
            ready = sorted(remaining)
        for n in sorted(ready):
            if by_name[n] not in ordered:
                ordered.append(by_name[n])
            remaining.pop(n, None)
    return ordered


# ============================================================
# SQL EMISSION
# ============================================================

_HEADER = """-- ---------------------------------------------------------------------------
-- Arz-e-Pak portal - PostgreSQL migration (generated by backend/db_migration.py)
-- Migration version: {version}
-- Tables: {tables}   Rows: {rows}
-- Do not hand-edit: regenerate with `uv run python migrate_to_postgres.py all`.
-- ---------------------------------------------------------------------------
"""


def schema_sql(tables: List[Table], fks: List[Tuple[str, str, str, str]],
               drop: bool = False, row_count: int = 0) -> str:
    out: List[str] = []
    by_name = {t.name: t for t in tables}
    out.append(_HEADER.format(version=MIGRATION_VERSION, tables=len(tables),
                              rows=row_count))
    out.append("BEGIN;")
    out.append('CREATE SCHEMA IF NOT EXISTS %s;' % _q(SCHEMA))
    out.append("")

    if drop:
        for table in reversed(tables):
            out.append("DROP TABLE IF EXISTS %s CASCADE;" % table.qualified)
        out.append("")

    for table in tables:
        lines = []
        for col in table.columns:
            lines.append("    " + col.definition)
        if table.pk and table.kind in ("rows", "keyed_json", "nested_keyed"):
            lines.append("    PRIMARY KEY (%s)" % ", ".join(_q(p) for p in table.pk))
        out.append("CREATE TABLE IF NOT EXISTS %s (\n%s\n);" % (
            table.qualified, ",\n".join(lines)))
        out.append("COMMENT ON TABLE %s IS %s;" % (
            table.qualified, _quote("%s.%s (%s)" % (
                table.module, table.store, table.model or table.kind))))
    out.append("")

    # Secondary indexes: foreign-key-ish columns and common lookups.
    for table in tables:
        for col in table.columns:
            if col.pk:
                continue
            if col.name == "id" or col.name.endswith("_id") or col.name in (
                "status", "kind", "type", "created_at", "date",
            ):
                idx = "idx_%s_%s" % (table.name, col.name)
                out.append('CREATE INDEX IF NOT EXISTS %s ON %s (%s);'
                           % (_q(idx), table.qualified, _q(col.name)))
    out.append("")

    for child, column, parent, parent_col in fks:
        cname = "fk_%s_%s" % (child, column)
        ct = by_name.get(child)
        child_col = next((c for c in ct.columns if c.name == column), None) if ct else None
        delete_rule = " ON DELETE SET NULL" if (child_col is not None and child_col.nullable) else ""
        out.append(
            "ALTER TABLE %s ADD CONSTRAINT %s FOREIGN KEY (%s) "
            "REFERENCES %s.%s (%s)%s;"
            % (SCHEMA + "." + _q(child), _q(cname), _q(column),
               SCHEMA, _q(parent), _q(parent_col), delete_rule)
        )
    out.append("")
    out.append("COMMIT;")
    out.append("")
    return "\n".join(out)


def data_sql(tables: List[Table], rows_map: Dict[str, List[Dict[str, Any]]],
             cascade: bool = True) -> str:
    out: List[str] = []
    total = sum(len(rows_map.get(t.name, [])) for t in tables)
    out.append(_HEADER.format(version=MIGRATION_VERSION, tables=len(tables), rows=total))
    out.append("BEGIN;")
    if cascade:
        for table in reversed(tables):
            out.append("DELETE FROM %s;" % table.qualified)
        out.append("")
    for table in tables:
        rows = rows_map.get(table.name, [])
        cols = table.column_names
        out.append("-- %s (%d row%s)" % (table.name, len(rows), "" if len(rows) == 1 else "s"))
        for row in rows:
            values = []
            for col in table.columns:
                values.append(_render_value(row.get(col.name), col))
            out.append("INSERT INTO %s (%s) VALUES (%s);" % (
                table.qualified, ", ".join(_q(c) for c in cols), ", ".join(values)))
        out.append("")
    out.append("COMMIT;")
    out.append("")
    return "\n".join(out)


def load_sql(tables: List[Table]) -> str:
    """Bulk COPY load from the per-table CSV files (fastest path)."""
    out: List[str] = []
    out.append(_HEADER.format(version=MIGRATION_VERSION, tables=len(tables), rows="CSV"))
    out.append("\\set ON_ERROR_STOP on")
    out.append("BEGIN;")
    for table in tables:
        cols = ", ".join(_q(c) for c in table.column_names)
        rel = "data/%s.csv" % table.name
        out.append("\\copy %s (%s) FROM '%s' WITH (FORMAT csv, HEADER true, NULL '');"
                   % (table.qualified, cols, rel))
    out.append("COMMIT;")
    out.append("")
    return "\n".join(out)


def csv_text(table: Table, rows: List[Dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(table.column_names)
    for row in rows:
        writer.writerow([_csv_value(row.get(c)) for c in table.column_names])
    return buffer.getvalue()


def manifest(tables: List[Table], rows_map: Dict[str, List[Dict[str, Any]]],
             fks: List[Tuple[str, str, str, str]], warnings: List[str]) -> Dict[str, Any]:
    return {
        "generated_by": "backend/db_migration.py",
        "migration_version": MIGRATION_VERSION,
        "schema": SCHEMA,
        "table_count": len(tables),
        "row_count": sum(len(rows_map.get(t.name, [])) for t in tables),
        "tables": [
            {
                "table": "%s.%s" % (SCHEMA, t.name),
                "module": t.module,
                "store": t.store,
                "model": t.model,
                "kind": t.kind,
                "transient": t.transient,
                "rows": len(rows_map.get(t.name, [])),
                "primary_key": t.pk,
                "columns": [
                    {"name": c.name, "type": c.sql_type, "kind": c.kind,
                     "nullable": c.nullable, "pk": c.pk}
                    for c in t.columns
                ],
            }
            for t in tables
        ],
        "foreign_keys": [
            {"child": c, "column": col, "parent": p, "parent_column": pc}
            for c, col, p, pc in fks
        ],
        "foreign_key_warnings": warnings,
    }


# ============================================================
# DRIVER (optional) + APPLY + VERIFY
# ============================================================

_DRIVERS = ["psycopg", "psycopg2", "pg8000", "sqlite3"]


def load_driver() -> Tuple[Any, Optional[str]]:
    """Return (module, name) for the first available DB-API driver."""
    import importlib

    for name in _DRIVERS:
        try:
            return importlib.import_module(name), name
        except Exception:
            continue
    return None, None


def _requires_driver() -> Dict[str, Any]:
    return {
        "status": "requires_optional_dependency",
        "dependency": "psycopg",
        "detail": (
            "No DB-API driver is installed. Install one to apply the migration from "
            "Python (e.g. `uv add psycopg[binary]`), or load the generated SQL with "
            "`psql -f schema.sql -f data.sql`."
        ),
        "alternatives": ["psql -f db/schema.sql -f db/data.sql", "psql -f db/load.sql"],
    }


def _connect(dsn: str) -> Tuple[Any, Optional[str], Optional[Dict[str, Any]]]:
    driver, name = load_driver()
    if driver is None:
        return None, None, _requires_driver()
    return driver.connect(dsn), name, None


def apply_sql(dsn: str, statements: List[str]) -> Dict[str, Any]:
    """Execute the given SQL statements against ``dsn``. ``dsn`` may be a DSN or path."""
    conn, name, error = _connect(dsn)
    if error is not None:
        return error
    executed = 0
    try:
        with conn:
            cur = conn.cursor()
            for statement in statements:
                if statement.strip():
                    cur.execute(statement)
                    executed += 1
            conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return {"status": "ok", "driver": name, "statements": executed}


def verify_counts(dsn: str, expected: Dict[str, int]) -> Dict[str, Any]:
    """Compare live table counts against the manifest."""
    conn, name, error = _connect(dsn)
    if error is not None:
        return error
    result: Dict[str, Any] = {"status": "ok", "driver": name, "tables": {}, "mismatches": []}
    try:
        cur = conn.cursor()
        for table, want in sorted(expected.items()):
            cur.execute("SELECT count(*) FROM %s.%s" % (SCHEMA, _q(table)))
            got = int(cur.fetchone()[0])
            result["tables"][table] = {"expected": want, "actual": got, "ok": want == got}
            if want != got:
                result["mismatches"].append(
                    "%s.%s: expected %d, found %d" % (SCHEMA, table, want, got))
        result["status"] = "ok" if not result["mismatches"] else "mismatch"
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return result


# ============================================================
# POSTGIS SEAM
# ============================================================

# Latitude/longitude pairs are plain DOUBLE PRECISION columns by default so the
# migration stays portable. When PostGIS is available the helper below rewrites
# them into ``geography(Point,4326)`` columns with a trigger-free expression index,
# which is what the GIS search features want. It is emitted as a *separate*,
# optional migration so a plain PostgreSQL install still works.
GEO_COLUMNS: List[Tuple[str, str, str]] = [
    # (table, latitude column, longitude column)
    ("core_cities", "latitude", "longitude"),
    ("core_housing_schemes", "latitude", "longitude"),
    ("core_block_zone_areas", "latitude", "longitude"),
    ("core_properties", "latitude", "longitude"),
    ("core_big_projects", "latitude", "longitude"),
    ("core_pois", "latitude", "longitude"),
    ("core_aois", "latitude", "longitude"),
]


def postgis_sql(tables: List[Table]) -> str:
    by_name = {t.name: t for t in tables}
    out: List[str] = []
    out.append(_HEADER.format(version=MIGRATION_VERSION, tables=len(tables), rows="-"))
    out.append("-- Optional: enable geography columns + GiST indexes (requires PostGIS).")
    out.append("BEGIN;")
    out.append("CREATE EXTENSION IF NOT EXISTS postgis;")
    out.append("")
    for table, lat_col, lon_col in GEO_COLUMNS:
        t = by_name.get(table)
        if t is None or lat_col not in t.column_names or lon_col not in t.column_names:
            continue
        geo = "geog"
        out.append("ALTER TABLE %s ADD COLUMN IF NOT EXISTS %s geography(Point, 4326);"
                   % (t.qualified, _q(geo)))
        out.append(
            "UPDATE %s SET %s = ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography "
            "WHERE %s IS NOT NULL AND %s IS NOT NULL;"
            % (t.qualified, _q(geo), _q(lon_col), _q(lat_col), _q(lat_col), _q(lon_col)))
        out.append('CREATE INDEX IF NOT EXISTS %s ON %s USING GIST (%s);'
                   % (_q("gix_%s_geog" % table), t.qualified, _q(geo)))
    out.append("COMMIT;")
    out.append("")
    return "\n".join(out)


# ============================================================
# ORCHESTRATION
# ============================================================


def build_plan(include_transient: bool = False,
               modules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Reflect the live stores into a complete migration plan (no I/O)."""
    modules = modules if modules is not None else _load_modules()
    tables = discover_tables(include_transient=include_transient, modules=modules)
    rows_map = {t.name: extract_rows(t, modules) for t in tables}
    pk_warnings = validate_primary_keys(tables, rows_map)
    fks, fk_warnings = resolve_foreign_keys(tables, rows_map)
    ordered = insert_order(tables, fks)
    return {
        "tables": tables,
        "ordered": ordered,
        "rows_map": rows_map,
        "fks": fks,
        "warnings": pk_warnings + fk_warnings,
        "row_count": sum(len(v) for v in rows_map.values()),
    }


def expected_counts(plan: Dict[str, Any]) -> Dict[str, int]:
    return {t.name: len(plan["rows_map"].get(t.name, [])) for t in plan["tables"]}


def write_bundle(out_dir: str, include_transient: bool = False,
                 drop: bool = True, write_csv: bool = True) -> Dict[str, Any]:
    """Write schema.sql, data.sql, load.sql, manifest.json and CSV files.

    Returns a summary dict (also written to ``manifest.json``). This is the single
    entry point used by the CLI and by the test suite.
    """
    plan = build_plan(include_transient=include_transient)
    tables, ordered = plan["tables"], plan["ordered"]
    rows_map, fks = plan["rows_map"], plan["fks"]

    os.makedirs(out_dir, exist_ok=True)
    data_dir = os.path.join(out_dir, "data")
    if write_csv:
        os.makedirs(data_dir, exist_ok=True)

    written: List[str] = []

    def _write(relpath: str, text: str) -> None:
        path = os.path.join(out_dir, relpath)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        written.append(relpath)

    _write("schema.sql", schema_sql(tables, fks, drop=drop, row_count=plan["row_count"]))
    _write("data.sql", data_sql(ordered, rows_map, cascade=drop))
    _write("load.sql", load_sql(ordered))
    _write("postgis.sql", postgis_sql(tables))

    if write_csv:
        for table in ordered:
            rel = os.path.join("data", "%s.csv" % table.name)
            _write(rel, csv_text(table, rows_map.get(table.name, [])))

    summary = manifest(tables, rows_map, fks, plan["warnings"])
    summary["files"] = written
    summary["out_dir"] = os.path.abspath(out_dir)
    _write("manifest.json", json.dumps(summary, indent=2, default=str) + "\n")
    return summary
