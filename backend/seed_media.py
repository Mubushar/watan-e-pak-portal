"""
Real, credited photos for the portal's reference data (``geodata/pk_seed_media.json``, built by
``build_seed_media.py`` from Wikimedia Commons via each record's Wikipedia article).

``apply()`` runs at start-up: a city or housing scheme without images of its own gets its photo,
with author, licence and file page kept in ``multimedia`` so every page can credit it. Images an
admin has added are never replaced. Mega projects read the same file in ``megaprojects.py``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

DATA = Path(__file__).with_name("geodata") / "pk_seed_media.json"


@lru_cache(maxsize=1)
def load() -> Dict[str, Any]:
    if not DATA.exists():
        return {}
    with DATA.open(encoding="utf-8") as fh:
        return json.load(fh)


def credit(kind: str, key: str) -> Optional[Dict[str, Any]]:
    return (load().get(kind) or {}).get(key)


def _attach(record: Any, media: Dict[str, Any]) -> bool:
    if record.image_urls and not any(u == media["url"] for u in record.image_urls):
        return False  # the record has its own images
    record.image_urls = [media["url"]]
    record.multimedia = {**(record.multimedia or {}), "photo_credit": {
        "author": media.get("author"), "license": media.get("license"), "license_url": media.get("license_url"),
        "file_page": media.get("file_page"), "article": media.get("article"), "source": "Wikimedia Commons",
        "text": media.get("credit")}}
    return True


def apply() -> Dict[str, int]:
    import server as core  # late: server imports this module

    data = load()
    done = {"cities": 0, "schemes": 0}
    for c in core.cities_db:
        m = (data.get("cities") or {}).get(c.name)
        if m and _attach(c, m):
            done["cities"] += 1
    for s in core.housing_schemes_db:
        m = (data.get("schemes") or {}).get(s.name)
        if m and _attach(s, m):
            done["schemes"] += 1
    return done
