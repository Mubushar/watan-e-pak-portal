"""
Find real, credited photos for the portal's reference data (cities, housing schemes and
infrastructure mega projects) and write ``geodata/pk_seed_media.json``.

Source: the lead image of each record's English Wikipedia article, served from Wikimedia
Commons at 1280 px, with its author, licence and file page. An article is accepted only when its
coordinates lie near the record (so "Gulberg" in another city can't slip in); records with no
matching article keep no image rather than a made-up one.

    uv run python build_seed_media.py            # all
    uv run python build_seed_media.py cities     # one kind

Run it again after adding cities / schemes; ``seed_media.apply()`` attaches the result at start.
"""

from __future__ import annotations

import html
import json
import math
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

OUT = Path(__file__).with_name("geodata") / "pk_seed_media.json"
API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "ArzePakPortal/1.0 (https://github.com/Mubushar/arzepak-portal) build_seed_media.py httpx"}
THUMB = 1280
# Images that are maps, flags, seals or logos rather than a picture of the place.
NOT_A_PHOTO = re.compile(r"(map|locator|location|flag|seal|logo|emblem|coat_of_arms|\.svg$|district_|tehsil)", re.I)


def _km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    dlat = math.radians(b[0] - a[0])
    dlon = math.radians(b[1] - a[1])
    h = math.sin(dlat / 2) ** 2 + math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _get(client: httpx.Client, **params: Any) -> Dict[str, Any]:
    params.update(format="json", formatversion=2)
    for attempt in range(4):
        time.sleep(1.0)  # polite pacing (Wikimedia API etiquette)
        r = client.get(API, params=params)
        if r.status_code == 429:
            time.sleep(10 + attempt * 10)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return {}


def _pages(client: httpx.Client, titles: List[str]) -> Dict[str, Dict[str, Any]]:
    """title -> page (following redirects) with thumbnail, page image file and coordinates."""
    out: Dict[str, Dict[str, Any]] = {}
    for i in range(0, len(titles), 40):
        chunk = titles[i:i + 40]
        data = _get(client, action="query", titles="|".join(chunk), redirects=1, prop="pageimages|coordinates|info",
                    piprop="thumbnail|name", pithumbsize=THUMB, pilimit="max", colimit="max", inprop="url")
        q = data.get("query", {})
        alias = {t: t for t in chunk}
        for step in q.get("normalized", []) + q.get("redirects", []):
            for k, v in list(alias.items()):
                if v == step["from"]:
                    alias[k] = step["to"]
        by_title = {p["title"]: p for p in q.get("pages", []) if not p.get("missing")}
        for asked, final in alias.items():
            if final in by_title:
                out[asked] = by_title[final]
    return out


