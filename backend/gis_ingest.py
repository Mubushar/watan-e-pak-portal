"""GIS file ingestion helpers for vector and georeferenced raster uploads.

GDAL/OGR is an optional system dependency. Vector formats are normalized to WGS84
GeoJSON; rasters are reprojected to WGS84 GeoTIFF and a small PNG map preview.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import gis_import

MAX_ARCHIVE_BYTES = 250 * 1024 * 1024
VECTOR_EXTENSIONS = {".shp", ".gdb", ".gpkg", ".dgn", ".dwg", ".pdf"}
RASTER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".ecw", ".pdf"}


def _run(args: List[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise gis_import.ImportError_(f"GIS conversion tool '{args[0]}' is unavailable. Install GDAL/OGR on the portal backend.") from exc
    except subprocess.TimeoutExpired as exc:
        raise gis_import.ImportError_(f"GIS conversion exceeded {timeout} seconds. Simplify or split the source file.") from exc
    if result.returncode:
        message = (result.stderr or result.stdout or "conversion failed").strip()
        raise gis_import.ImportError_(message[-1800:])
    return result


def _safe_unzip(raw: bytes, folder: Path) -> List[Path]:
    try:
        archive = zipfile.ZipFile(__import__("io").BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise gis_import.ImportError_("The ZIP archive is invalid") from exc
    files: List[Path] = []
    total = 0
    with archive:
        for item in archive.infolist():
            name = item.filename.replace("\\", "/")
            parts = Path(name).parts
            if item.is_dir():
                continue
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or any(p in ("..", "") for p in parts) or item.flag_bits & 1:
                raise gis_import.ImportError_("The archive contains an unsafe or encrypted path")
            total += item.file_size
            if total > MAX_ARCHIVE_BYTES:
                raise gis_import.ImportError_("The expanded archive is larger than 250 MB")
            target = folder.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            files.append(target)
    return files


def _vector_input(filename: str, raw: bytes, folder: Path) -> Path:
    ext = Path(filename).suffix.lower()
    if ext == ".zip":
        files = _safe_unzip(raw, folder / "archive")
        geodatabases = [p for p in (folder / "archive").rglob("*.gdb") if p.is_dir()]
        if geodatabases:
            return geodatabases[0]
        candidates = [p for p in files if p.suffix.lower() in (".shp", ".gpkg", ".dgn", ".dwg", ".pdf")]
        if not candidates:
            raise gis_import.ImportError_("ZIP must contain a shapefile set, GeoPackage, file geodatabase (.gdb), DGN, DWG or GeoPDF")
        return candidates[0]
    if ext == ".gdb":
        raise gis_import.ImportError_("Upload a .gdb folder as a ZIP archive so all of its files arrive together")
    path = folder / (re.sub(r"[^A-Za-z0-9_.-]", "_", Path(filename).name) or "source.bin")
    path.write_bytes(raw)
    return path


def _vector(filename: str, raw: bytes, source_crs: Optional[str]) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="portal-gis-vector-") as temp:
        folder = Path(temp)
        source = _vector_input(filename, raw, folder)
        output = folder / "features.geojson"
        args = ["ogr2ogr", "-f", "GeoJSON", str(output), str(source), "-t_srs", "EPSG:4326", "-dim", "XY"]
        if source_crs:
            args.extend(["-s_srs", source_crs])
        _run(args)
        if not output.is_file() or output.stat().st_size == 0:
            raise gis_import.ImportError_("No vector features were found in this file")
        collection, stats = gis_import.read("features.geojson", content_base64=base64.b64encode(output.read_bytes()).decode("ascii"))
        stats["format"] = Path(filename).suffix.lower().lstrip(".") or "zip"
        stats["source_crs"] = source_crs or "detected by GDAL/OGR"
        return {"kind": "vector", "geojson": collection, "import": stats}


def _raster_info(path: Path) -> Dict[str, Any]:
    result = _run(["gdalinfo", "-json", str(path)])
    try:
        return json.loads(result.stdout)
    except ValueError as exc:
        raise gis_import.ImportError_("GDAL returned invalid raster metadata") from exc


def _preview(path: Path, folder: Path, size: List[int]) -> bytes:
    width, height = size
    factor = min(1.0, 1800 / max(width, height, 1))
    w, h = max(1, round(width * factor)), max(1, round(height * factor))
    png = folder / "preview.png"
    _run(["gdal_translate", "-q", "-of", "PNG", "-outsize", str(w), str(h), str(path), str(png)])
    if not png.exists():
        raise gis_import.ImportError_("GDAL could not render a preview for this raster")
    return png.read_bytes()


def _bounds(info: Dict[str, Any]) -> List[List[float]]:
    corners = info.get("cornerCoordinates") or {}
    points = [corners.get(k) for k in ("upperLeft", "upperRight", "lowerLeft", "lowerRight")]
    points = [p for p in points if isinstance(p, list) and len(p) >= 2]
    if not points:
        extent = info.get("wgs84Extent", {}).get("coordinates")
        def walk(v: Any) -> None:
            if isinstance(v, list) and len(v) >= 2 and all(isinstance(x, (int, float)) for x in v[:2]):
                points.append(v[:2])
            elif isinstance(v, list):
                for child in v:
                    walk(child)
        if extent:
            walk(extent)
    if not points:
        raise gis_import.ImportError_("Raster has no usable geographic bounds after reprojection")
    lons = [float(p[0]) for p in points]
    lats = [float(p[1]) for p in points]
    if not (-180 <= min(lons) <= max(lons) <= 180 and -90 <= min(lats) <= max(lats) <= 90):
        raise gis_import.ImportError_("Raster reprojection produced invalid WGS84 coordinates")
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


def _raster(filename: str, raw: bytes, source_crs: Optional[str], mode: str,
            control_points: Optional[List[Dict[str, Any]]], dry_run: bool) -> Dict[str, Any]:
    ext = Path(filename).suffix.lower()
    with tempfile.TemporaryDirectory(prefix="portal-gis-raster-") as temp:
        folder = Path(temp)
        source = folder / ("source" + (ext if ext else ".bin"))
        source.write_bytes(raw)
        info = _raster_info(source)
        size = info.get("size") or []
        if len(size) < 2:
            raise gis_import.ImportError_("Could not read the raster image dimensions")
        original_preview = _preview(source, folder, [int(size[0]), int(size[1])])
        gcps = control_points or []
        embedded = bool(info.get("geoTransform") or (info.get("gcps") or {}).get("gcpList"))
        needs_points = mode == "manual" or bool(control_points) or (mode == "assisted" and not embedded)
        fit: Optional[Dict[str, Any]] = None
        working = source
        if needs_points:
            if len(gcps) > 50:
                raise gis_import.ImportError_("Use at most 50 ground control points")
            if len(gcps) < 3:
                if dry_run:
                    return {"kind": "raster", "preview_base64": base64.b64encode(original_preview).decode("ascii"),
                            "width": int(size[0]), "height": int(size[1]), "requires_control_points": True,
                            "embedded_georeference": embedded, "detected_crs": (info.get("coordinateSystem") or {}).get("wkt"),
                            "import": {"format": ext.lstrip("."), "features": 0, "warnings": ["Add at least 3 well-spread ground control points"]}}
                raise gis_import.ImportError_("Manual georeferencing needs at least 3 ground control points")
            for point in gcps:
                px = point.get("image") or point.get("px")
                geo = point.get("geo") or point.get("latlon")
                if not px or not geo or len(px) < 2 or len(geo) < 2:
                    raise gis_import.ImportError_("Each control point needs image [x,y] and geographic [latitude,longitude]")
                try:
                    x, y, lat, lon = float(px[0]), float(px[1]), float(geo[0]), float(geo[1])
                except (TypeError, ValueError) as exc:
                    raise gis_import.ImportError_("Control point coordinates must be numeric") from exc
                if not (0 <= x <= int(size[0]) and 0 <= y <= int(size[1])):
                    raise gis_import.ImportError_("A control point pixel lies outside the source image")
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise gis_import.ImportError_("Control point latitude/longitude must be valid WGS84 coordinates")
            from tools import georeference
            fit = georeference(gcps)
            if fit.get("error"):
                raise gis_import.ImportError_(fit["error"])
            vrt = folder / "control-points.vrt"
            args = ["gdal_translate", "-q", "-of", "VRT", "-a_srs", "EPSG:4326"]
            for point in gcps:
                px = point.get("image") or point.get("px")
                geo = point.get("geo") or point.get("latlon")
                args += ["-gcp", str(px[0]), str(px[1]), str(geo[1]), str(geo[0])]
            args += [str(source), str(vrt)]
            _run(args)
            working = vrt
        elif source_crs and not ((info.get("coordinateSystem") or {}).get("wkt") or
                                 ((info.get("gcps") or {}).get("coordinateSystem") or {}).get("wkt")):
            tagged = folder / "tagged.vrt"
            _run(["gdal_translate", "-q", "-of", "VRT", "-a_srs", source_crs, str(source), str(tagged)])
            working = tagged
            info["coordinateSystem"] = {"wkt": source_crs}
            embedded = bool(info.get("geoTransform"))

        if not embedded and not needs_points:
            if dry_run:
                return {"kind": "raster", "preview_base64": base64.b64encode(original_preview).decode("ascii"),
                        "width": int(size[0]), "height": int(size[1]), "requires_control_points": True,
                        "embedded_georeference": False, "detected_crs": source_crs,
                        "import": {"format": ext.lstrip("."), "features": 0, "warnings": ["No embedded location found; add ground control points"]}}
            raise gis_import.ImportError_("This image has no embedded geographic transform. Add ground control points or select its source CRS and coordinates.")

        warped = folder / "warped.tif"
        args = ["gdalwarp", "-q", "-overwrite", "-t_srs", "EPSG:4326", "-r", "bilinear"]
        if needs_points:
            args += ["-order", "1"]
        args += [str(working), str(warped)]
        _run(args)
        warped_info = _raster_info(warped)
        warped_size = warped_info.get("size") or size
        preview = _preview(warped, folder, [int(warped_size[0]), int(warped_size[1])])
        stats = {"format": ext.lstrip("."), "features": 0, "warnings": [], "source_crs": source_crs or
                 ("embedded" if (info.get("coordinateSystem") or {}).get("wkt") else "ground control points"),
                 "width": int(size[0]), "height": int(size[1]), "bounds": _bounds(warped_info)}
        result = {"kind": "raster", "preview_base64": base64.b64encode(original_preview).decode("ascii"),
                "width": int(size[0]), "height": int(size[1]), "requires_control_points": False,
                "embedded_georeference": bool(info.get("geoTransform") or (info.get("gcps") or {}).get("gcpList")),
                "detected_crs": (info.get("coordinateSystem") or {}).get("wkt"),
                "georeference": fit, "georeference_mode": mode, "import": stats,
                "alignment_preview_base64": base64.b64encode(preview).decode("ascii") if dry_run else None}
        if not dry_run:
            result["warped_geotiff"] = warped.read_bytes()
            result["preview_png"] = preview
        return result


def ingest(filename: str, raw: bytes, source_crs: Optional[str] = None, mode: str = "auto",
           control_points: Optional[List[Dict[str, Any]]] = None, dry_run: bool = False) -> Dict[str, Any]:
    """Read a portal GIS upload as either normalized vector features or a rectified raster."""
    ext = Path(filename).suffix.lower()
    if ext in {".json", ".geojson", ".kml", ".gpx", ".csv"}:
        collection, stats = gis_import.read(filename, content_base64=base64.b64encode(raw).decode("ascii"))
        return {"kind": "vector", "geojson": collection, "import": stats}
    if mode not in {"auto", "assisted", "manual"}:
        raise gis_import.ImportError_("Georeference mode must be auto, assisted or manual")
    if ext in RASTER_EXTENSIONS:
        if ext in VECTOR_EXTENSIONS and ext == ".pdf":
            try:
                return _vector(filename, raw, source_crs)
            except gis_import.ImportError_:
                pass  # a scanned GeoPDF may have no vector layer; try raster reading next
        return _raster(filename, raw, source_crs, mode, control_points, dry_run)
    if ext in VECTOR_EXTENSIONS or ext == ".zip":
        return _vector(filename, raw, source_crs)
    raise gis_import.ImportError_(f"Unsupported GIS file type: {ext or 'unknown'}")
