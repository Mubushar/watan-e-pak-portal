"""
Turn an uploaded GIS file into a clean GeoJSON FeatureCollection for a portal layer.

Accepted: GeoJSON (.geojson / .json — a FeatureCollection, a Feature or a bare geometry),
KML (.kml, Google Earth), GPX (.gpx, GPS tracks / waypoints) and CSV (.csv with latitude /
longitude columns; other columns become properties). Shapefiles and KMZ should be converted
first (QGIS: Export → GeoJSON) — the error says so.

Every coordinate is checked (finite, inside lon -180..180 / lat -90..90); files whose points
look like [lat, lon] for Pakistan (lat 23–37, lon 60–78 swapped) are flipped and reported.
The result carries stats (feature count, geometry types, bounding box) so the admin can see what
was read before saving (``dry_run``).
"""

from __future__ import annotations

import base64
import csv
import io
import json
import math
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterable, List, Optional, Tuple

MAX_FEATURES = 50_000
MAX_BYTES = 25 * 1024 * 1024
GEOMETRY_TYPES = {"Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon", "GeometryCollection"}


class ImportError_(ValueError):
    """A file that can't become a layer (the message is shown to the admin)."""


# ---------------------------------------------------------------- reading


def decode(content: Optional[str], content_base64: Optional[str]) -> bytes:
    if content_base64:
        try:
            raw = base64.b64decode(content_base64.split(",")[-1], validate=False)
        except Exception:
            raise ImportError_("content_base64 is not valid base64")
    else:
        raw = (content or "").encode("utf-8")
    if not raw.strip():
        raise ImportError_("The file is empty")
    if len(raw) > MAX_BYTES:
        raise ImportError_(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB; simplify it or split it into several layers")
    return raw


def _format(filename: str, raw: bytes) -> str:
    name = (filename or "").lower()
    for ext, fmt in ((".geojson", "geojson"), (".json", "geojson"), (".kml", "kml"), (".gpx", "gpx"), (".csv", "csv")):
        if name.endswith(ext):
            return fmt
    if name.endswith((".zip", ".shp", ".kmz", ".gpkg")):
        raise ImportError_("Shapefiles, KMZ and GeoPackages aren't read directly: export the layer as GeoJSON "
                           "(QGIS: right-click the layer → Export → Save Features As… → GeoJSON) and upload that")
    head = raw.lstrip()[:200].lower()
    if head.startswith(b"{"):
        return "geojson"
    if b"<kml" in head:
        return "kml"
    if b"<gpx" in head:
        return "gpx"
    return "csv"


def _text(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ImportError_("Couldn't read the file's text encoding (save it as UTF-8)")


def _from_geojson(raw: bytes) -> List[Dict[str, Any]]:
    try:
        data = json.loads(_text(raw))
    except ValueError as exc:
        raise ImportError_(f"Not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise ImportError_("GeoJSON must be an object")
    kind = data.get("type")
    if kind == "FeatureCollection":
        return [f for f in data.get("features") or [] if isinstance(f, dict)]
    if kind == "Feature":
        return [data]
    if kind in GEOMETRY_TYPES:
        return [{"type": "Feature", "properties": {}, "geometry": data}]
    raise ImportError_("GeoJSON must be a FeatureCollection, a Feature or a geometry")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _kml_coords(text: str) -> List[List[float]]:
    out = []
    for chunk in (text or "").split():
        parts = chunk.split(",")
        if len(parts) >= 2:
            try:
                out.append([float(parts[0]), float(parts[1])])
            except ValueError:
                continue
    return out


def _from_kml(raw: bytes) -> List[Dict[str, Any]]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ImportError_(f"Not valid KML: {exc}")
    features = []
    for pm in root.iter():
        if _local(pm.tag) != "Placemark":
            continue
        props: Dict[str, Any] = {}
        geoms: List[Dict[str, Any]] = []
        for el in pm.iter():
            tag = _local(el.tag)
            if tag == "name" and el.text:
                props["name"] = el.text.strip()
            elif tag == "description" and el.text:
                props["description"] = el.text.strip()
            elif tag == "Data" and el.get("name"):
                val = next((c.text for c in el if _local(c.tag) == "value"), None)
                props[el.get("name")] = val
            elif tag == "SimpleData" and el.get("name"):
                props[el.get("name")] = el.text
            elif tag == "Point":
                c = _kml_coords(next((x.text for x in el.iter() if _local(x.tag) == "coordinates"), ""))
                if c:
                    geoms.append({"type": "Point", "coordinates": c[0]})
            elif tag == "LineString":
                c = _kml_coords(next((x.text for x in el.iter() if _local(x.tag) == "coordinates"), ""))
                if len(c) >= 2:
                    geoms.append({"type": "LineString", "coordinates": c})
            elif tag == "Polygon":
                rings = []
                for boundary in el:
                    if _local(boundary.tag) in ("outerBoundaryIs", "innerBoundaryIs"):
                        c = _kml_coords(next((x.text for x in boundary.iter() if _local(x.tag) == "coordinates"), ""))
                        if len(c) >= 4:
                            rings.append(c) if _local(boundary.tag) == "innerBoundaryIs" else rings.insert(0, c)
                if rings:
                    geoms.append({"type": "Polygon", "coordinates": rings})
        if not geoms:
            continue
        geometry = geoms[0] if len(geoms) == 1 else {"type": "GeometryCollection", "geometries": geoms}
        features.append({"type": "Feature", "properties": props, "geometry": geometry})
    return features


def _from_gpx(raw: bytes) -> List[Dict[str, Any]]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ImportError_(f"Not valid GPX: {exc}")
    features = []

    def name_of(el: Any) -> Dict[str, Any]:
        n = next((c.text for c in el if _local(c.tag) == "name"), None)
        return {"name": n} if n else {}

    for el in root:
        tag = _local(el.tag)
        if tag == "wpt":
            features.append({"type": "Feature", "properties": name_of(el),
                             "geometry": {"type": "Point", "coordinates": [float(el.get("lon")), float(el.get("lat"))]}})
        elif tag in ("trk", "rte"):
            pts = [[float(p.get("lon")), float(p.get("lat"))] for p in el.iter() if _local(p.tag) in ("trkpt", "rtept")]
            if len(pts) >= 2:
                features.append({"type": "Feature", "properties": name_of(el), "geometry": {"type": "LineString", "coordinates": pts}})
    return features


_LAT = ("latitude", "lat", "y", "lat_dd")
_LON = ("longitude", "lon", "lng", "long", "x", "lon_dd")


def _from_csv(raw: bytes) -> List[Dict[str, Any]]:
    text = _text(raw)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.DictReader(io.StringIO(text), dialect=dialect))
    if not rows:
        raise ImportError_("The CSV has no rows")
    cols = {c.lower().strip(): c for c in rows[0].keys() if c}
    lat = next((cols[c] for c in _LAT if c in cols), None)
    lon = next((cols[c] for c in _LON if c in cols), None)
    if not lat or not lon:
        raise ImportError_("The CSV needs latitude and longitude columns (lat / lon / lng also work)")
    features = []
    for row in rows:
        try:
            x, y = float(row[lon]), float(row[lat])
        except (TypeError, ValueError):
            continue
        props = {k: v for k, v in row.items() if k not in (lat, lon) and k}
        features.append({"type": "Feature", "properties": props, "geometry": {"type": "Point", "coordinates": [x, y]}})
    return features


# ---------------------------------------------------------------- checking


def _positions(geom: Dict[str, Any]) -> Iterable[List[float]]:
    t = geom.get("type")
    c = geom.get("coordinates")
    if t == "Point":
        yield c
    elif t in ("MultiPoint", "LineString"):
        yield from c or []
    elif t in ("MultiLineString", "Polygon"):
        for part in c or []:
            yield from part
    elif t == "MultiPolygon":
        for poly in c or []:
            for ring in poly:
                yield from ring
    elif t == "GeometryCollection":
        for g in geom.get("geometries") or []:
            yield from _positions(g)


def _map_positions(geom: Dict[str, Any], fn: Any) -> Dict[str, Any]:
    t = geom.get("type")
    if t == "GeometryCollection":
        return {**geom, "geometries": [_map_positions(g, fn) for g in geom.get("geometries") or []]}
    depth = {"Point": 0, "MultiPoint": 1, "LineString": 1, "MultiLineString": 2, "Polygon": 2, "MultiPolygon": 3}.get(t)

    def walk(c: Any, d: int) -> Any:
        return fn(c) if d == 0 else [walk(x, d - 1) for x in c]

    return {**geom, "coordinates": walk(geom.get("coordinates"), depth)} if depth is not None else geom


def _valid_position(p: Any) -> bool:
    return (isinstance(p, (list, tuple)) and len(p) >= 2 and all(isinstance(v, (int, float)) and math.isfinite(v) for v in p[:2])
            and -180 <= p[0] <= 180 and -90 <= p[1] <= 90)


def normalize(features: List[Dict[str, Any]], allow_empty: bool = False) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Validate, clean and describe features. Returns (FeatureCollection, stats)."""
    if not features and allow_empty:  # a layer created now and drawn later
        return {"type": "FeatureCollection", "features": []}, {"features": 0, "dropped": 0, "geometry_types": {}, "vertices": 0,
                                                               "bbox": None, "warnings": []}
    if len(features) > MAX_FEATURES:
        raise ImportError_(f"{len(features):,} features is more than the {MAX_FEATURES:,} a layer may hold; split the file")
    clean: List[Dict[str, Any]] = []
    dropped = 0
    for f in features:
        g = f.get("geometry")
        if not isinstance(g, dict) or g.get("type") not in GEOMETRY_TYPES:
            dropped += 1
            continue
        pts = list(_positions(g))
        if not pts or not all(_valid_position(p) for p in pts):
            dropped += 1
            continue
        props = f.get("properties") if isinstance(f.get("properties"), dict) else {}
        props = {str(k)[:80]: (v if isinstance(v, (str, int, float, bool)) or v is None else json.dumps(v, default=str))
                 for k, v in list(props.items())[:60]}
        clean.append({"type": "Feature", "properties": props, "geometry": g})
    if not clean:
        raise ImportError_("No valid features found (each needs a geometry with [longitude, latitude] coordinates)")
    # [lat, lon] written the wrong way round for Pakistan?
    pts = [p for f in clean for p in _positions(f["geometry"])]
    swapped = all(23 <= p[0] <= 37.5 and 60 <= p[1] <= 78 for p in pts[:5000])
    if swapped:
        clean = [{**f, "geometry": _map_positions(f["geometry"], lambda p: [p[1], p[0], *p[2:]])} for f in clean]
        pts = [[p[1], p[0]] for p in pts]
    lons, lats = [p[0] for p in pts], [p[1] for p in pts]
    types: Dict[str, int] = {}
    for f in clean:
        types[f["geometry"]["type"]] = types.get(f["geometry"]["type"], 0) + 1
    in_pk = sum(1 for x, y in zip(lons, lats) if 60 <= x <= 78 and 23 <= y <= 37.5) / max(1, len(pts))
    stats = {
        "features": len(clean), "dropped": dropped, "geometry_types": types, "vertices": len(pts),
        "bbox": [round(min(lons), 6), round(min(lats), 6), round(max(lons), 6), round(max(lats), 6)],
        "swapped_lat_lon": swapped, "inside_pakistan_pct": round(in_pk * 100, 1),
        "property_keys": sorted({k for f in clean[:500] for k in f["properties"]})[:30],
    }
    warnings = []
    if dropped:
        warnings.append(f"{dropped} feature(s) without a valid geometry were skipped")
    if swapped:
        warnings.append("Coordinates looked like [latitude, longitude]; they were flipped to GeoJSON's [longitude, latitude]")
    if in_pk < 0.5:
        warnings.append(f"Only {stats['inside_pakistan_pct']}% of the points are inside Pakistan — check the projection (it must be WGS84 / EPSG:4326)")
    stats["warnings"] = warnings
    return {"type": "FeatureCollection", "features": clean}, stats


def read(filename: str, content: Optional[str] = None, content_base64: Optional[str] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    raw = decode(content, content_base64)
    fmt = _format(filename, raw)
    reader = {"geojson": _from_geojson, "kml": _from_kml, "gpx": _from_gpx, "csv": _from_csv}[fmt]
    try:
        features = reader(raw)
    except ImportError_:
        raise
    except Exception as exc:  # a malformed file must never be a 500
        raise ImportError_(f"Couldn't read the {fmt.upper()} file ({type(exc).__name__}: {exc})")
    collection, stats = normalize(features)
    stats["format"] = fmt
    return collection, stats


def from_payload(geojson: Any) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Validate GeoJSON sent directly (create / update)."""
    raw = json.dumps(geojson).encode()
    collection, stats = normalize(_from_geojson(raw), allow_empty=True)
    stats["format"] = "geojson"
    return collection, stats