def _licences(client: httpx.Client, files: Iterable[str]) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    names = [f"File:{f}" for f in files]
    for i in range(0, len(names), 40):
        data = _get(client, action="query", titles="|".join(names[i:i + 40]), prop="imageinfo",
                    iiprop="extmetadata|url", iiextmetadatafilter="Artist|LicenseShortName|LicenseUrl|ImageDescription")
        for p in data.get("query", {}).get("pages", []):
            info = (p.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata", {})
            text = lambda k: re.sub(r"<[^>]+>", "", html.unescape((meta.get(k) or {}).get("value", ""))).strip()  # noqa: E731
            out[p["title"].removeprefix("File:").replace(" ", "_")] = {
                "author": text("Artist")[:120], "license": text("LicenseShortName"), "license_url": text("LicenseUrl"),
                "file_page": info.get("descriptionurl", ""), "description": text("ImageDescription")[:200],
            }
    return out


def _search_title(client: httpx.Client, query: str) -> Optional[str]:
    data = _get(client, action="query", list="search", srsearch=query, srlimit=1, srnamespace=0)
    hits = data.get("query", {}).get("search", [])
    return hits[0]["title"] if hits else None


def _key_words(name: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", name.lower()) if len(w) > 2 and w not in {"the", "and", "phase", "new", "pakistan"}}


def find(client: httpx.Client, records: List[Dict[str, Any]], max_km: float) -> Dict[str, Dict[str, Any]]:
    """records: {key, titles: [candidate article titles], lat, lon}. Returns key -> image."""
    titles = sorted({t for r in records for t in r["titles"]})
    pages = _pages(client, titles)
    # No article under the record's own names: ask Wikipedia's search, and keep the result only if
    # its title shares the record's key words (coordinates are still checked below when required).
    missing = [r for r in records if not any(t in pages and pages[t].get("pageimage") for t in r["titles"])]
    extra: List[str] = []
    for r in missing:
        t = _search_title(client, f"{r['titles'][0]} Pakistan")
        if t and len(_key_words(t) & _key_words(r["titles"][0])) >= max(1, min(2, len(_key_words(t)))):
            r["titles"] = r["titles"] + [t]
            extra.append(t)
    if extra:
        pages.update(_pages(client, sorted(set(extra))))
    chosen: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]] = {}
    for r in records:
        for t in r["titles"]:
            p = pages.get(t)
            if not p or not p.get("thumbnail") or not p.get("pageimage") or NOT_A_PHOTO.search(p["pageimage"]):
                continue
            coords = (p.get("coordinates") or [{}])[0]
            if r.get("lat") is not None and coords.get("lat") is not None:
                if _km((r["lat"], r["lon"]), (coords["lat"], coords["lon"])) > max_km:
                    continue
            elif r.get("require_coords", True):
                continue
            chosen[r["key"]] = (p, coords)
            break
    lic = _licences(client, {p["pageimage"] for p, _ in chosen.values()})
    out = {}
    for key, (p, _) in chosen.items():
        l = lic.get(p["pageimage"], {})
        if not l.get("license"):
            continue  # unknown licence: don't use it
        out[key] = {"url": p["thumbnail"]["source"].split("?")[0].replace("//thumb.wikimedia.org/", "//upload.wikimedia.org/"), "width": p["thumbnail"].get("width"), "height": p["thumbnail"].get("height"),
                    "article": p.get("fullurl"), "article_title": p["title"], "file": p["pageimage"], **l,
                    "credit": f"{l.get('author') or 'Wikimedia Commons contributor'} · {l.get('license')} · Wikimedia Commons"}
    return out


def _records() -> Dict[str, List[Dict[str, Any]]]:
    import os

    os.environ.setdefault("PORTAL_PERSIST", "0")
    import api  # noqa: F401  (loads base data)
    import megaprojects
    import server as core

    city = {c.id: c for c in core.cities_db}
    cities = [{"key": c.name, "lat": c.latitude, "lon": c.longitude,
               "titles": [c.name, f"{c.name}, Pakistan", f"{c.name}, {c.state}" if c.state else c.name]} for c in core.cities_db]
    schemes = []
    for s in core.housing_schemes_db:
        cname = city[s.city_id].name if s.city_id in city else ""
        base = re.sub(r"\s*\(.*?\)\s*", " ", s.name).strip()
        titles = [s.name, base, f"{base}, {cname}" if cname else base, f"{base} {cname}".strip()]
        schemes.append({"key": s.name, "lat": s.latitude, "lon": s.longitude, "titles": list(dict.fromkeys(titles))})
    megas = []
    for m in megaprojects.all_projects():
        if m.get("portal_project"):
            continue  # projects with their own official images
        g = m.get("geometry") or {}
        pt = g.get("center") or ((g.get("path") or g.get("ring") or [[None, None]])[0])
        base = re.sub(r"\s*\(.*?\)\s*", " ", m["name"]).split(" — ")[0].strip()
        # named infrastructure (motorways, ring roads, airports) is unambiguous; many articles have no single point
        megas.append({"key": m["id"], "lat": pt[0], "lon": pt[1], "require_coords": False,
                      "titles": list(dict.fromkeys([m["name"], base, base.replace("–", "-")]))})
    return {"cities": cities, "schemes": schemes, "megaprojects": megas}


def main(kinds: List[str]) -> None:
    current = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    records = _records()
    radius = {"cities": 40.0, "schemes": 12.0, "megaprojects": 60.0}
    with httpx.Client(headers=HEADERS, timeout=30) as client:
        for kind in kinds:
            found = find(client, records[kind], radius[kind])
            current[kind] = found
            print(f"{kind}: {len(found)} of {len(records[kind])} with a credited photo")
    current["note"] = ("Lead images of the matching English Wikipedia articles, from Wikimedia Commons, with author and "
                       "licence. Built by build_seed_media.py; records without a matching article have no image.")
    current["built"] = time.strftime("%Y-%m-%d")
    OUT.write_text(json.dumps(current, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:] or ["cities", "schemes", "megaprojects"])
