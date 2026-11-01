"""
Durable storage for the portal's in-memory stores.

The portal keeps its working data in module-level containers (``properties_db``, ``leads_db``,
``GIS_LAYERS`` …) so reads are fast and every module can share them. This module makes those
containers survive a restart:

* every store found by :func:`db_migration.discover_tables` (the same reflection the PostgreSQL
  export uses) is written to one table, ``portal_rows(store, key, ord, data)``, one row per item;
* binary uploads are written to ``portal_assets`` (SQLite BLOB or PostgreSQL BYTEA), keyed by an
  opaque asset id and accompanied by their media type;
* writes are incremental: each flush hashes every item and only upserts what changed and deletes
  what is gone, so a busy store costs a few rows per flush;
* flushes run on a background thread a few seconds after any write request (the access guard
  marks the store dirty), once a minute regardless, and at shutdown;
* at startup, once the database has been seeded, its rows replace the freshly seeded sample data
  as a whole, so ids stay consistent across stores.

Backends: PostgreSQL when ``DATABASE_URL`` (``postgresql://…``) is set and ``psycopg`` is
installed (rows go into ``JSONB``), otherwise a local SQLite file (``PORTAL_DB_PATH``, default
``backend/data/portal.sqlite3``). ``PORTAL_PERSIST=0`` turns persistence off (the test suite does).

Bulky derived data is not copied: a GIS layer whose geometry is rebuilt from source files on
start (``geojson_ref``) is stored without its geometry and re-attached on load.
"""

from __future__ import annotations

import atexit
import hashlib
import importlib
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import portal_env

log = logging.getLogger("portal.storage")

HERE = os.path.dirname(os.path.abspath(__file__))
FLUSH_DELAY_SECONDS = float(portal_env.value("PORTAL_DB_FLUSH_SECONDS", "3") or 3)
FULL_FLUSH_SECONDS = 60.0

# Stores never written to the database: secrets in flight, rate limiters, caches.
SKIP_STORES = {
    "auth.otps_db",            # one-time codes expire within minutes
    "messaging.link_codes_db",
    "messaging.rate_db",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- encoding


def _type_path(obj: Any) -> Optional[str]:
    if hasattr(obj, "model_dump"):
        return f"{type(obj).__module__}.{type(obj).__qualname__}"
    return None


def _resolve_type(path: str) -> Any:
    module, _, name = path.rpartition(".")
    if module == "__main__":
        module = "server"
    return getattr(importlib.import_module(module), name)


# Hooks that shrink an item before it is stored and restore it on load, per store.
_SLIM: Dict[str, Tuple[Callable[[Any], Any], Callable[[Dict[str, Any]], Dict[str, Any]]]] = {}


def register_codec(store: str, exclude: Callable[[Any], Any],
                   restore: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
    """``store`` is ``module.attribute``; ``exclude(item)`` names the fields left out of the saved
    copy (or None) and ``restore`` fills them back in before the row becomes a model again."""
    _SLIM[store] = (exclude, restore)


def _encode(store: str, obj: Any) -> str:
    t = _type_path(obj)
    skip = _SLIM[store][0](obj) if t and store in _SLIM else None
    value = obj.model_dump(mode="json", exclude=skip or None) if t else obj
    return json.dumps({"t": t, "v": value}, default=str, ensure_ascii=False, sort_keys=True)


def _decode(store: str, text: Any) -> Any:
    env = text if isinstance(text, dict) else json.loads(text)
    t, value = env.get("t"), env.get("v")
    if not t:
        return value
    if store in _SLIM:
        value = _SLIM[store][1](value)
    return _resolve_type(t).model_validate(value)


def _encode_key(key: Any) -> str:
    return key if isinstance(key, str) else "json:" + json.dumps(key, default=str)


def _decode_key(key: str) -> Any:
    if not key.startswith("json:"):
        return key
    value = json.loads(key[5:])
    return tuple(value) if isinstance(value, list) else value


# ---------------------------------------------------------------- backends


class _SQLite:
    name = "sqlite"
    ph = "?"
    json_cast = "?"

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("CREATE TABLE IF NOT EXISTS portal_rows (store TEXT NOT NULL, key TEXT NOT NULL, "
                          "ord INTEGER NOT NULL, data TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY (store, key))")
        self.conn.execute("CREATE TABLE IF NOT EXISTS portal_kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS portal_assets (asset_key TEXT PRIMARY KEY, media_type TEXT NOT NULL, "
                          "data BLOB NOT NULL, updated_at TEXT NOT NULL)")

    def describe(self) -> str:
        return f"sqlite:{self.path}"

    def execute(self, sql: str, params: Iterable[Any] = ()) -> List[Tuple[Any, ...]]:
        return self.conn.execute(sql, tuple(params)).fetchall()

    def executemany(self, sql: str, rows: List[Tuple[Any, ...]]) -> None:
        self.conn.executemany(sql, rows)

    def begin(self) -> None:
        self.conn.execute("BEGIN")

    def commit(self) -> None:
        self.conn.execute("COMMIT")

    def rollback(self) -> None:
        self.conn.execute("ROLLBACK")

    def close(self) -> None:
        self.conn.close()


class _Postgres:
    name = "postgresql"
    ph = "%s"
    json_cast = "%s::jsonb"

    def __init__(self, url: str):
        import psycopg  # optional dependency: pip install "psycopg[binary]"

        self.url = url
        self.conn = psycopg.connect(url, autocommit=True)
        self.conn.execute("CREATE TABLE IF NOT EXISTS portal_rows (store TEXT NOT NULL, key TEXT NOT NULL, "
                          "ord INTEGER NOT NULL, data JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                          "PRIMARY KEY (store, key))")
        self.conn.execute("CREATE TABLE IF NOT EXISTS portal_kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS portal_assets (asset_key TEXT PRIMARY KEY, media_type TEXT NOT NULL, "
                          "data BYTEA NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now())")
        self.postgis_available = False
        self.postgis_raster_available = False
        self.pgvector_available = False
        try:
            self.conn.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            self.conn.execute("CREATE TABLE IF NOT EXISTS portal_gis_layer_catalog ("
                              "layer_id TEXT PRIMARY KEY, name TEXT NOT NULL, layer_type TEXT NOT NULL, "
                              "entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, published BOOLEAN NOT NULL, "
                              "visible BOOLEAN NOT NULL, source_file TEXT, style JSONB NOT NULL DEFAULT '{}'::jsonb, "
                              "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())")
            self.conn.execute("CREATE TABLE IF NOT EXISTS portal_gis_features ("
                              "layer_id TEXT NOT NULL REFERENCES portal_gis_layer_catalog(layer_id) ON DELETE CASCADE, "
                              "feature_id TEXT NOT NULL, properties JSONB NOT NULL DEFAULT '{}'::jsonb, "
                              "geom geometry(Geometry, 4326), PRIMARY KEY (layer_id, feature_id))")
            self.conn.execute("CREATE INDEX IF NOT EXISTS portal_gis_features_geom_gix "
                              "ON portal_gis_features USING GIST (geom)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS portal_gis_features_layer_idx "
                              "ON portal_gis_features (layer_id)")
            self.postgis_available = True
        except Exception as exc:
            # Keep generic PostgreSQL deployments operational; the GIS status endpoint makes the
            # missing PostGIS capability visible instead of silently claiming spatial storage.
            logging.getLogger("portal.storage").warning("PostGIS layer tables unavailable: %s", exc)
        if self.postgis_available:
            try:
                self.conn.execute("CREATE EXTENSION IF NOT EXISTS postgis_raster")
                self.conn.execute("CREATE TABLE IF NOT EXISTS portal_gis_rasters ("
                                  "layer_id TEXT PRIMARY KEY REFERENCES portal_gis_layer_catalog(layer_id) ON DELETE CASCADE, "
                                  "rast raster NOT NULL)")
                self.conn.execute("CREATE INDEX IF NOT EXISTS portal_gis_rasters_hull_gix "
                                  "ON portal_gis_rasters USING GIST (ST_ConvexHull(rast))")
                self.postgis_raster_available = True
            except Exception as exc:
                logging.getLogger("portal.storage").warning("PostGIS raster layer table unavailable: %s", exc)
        try:
            self.conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            self.conn.execute("CREATE TABLE IF NOT EXISTS portal_semantic_chunks ("
                              "chunk_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, source_type TEXT NOT NULL, "
                              "title TEXT NOT NULL, content TEXT NOT NULL, metadata JSONB NOT NULL DEFAULT '{}'::jsonb, "
                              "embedding vector(1536) NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now())")
            self.conn.execute("CREATE INDEX IF NOT EXISTS portal_semantic_chunks_embedding_idx "
                              "ON portal_semantic_chunks USING hnsw (embedding vector_cosine_ops)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS portal_semantic_chunks_source_idx "
                              "ON portal_semantic_chunks (source_type, source_id)")
            self.pgvector_available = True
        except Exception as exc:
            logging.getLogger("portal.storage").info("pgvector unavailable; semantic retrieval disabled: %s", exc)

    def describe(self) -> str:
        host = self.url.split("@")[-1]  # never report the password
        return f"postgresql://…@{host}"

    def execute(self, sql: str, params: Iterable[Any] = ()) -> List[Tuple[Any, ...]]:
        cur = self.conn.execute(sql, tuple(params))
        return cur.fetchall() if cur.description else []

    def executemany(self, sql: str, rows: List[Tuple[Any, ...]]) -> None:
        with self.conn.cursor() as cur:
            cur.executemany(sql, rows)

    def begin(self) -> None:
        self.conn.execute("BEGIN")

    def commit(self) -> None:
        self.conn.execute("COMMIT")

    def rollback(self) -> None:
        self.conn.execute("ROLLBACK")

    def close(self) -> None:
        self.conn.close()


def _open(url: str) -> Any:
    if url.startswith(("postgres://", "postgresql://")):
        return _Postgres(url)
    path = url[len("sqlite:///"):] if url.startswith("sqlite:///") else url
    return _SQLite(path or os.path.join(HERE, "data", "portal.sqlite3"))


# ---------------------------------------------------------------- the store


class Storage:
    """Mirrors a set of in-memory containers into a database."""

    def __init__(self, url: str, stores: Optional[Dict[str, Tuple[Any, str]]] = None):
        self.db = _open(url)
        self._stores = stores  # name -> (module object, attribute); discovered lazily
        self._hashes: Dict[str, Dict[str, str]] = {}
        self._frozen: Dict[str, str] = {}  # stores that failed to load: never overwritten
        self._lock = threading.RLock()
        self._dirty = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_flush: Optional[str] = None
        self.last_error: Optional[str] = None
        self.loaded_from_db = False

    # ---- discovery
    def stores(self) -> Dict[str, Tuple[Any, str]]:
        if self._stores is None:
            import db_migration

            modules = db_migration._load_modules()
            found: Dict[str, Tuple[Any, str]] = {}
            for table in db_migration.discover_tables(include_transient=False, modules=modules):
                name = f"{table.module}.{table.store}"
                if name not in SKIP_STORES:
                    found[name] = (modules[table.module], table.store)
            self._stores = found
        return self._stores

    def _container(self, name: str) -> Any:
        module, attr = self.stores()[name]
        return getattr(module, attr, None)

    # ---- kv
    def kv_get(self, key: str) -> Optional[str]:
        rows = self.db.execute(f"SELECT value FROM portal_kv WHERE key = {self.db.ph}", (key,))
        return rows[0][0] if rows else None

    def kv_set(self, key: str, value: str) -> None:
        ph = self.db.ph
        self.db.execute(f"INSERT INTO portal_kv (key, value) VALUES ({ph}, {ph}) "
                        f"ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, value))

    # ---- snapshot of one store: key -> (ord, json)
    def _snapshot(self, name: str) -> Dict[str, Tuple[int, str]]:
        container = self._container(name)
        out: Dict[str, Tuple[int, str]] = {}
        if isinstance(container, dict):
            for i, (k, v) in enumerate(list(container.items())):
                out[_encode_key(k)] = (i, _encode(name, v))
        elif isinstance(container, list):
            for i, item in enumerate(list(container)):
                ident = None
                for attr in ("id", "token", "code", "user_id", "name"):
                    ident = getattr(item, attr, None) if not isinstance(item, dict) else item.get(attr)
                    if isinstance(ident, (str, int)) and ident != "":
                        break
                    ident = None
                key = f"{ident}" if ident is not None else f"#{i}"
                if key in out:  # a duplicate id: keep both, positionally
                    key = f"{key}#{i}"
                out[key] = (i, _encode(name, item))
        return out

    # ---- flush
    def flush(self, full: bool = False) -> Dict[str, int]:
        """Write what changed since the last flush (``full`` rewrites every hash check from
        the database's point of view, used for the first save)."""
        with self._lock:
            self._dirty.clear()
            ph, cast = self.db.ph, self.db.json_cast
            upsert = (f"INSERT INTO portal_rows (store, key, ord, data, updated_at) VALUES ({ph}, {ph}, {ph}, {cast}, {ph}) "
                      f"ON CONFLICT (store, key) DO UPDATE SET ord = EXCLUDED.ord, data = EXCLUDED.data, updated_at = EXCLUDED.updated_at")
            delete = f"DELETE FROM portal_rows WHERE store = {ph} AND key = {ph}"
            written = removed = 0
            now = _now()
            self.db.begin()
            try:
                for name in self.stores():
                    if name in self._frozen:
                        continue
                    snap = self._snapshot(name)
                    current = {k: hashlib.sha1(f"{o}|{d}".encode()).hexdigest() for k, (o, d) in snap.items()}
                    previous = {} if full else self._hashes.get(name, {})
                    changed = [(name, k, snap[k][0], snap[k][1], now) for k, h in current.items() if previous.get(k) != h]
                    gone = [(name, k) for k in previous if k not in current]
                    if full:
                        gone = [(name, k) for (k,) in self.db.execute(f"SELECT key FROM portal_rows WHERE store = {ph}", (name,))
                                if k not in current]
                    if changed:
                        self.db.executemany(upsert, changed)
                    if gone:
                        self.db.executemany(delete, gone)
                    written += len(changed)
                    removed += len(gone)
                    self._hashes[name] = current
                self.kv_set("stores", json.dumps(sorted(self.stores())))
                self.kv_set("seeded", "1")
                self.db.commit()
            except Exception as exc:
                self.db.rollback()
                self._hashes.clear()  # resync everything next time
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.exception("storage flush failed")
                raise
            self.last_flush = now
            self.last_error = None
            return {"written": written, "removed": removed}

    # ---- load
    def load(self) -> Dict[str, Any]:
        """Replace the seeded stores with the database's rows, or save the seed on first run."""
        with self._lock:
            if self.kv_get("seeded") != "1":
                result = self.flush(full=True)
                return {"loaded": False, "seeded": True, **result}
            known = set(json.loads(self.kv_get("stores") or "[]"))
            rows: Dict[str, List[Tuple[str, int, Any]]] = {}
            for store, key, ord_, data in self.db.execute("SELECT store, key, ord, data FROM portal_rows ORDER BY store, ord"):
                rows.setdefault(store, []).append((key, ord_, data))
            restored = 0
            for name in self.stores():
                if name not in known:
                    continue  # a store added in a newer version keeps its seed
                container = self._container(name)
                try:
                    if isinstance(container, dict):
                        fresh = {_decode_key(k): _decode(name, d) for k, _o, d in rows.get(name, [])}
                        container.clear()
                        container.update(fresh)
                    elif isinstance(container, list):
                        container[:] = [_decode(name, d) for _k, _o, d in rows.get(name, [])]
                    restored += len(rows.get(name, []))
                except Exception as exc:  # keep the seed, and never overwrite the stored rows
                    self._frozen[name] = f"{type(exc).__name__}: {exc}"
                    log.error("storage: could not load %s (%s); keeping its sample data", name, exc)
            self.loaded_from_db = True
            # the hashes now describe what is in the database
            self.flush(full=True)
            return {"loaded": True, "rows": restored, "frozen": dict(self._frozen)}

    # ---- background writer
    def mark_dirty(self) -> None:
        self._dirty.set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="portal-storage", daemon=True)
        self._thread.start()
        atexit.register(self.stop)

    def _run(self) -> None:
        while not self._stop.is_set():
            woke = self._dirty.wait(timeout=FULL_FLUSH_SECONDS)
            if self._stop.is_set():
                break
            if woke:  # let a burst of writes settle
                self._stop.wait(FLUSH_DELAY_SECONDS)
            try:
                self.flush()
            except Exception:
                pass  # logged in flush; retried on the next tick

    def stop(self) -> None:
        self._stop.set()
        self._dirty.set()
        # Let a flush already running on the worker finish before the final one, so the
        # connection is never closed underneath it (that crashed the process on shutdown).
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=30)
        try:
            self.flush()
        except Exception:
            pass

    # ---- binary assets
    def put_asset(self, asset_key: str, media_type: str, data: bytes) -> None:
        ph = self.db.ph
        self.db.execute(
            f"INSERT INTO portal_assets (asset_key, media_type, data, updated_at) VALUES ({ph}, {ph}, {ph}, {ph}) "
            "ON CONFLICT (asset_key) DO UPDATE SET media_type = EXCLUDED.media_type, "
            "data = EXCLUDED.data, updated_at = EXCLUDED.updated_at",
            (asset_key, media_type, data, _now()),
        )

    def get_asset(self, asset_key: str) -> Optional[Tuple[bytes, str]]:
        rows = self.db.execute(
            f"SELECT data, media_type FROM portal_assets WHERE asset_key = {self.db.ph}", (asset_key,)
        )
        return (bytes(rows[0][0]), rows[0][1]) if rows else None

    def has_asset(self, asset_key: str) -> bool:
        return bool(self.db.execute(
            f"SELECT 1 FROM portal_assets WHERE asset_key = {self.db.ph}", (asset_key,)
        ))

    def delete_asset(self, asset_key: str) -> None:
        self.db.execute(f"DELETE FROM portal_assets WHERE asset_key = {self.db.ph}", (asset_key,))

    def gis_storage_status(self) -> Dict[str, Any]:
        """Describe whether uploaded GIS features have a native PostGIS geometry store."""
        if getattr(self.db, "name", "") != "postgresql":
            return {"backend": self.db.name, "spatial": False, "format": "GeoJSON in portal_rows"}
        if not getattr(self.db, "postgis_available", False):
            return {"backend": "postgresql", "spatial": False, "format": "JSONB fallback",
                    "detail": "Enable the PostGIS extension and restart the backend."}
        return {"backend": "postgresql", "spatial": True, "format": "PostGIS geometry + JSONB properties",
                "catalog_table": "portal_gis_layer_catalog", "feature_table": "portal_gis_features",
                "raster": bool(getattr(self.db, "postgis_raster_available", False)),
                "raster_table": "portal_gis_rasters" if getattr(self.db, "postgis_raster_available", False) else None}

    def semantic_storage_status(self) -> Dict[str, Any]:
        available = bool(getattr(self.db, "pgvector_available", False))
        count = int(self.db.execute("SELECT COUNT(*) FROM portal_semantic_chunks")[0][0]) if available else 0
        return {"backend": self.db.name, "vector_store": available,
                "indexed_chunks": count,
                "table": "portal_semantic_chunks" if available else None}

    def semantic_upsert(self, chunks: Iterable[Dict[str, Any]]) -> int:
        if not getattr(self.db, "pgvector_available", False):
            return 0
        rows = list(chunks)
        if not rows:
            return 0
        ph = self.db.ph
        self.db.begin()
        try:
            ids = [str(row["chunk_id"]) for row in rows]
            self.db.execute(f"DELETE FROM portal_semantic_chunks WHERE chunk_id = ANY({ph})", (ids,))
            for row in rows:
                vector = "[" + ",".join(str(float(x)) for x in row["embedding"]) + "]"
                self.db.execute("INSERT INTO portal_semantic_chunks "
                                "(chunk_id,source_id,source_type,title,content,metadata,embedding) "
                                f"VALUES ({ph},{ph},{ph},{ph},{ph},{ph}::jsonb,{ph}::vector)",
                                (row["chunk_id"], row["source_id"], row["source_type"], row["title"],
                                 row["content"], json.dumps(row.get("metadata") or {}, ensure_ascii=False), vector))
            self.db.commit()
            return len(rows)
        except Exception:
            self.db.rollback()
            raise

    def semantic_clear(self) -> bool:
        if not getattr(self.db, "pgvector_available", False):
            return False
        self.db.execute("TRUNCATE TABLE portal_semantic_chunks")
        return True

    def semantic_replace(self, chunks: Iterable[Dict[str, Any]]) -> int:
        """Atomically replace the vector index after every embedding batch is ready."""
        if not getattr(self.db, "pgvector_available", False):
            return 0
        rows = list(chunks)
        ph = self.db.ph
        self.db.begin()
        try:
            self.db.execute("TRUNCATE TABLE portal_semantic_chunks")
            for start in range(0, len(rows), 64):
                for row in rows[start:start + 64]:
                    vector = "[" + ",".join(str(float(x)) for x in row["embedding"]) + "]"
                    self.db.execute("INSERT INTO portal_semantic_chunks "
                                    "(chunk_id,source_id,source_type,title,content,metadata,embedding) "
                                    f"VALUES ({ph},{ph},{ph},{ph},{ph},{ph}::jsonb,{ph}::vector)",
                                    (row["chunk_id"], row["source_id"], row["source_type"], row["title"],
                                     row["content"], json.dumps(row.get("metadata") or {}, ensure_ascii=False), vector))
            self.db.commit()
            return len(rows)
        except Exception:
            self.db.rollback()
            raise

    def semantic_search(self, embedding: List[float], limit: int = 8) -> List[Dict[str, Any]]:
        if not getattr(self.db, "pgvector_available", False):
            return []
        vector = "[" + ",".join(str(float(x)) for x in embedding) + "]"
        rows = self.db.execute("SELECT chunk_id,source_id,source_type,title,content,metadata, "
                               f"1-(embedding <=> {self.db.ph}::vector) AS score FROM portal_semantic_chunks "
                               f"ORDER BY embedding <=> {self.db.ph}::vector LIMIT {int(max(1,min(limit,30)))}",
                               (vector, vector))
        return [{"chunk_id": r[0], "source_id": r[1], "source_type": r[2], "title": r[3],
                 "content": r[4], "metadata": r[5], "score": float(r[6])} for r in rows]

    def sync_gis_layer(self, layer: Any) -> bool:
        """Mirror a portal vector layer into PostGIS. The JSONB store remains the app's metadata source."""
        if not getattr(self.db, "postgis_available", False):
            return False
        value = layer.model_dump(mode="json") if hasattr(layer, "model_dump") else dict(layer)
        layer_id = str(value["id"])
        ph = self.db.ph
        self.db.begin()
        try:
            self.db.execute(
                "INSERT INTO portal_gis_layer_catalog "
                "(layer_id,name,layer_type,entity_type,entity_id,published,visible,source_file,style,updated_at) "
                f"VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph}::jsonb,now()) "
                "ON CONFLICT (layer_id) DO UPDATE SET name=EXCLUDED.name, layer_type=EXCLUDED.layer_type, "
                "entity_type=EXCLUDED.entity_type, entity_id=EXCLUDED.entity_id, published=EXCLUDED.published, "
                "visible=EXCLUDED.visible, source_file=EXCLUDED.source_file, style=EXCLUDED.style, updated_at=now()",
                (layer_id, value.get("name") or "GIS layer", value.get("layer_type") or "other",
                 value.get("entity_type") or "city", value.get("entity_id") or "pakistan",
                 bool(value.get("published", True)), bool(value.get("visible", True)), value.get("source_file"),
                 json.dumps(value.get("style") or {}, ensure_ascii=False)),
            )
            self.db.execute(f"DELETE FROM portal_gis_features WHERE layer_id={ph}", (layer_id,))
            rows = []
            features = (value.get("geojson") or {}).get("features") or []
            for index, feature in enumerate(features):
                geometry = feature.get("geometry")
                if not geometry:
                    continue
                rows.append((layer_id, f"{index}:{feature.get('id') or ''}",
                             json.dumps(feature.get("properties") or {}, ensure_ascii=False),
                             json.dumps(geometry, ensure_ascii=False)))
            if rows:
                self.db.executemany(
                    "INSERT INTO portal_gis_features (layer_id,feature_id,properties,geom) "
                    f"VALUES ({ph},{ph},{ph}::jsonb,ST_Force2D(ST_SetSRID(ST_GeomFromGeoJSON({ph}),4326)))",
                    rows,
                )
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            raise

    def delete_gis_layer(self, layer_id: str) -> bool:
        if not getattr(self.db, "postgis_available", False):
            return False
        self.db.execute(f"DELETE FROM portal_gis_layer_catalog WHERE layer_id={self.db.ph}", (layer_id,))
        return True

    def sync_gis_raster(self, layer_id: str, geotiff: bytes) -> bool:
        """Store a georeferenced GeoTIFF as a PostGIS raster tile when raster support is enabled."""
        if not getattr(self.db, "postgis_raster_available", False):
            return False
        ph = self.db.ph
        self.db.execute(
            "INSERT INTO portal_gis_rasters (layer_id, rast) "
            f"VALUES ({ph}, ST_FromGDALRaster({ph})) "
            "ON CONFLICT (layer_id) DO UPDATE SET rast=EXCLUDED.rast",
            (layer_id, geotiff),
        )
        return True

    def delete_gis_raster(self, layer_id: str) -> bool:
        if not getattr(self.db, "postgis_raster_available", False):
            return False
        self.db.execute(f"DELETE FROM portal_gis_rasters WHERE layer_id={self.db.ph}", (layer_id,))
        return True

    def sync_gis_layers(self, layers: Iterable[Any]) -> int:
        if not getattr(self.db, "postgis_available", False):
            return 0
        count = 0
        for layer in layers:
            if not getattr(layer, "geojson_ref", None):
                self.sync_gis_layer(layer)
                count += 1
        return count

    def import_directory(self, directory: str, prefix: str = "") -> int:
        """Import legacy files once, leaving the original files untouched as a recovery copy."""
        added = 0
        for parent, _dirs, names in os.walk(directory):
            for name in names:
                path = os.path.join(parent, name)
                rel = os.path.relpath(path, directory).replace(os.sep, "/")
                key = f"{prefix.rstrip('/')}/{rel}" if prefix else rel
                if self.has_asset(key):
                    continue
                import mimetypes
                media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
                with open(path, "rb") as fh:
                    self.put_asset(key, media_type, fh.read())
                added += 1
        return added

    def import_seed_assets(self, backend_dir: str) -> int:
        """Persist reference vector/OSM sources once; generated master-plan PNG tiles stay a cache."""
        if self.kv_get("seed_assets_v1") == "1":
            return 0
        selected: List[str] = []
        for directory in ("geodata", "media/boundaries", "media/roads", "media/water"):
            base = os.path.join(backend_dir, directory)
            if not os.path.isdir(base):
                continue
            for parent, _dirs, names in os.walk(base):
                for name in names:
                    if os.path.splitext(name)[1].lower() in (".json", ".geojson", ".gz"):
                        selected.append(os.path.join(parent, name))
        osm = os.path.join(backend_dir, "media", "osm", "pakistan-latest.osm.pbf")
        if os.path.isfile(osm):
            selected.append(osm)
        plans = os.path.join(backend_dir, "media", "masterplans")
        for name in ("plans.json", "labels.json.gz", "knowledge.json"):
            path = os.path.join(plans, name)
            if os.path.isfile(path):
                selected.append(path)
        added = 0
        for path in selected:
            rel = os.path.relpath(path, backend_dir).replace(os.sep, "/")
            if self.has_asset(f"seed/{rel}"):
                continue
            import mimetypes
            media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
            with open(path, "rb") as fh:
                self.put_asset(f"seed/{rel}", media_type, fh.read())
            added += 1
        self.kv_set("seed_assets_v1", "1")
        return added

    def read_seed_asset(self, relative_path: str, fallback_path: Optional[str] = None) -> Optional[bytes]:
        key = "seed/" + relative_path.replace("\\", "/").lstrip("/")
        asset = self.get_asset(key)
        if asset:
            return asset[0]
        if fallback_path and os.path.isfile(fallback_path):
            with open(fallback_path, "rb") as fh:
                return fh.read()
        return None

    def status(self) -> Dict[str, Any]:
        counts = dict(self.db.execute("SELECT store, COUNT(*) FROM portal_rows GROUP BY store"))
        return {
            "backend": self.db.name, "location": self.db.describe(), "loaded_from_database": self.loaded_from_db,
            "last_flush": self.last_flush, "last_error": self.last_error, "frozen": dict(self._frozen),
            "stores": len(self.stores()), "rows": sum(int(v) for v in counts.values()),
            "rows_by_store": {k: int(v) for k, v in sorted(counts.items())},
            "assets": int(self.db.execute("SELECT COUNT(*) FROM portal_assets")[0][0]),
            "asset_bytes": int(self.db.execute("SELECT COALESCE(SUM(length(data)), 0) FROM portal_assets")[0][0]),
        }


# ---------------------------------------------------------------- process-wide instance

_instance: Optional[Storage] = None


def enabled() -> bool:
    return portal_env.flag("PORTAL_PERSIST", True)


def database_url() -> str:
    return (os.getenv("DATABASE_URL") or "").strip() or (os.getenv("PORTAL_DB_PATH") or "").strip()


def instance() -> Optional[Storage]:
    return _instance


def put_asset(asset_key: str, media_type: str, data: bytes) -> bool:
    if _instance is None:
        return False
    with _instance._lock:
        _instance.put_asset(asset_key, media_type, data)
    return True


def get_asset(asset_key: str) -> Optional[Tuple[bytes, str]]:
    if _instance is None:
        return None
    with _instance._lock:
        return _instance.get_asset(asset_key)


def delete_asset(asset_key: str) -> None:
    if _instance is not None:
        with _instance._lock:
            _instance.delete_asset(asset_key)


def has_asset(asset_key: str) -> bool:
    if _instance is None:
        return False
    with _instance._lock:
        return _instance.has_asset(asset_key)


def import_assets_from_directory(directory: str, prefix: str = "") -> int:
    if _instance is None or not os.path.isdir(directory):
        return 0
    with _instance._lock:
        return _instance.import_directory(directory, prefix)


def import_seed_assets(backend_dir: str) -> int:
    if _instance is None:
        return 0
    with _instance._lock:
        return _instance.import_seed_assets(backend_dir)


def read_seed_asset(relative_path: str, fallback_path: Optional[str] = None) -> Optional[bytes]:
    if _instance is not None:
        with _instance._lock:
            return _instance.read_seed_asset(relative_path, fallback_path)
    if fallback_path and os.path.isfile(fallback_path):
        with open(fallback_path, "rb") as fh:
            return fh.read()
    return None


def start() -> Dict[str, Any]:
    """Open the database, load (or seed) it and start the background writer."""
    global _instance
    if not enabled():
        return {"enabled": False}
    if _instance is not None:
        return {"enabled": True, "already_started": True}
    url = database_url()
    try:
        store = Storage(url)
    except ImportError:
        log.error("DATABASE_URL points at PostgreSQL but psycopg is not installed; using SQLite. "
                  "Install it with: pip install \"psycopg[binary]\"")
        store = Storage("")
    result = store.load()
    store.start()
    _instance = store
    log.info("storage: %s (%s)", store.db.describe(), result)
    return {"enabled": True, **result}


def mark_dirty() -> None:
    if _instance is not None:
        _instance.mark_dirty()


def stop() -> None:
    global _instance
    if _instance is not None:
        _instance.stop()
        with _instance._lock:
            _instance.db.close()
        _instance = None
