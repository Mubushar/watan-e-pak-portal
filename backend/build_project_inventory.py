"""Build backend/geodata/pk_project_inventory.json from the three project websites' inventories
(scraped 2026-10-19: chinacenterpk.com, skyratower.com, goldcrest-breeze.com)."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).with_name("geodata") / "project_sources"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("geodata") / "pk_project_inventory.json"
CHECKED = "2026-10-19"

# ------------------------------------------------------------------ China Center
cc_rows = json.load(open(HERE / "chinacenter.json"))
CC_FLOOR = {"lower-ground": (-1, "Lower ground"), "ground": (0, "Ground floor"), "first": (1, "1st floor"),
            "second": (2, "2nd floor"), "food-court": (8, "Food court (floor to be confirmed)"),
            "seventh-apartments": (7, "7th floor")}
cc_units = []
for r in cc_rows:
    if r["status"] != "available":
        continue
    floor, floor_label = CC_FLOOR[r["section"]]
    kind = {"shop": "shop", "food-court": "food_court", "apartment": "apartment"}[r["category"]]
    cc_units.append({
        "unit": r["unit"], "floor": floor, "floor_label": floor_label, "kind": kind, "layout": None, "bedrooms": None,
        "sqft": r["sqft"], "rate_per_sqft": r["rate"], "price": r["total"],
        "payment": {"down": r["down"], "instalment": r["instalment"], "instalments": r["instalments"],
                    "cadence": "monthly", "on_possession": r["possession"]},
    })

china = {
    "id": "china-center-bahria-phase-8",
    "name": "China Center",
    "tagline": "Chinese-themed shopping centre with apartments above",
    "developer": "Creation Developers (Pvt) Ltd",
    "project_type": "mixed_use",
    "status": "under_construction",
    "city": "Rawalpindi",
    "scheme": "Bahria Town Phase 8",
    "address": "Plot 563, Central Business District, Bahria Town Phase VIII, Rawalpindi / Islamabad",
    "location": {"lat": 33.5013, "lon": 73.0838, "precision": "approximate",
                 "note": "Placed at the Bahria Town Phase 8 Business District (OpenStreetMap); the website gives the plot, not coordinates."},
    "floors": "Lower ground + ground + 8",
    "floor_count": 10,
    "description": ("A Chinese-themed shopping centre in the Central Business District of Bahria Town Phase VIII: "
                    "shops on the lower floors (lower ground to 2nd), apartments on the 7th floor and a food court "
                    "with terrace dining under the pavilion roof on the 8th."),
    "payment_plan": {"summary": "30% down · 24 monthly instalments of 2.5% · 10% on possession",
                     "down_pct": 30, "instalments": 24, "instalment_pct": 2.5, "cadence": "monthly", "on_possession_pct": 10,
                     "payee": "Creation Developers (Pvt) Ltd"},
    "offer": None,
    "rates": {"shop": 40000, "food_court": 40000, "apartment": 15000},
    "inventory_source": "Developer's inventory sheet (CC-inventory.pdf, undated; Excel export 2026-01-24) as published on chinacenterpk.com",
    "units": cc_units,
    "sources": [{"title": "China Center — official project website", "url": "https://chinacenterpk.com/"}],
}

# ------------------------------------------------------------------ Skyra Tower
SK_RATE = {"shop": 60000, "clinic": 25000, "apartment": 15000, "penthouse": 17000}
SK_LAYOUT = [(1, "A", 1050), (2, "B", 600), (3, "B", 600), (4, "B", 600), (5, "B", 600), (6, "B", 600), (7, "B", 600),
             (8, "B", 600), (9, "C", 1075), (10, "D", 1225), (11, "E", 560), (12, "E", 560), (13, "F", 440),
             (14, "G", 1150), (15, "E", 560)]
SK_BEDS = {"A": 2, "B": 1, "C": 2, "D": 2, "E": 1, "F": 0, "G": 2, "PH1": 4, "PH2": 4, "PH3": 4}
SK_CLINIC = [435, 435, 435, 435, 435, 540, 580, 580, 580, 580, 830, 810, 550, 550, 480, 410, 530, 400, 380]
SK_SHOPS = [("G-01", 1123), ("G-02", 800), ("G-03", 800), ("G-04", 800), ("G-05", 757), ("G-06", 560), ("G-07", 885),
            ("G-08", 858), ("G-09", 676)]
SK_AVAILABLE = {"G-09", "106", "209", "210", "213", "214", "217", "501", "502", "503", "504", "505", "506", "507", "508",
                "509", "510", "511", "512", "513", "514", "515", "601", "605", "609", "610", "611", "612", "613", "614",
                "615", "801", "802", "803"}
ORD = {0: "Ground floor", 1: "1st floor", 2: "2nd floor", 3: "3rd floor", 4: "4th floor", 5: "5th floor", 6: "6th floor",
       7: "7th floor", 8: "8th & 9th floor (duplex)"}
sk_all = [(u, 0, "shop", None, s) for u, s in SK_SHOPS]
sk_all += [(f"{f}{i + 1:02d}", f, "clinic", None, s) for f in (1, 2) for i, s in enumerate(SK_CLINIC)]
sk_all += [(f"{f}{n:02d}", f, "apartment", lay, s) for f in (3, 4, 5, 6, 7) for n, lay, s in SK_LAYOUT]
sk_all += [("801", 8, "penthouse", "PH1", 5300), ("802", 8, "penthouse", "PH2", 5090), ("803", 8, "penthouse", "PH3", 4290)]
sk_units = []
for unit, floor, kind, layout, sqft in sk_all:
    if unit not in SK_AVAILABLE:
        continue
    price = sqft * SK_RATE[kind]
    sk_units.append({
        "unit": unit, "floor": floor, "floor_label": ORD[floor], "kind": kind, "layout": layout,
        "bedrooms": SK_BEDS.get(layout) if layout else None, "sqft": sqft, "rate_per_sqft": SK_RATE[kind], "price": price,
        "payment": {"down": round(price * 0.30), "instalment": round(price * 0.65 / 36), "instalments": 36,
                    "cadence": "monthly", "on_possession": round(price * 0.05)},
    })

skyra = {
    "id": "skyra-tower-bahria-phase-8",
    "name": "Skyra Tower",
    "tagline": "Studios, 1–2 bed apartments and duplex penthouses with private pools",
    "developer": "Creation Developers (Pvt) Ltd",
    "project_type": "tower",
    "status": "under_construction",
    "city": "Rawalpindi",
    "scheme": "Bahria Town Phase 8",
    "address": "Business District, Bahria Town Phase 8, Rawalpindi",
    "location": {"lat": 33.5009, "lon": 73.0847, "precision": "approximate",
                 "note": "Placed at the Bahria Town Phase 8 Business District (OpenStreetMap); the website gives the district, not coordinates."},
    "floors": "Lower ground + ground + 9",
    "floor_count": 11,
    "total_units": 75 + 3 + 9 + 38,
    "description": ("A G+9 residential tower in the Business District of Bahria Town Phase 8: a residents' clubhouse "
                    "(gym, snooker, day care) on the lower ground, 9 double-height showrooms at street level, clinics "
                    "and offices on the 1st and 2nd floors, 75 apartments (studio, 1 and 2 bed) on the 3rd–7th floors "
                    "and three 4-bed duplex penthouses with private infinity pools on the 8th–9th."),
    "payment_plan": {"summary": "30% down · 65% over 36 monthly instalments · 5% on possession",
                     "down_pct": 30, "instalments": 36, "instalment_pct": round(65 / 36, 3), "cadence": "monthly",
                     "on_possession_pct": 5},
    "offer": "15% off on full payment (per the website)",
    "rates": SK_RATE,
    "inventory_source": "Developer's updated inventory (undated) as published on skyratower.com",
    "units": sk_units,
    "sources": [{"title": "Skyra Tower — official project website", "url": "https://skyratower.com/"}],
}

# ------------------------------------------------------------------ Goldcrest Breeze Overseas
gb_rows = json.load(open(HERE / "goldcrest.json"))
FACING = {0: "Community facing", 1: "Margalla facing", 2: "Dual-aspect corner"}
GB_LAYOUT_BEDS = lambda code, beds: beds  # noqa: E731


def gb_floor_label(f: int) -> str:
    return "Ground floor" if f == 0 else f"Level {f}"


gb_units = []
for row in gb_rows:
    unit, code, floor, beds, sqft, band, price = row[:7]
    dual = len(row) > 7 and bool(row[7])
    pool = code.startswith("TP")
    facing = "Pool apartment" if pool else ("Dual-aspect corner" if dual or band == 2 else FACING.get(band, "Community facing"))
    kind = "studio" if beds == 0 else "pool_apartment" if pool else "apartment"
    total = int(price)
    gb_units.append({
        "unit": unit, "floor": floor, "floor_label": gb_floor_label(floor), "kind": kind, "layout": code,
        "bedrooms": beds, "sqft": round(sqft, 2), "rate_per_sqft": round(total / sqft), "price": total, "facing": facing,
        "payment": {"down": round(total * 0.25), "instalment": round(total * 0.60 / 12), "instalments": 12,
                    "cadence": "quarterly", "on_possession": round(total * 0.15)},
    })

goldcrest = {
    "id": "goldcrest-breeze-overseas",
    "name": "Goldcrest Breeze Overseas",
    "tagline": "Studio to 3-bed residences, some with private terrace pools",
    "developer": "Giga Group",
    "marketed_by": "Al Faisal Properties",
    "project_type": "tower",
    "status": "under_construction",
    "city": "Islamabad",
    "scheme": "DHA Phase II",
    "address": "Downtown Giga, DHA Phase II, Islamabad (G.T. Road frontage)",
    "location": {"lat": 33.5252612, "lon": 73.1493105, "precision": "exact",
                 "note": "Coordinates published on goldcrest-breeze.com."},
    "floors": "Ground + 28 (6 parking levels; amenities floor at level 26)",
    "floor_count": 29,
    "description": ("The final chapter of the Goldcrest Views community at Downtown Giga, DHA Phase II: a curved tower "
                    "with one face towards the Margalla Hills and the other over G.T. Road, studios to three-bedroom "
                    "residences (some with a private terrace pool), about 8.5 kanal of amenities on the 26th floor and a "
                    "rooftop panoramic pool. By Giga Group (Goldcrest Views I & II delivered)."),
    "payment_plan": {"summary": "25% down · 60% over 12 quarterly instalments · 15% on possession",
                     "down_pct": 25, "instalments": 12, "instalment_pct": 5, "cadence": "quarterly", "on_possession_pct": 15,
                     "alternative": "30% down as 10% upfront, 10% in the 3rd month and 10% in the 6th month"},
    "offer": "Launch offer on the website: 25% discount until 31 Oct 2026 (confirm at booking)",
    "rates": {"Community facing": 19900, "Margalla facing": 21900, "G.T. Road facing": 19900,
              "Dual-aspect corner": 23900, "Pool apartment": 23900},
    "inventory_source": "Available-unit inventory as published on goldcrest-breeze.com",
    "units": gb_units,
    "sources": [{"title": "Goldcrest Breeze Overseas — official project website", "url": "https://goldcrest-breeze.com/"}],
}

# ------------------------------------------------------------------ real images from each official site
CC = "https://chinacenterpk.com/media/"
china["images"] = [
    {"url": CC + "photos/exterior-golden-live.webp", "caption": "China Center from the corner of the boulevard at golden hour"},
    {"url": CC + "photos/exterior-dusk-live.webp", "caption": "The pagoda roofline and lanterns at blue hour"},
    {"url": CC + "photos/aerial-evening-live.webp", "caption": "From above, evening"},
    {"url": CC + "photos/atrium-v2-live.webp", "caption": "Ground-floor atrium with the glass capsule lift"},
    {"url": CC + "photos/rooftop-terrace-live.webp", "caption": "Rooftop dining terrace"},
    {"url": CC + "photos/food-court-hall-live.webp", "caption": "Food court hall"},
    {"url": CC + "photos/apartment-living-live.webp", "caption": "Apartment living room"},
    {"url": CC + "renders/apartment-bedroom.webp", "caption": "Developer's render of an apartment bedroom"},
    {"url": CC + "video/progress-marble-floor.webp", "caption": "Construction progress: marble flooring laid on site"},
    {"url": CC + "video/progress-corridor.webp", "caption": "Construction progress: corridor on site"},
]
CC_PLAN = {"lower-ground": "floor-lg-r5-sm", "ground": "floor-g-r5-sm", "first": "floor-1-r5-sm", "second": "floor-2-r5-sm",
           "food-court": "foodcourt-8-r5-sm", "seventh-apartments": "floor-7-serviced-r5-sm"}
china["floor_plans"] = [{"url": f"{CC}plans/{v}.webp", "caption": k.replace("-", " ").title()} for k, v in CC_PLAN.items()]
SECTION_OF = {r["unit"]: r["section"] for r in cc_rows}
for u in china["units"]:
    u["plan"] = f"{CC}plans/{CC_PLAN[SECTION_OF[u['unit']]]}.webp"

SK = "https://skyratower.com/media/"
skyra["images"] = [
    {"url": SK + "live/hero-desk.webp", "caption": "Skyra Tower at sunset (artist's impression)"},
    {"url": SK + "live/aerial-top.webp", "caption": "From above: the penthouse terraces and pools"},
    {"url": SK + "live/reception.webp", "caption": "Grand reception"},
    {"url": SK + "live/apt-lounge.webp", "caption": "Apartment lounge"},
    {"url": SK + "live/apt-bedroom.webp", "caption": "Apartment bedroom"},
    {"url": SK + "live/apt-kitchen.webp", "caption": "Apartment kitchen"},
    {"url": SK + "live/ph-staircase.webp", "caption": "Duplex penthouse interior"},
    {"url": SK + "amenities/clubhouse-live.webp", "caption": "Residents' clubhouse lounge (artist's impression)"},
    {"url": SK + "live/clinic-reception.webp", "caption": "Clinics and offices"},
    {"url": SK + "live/street.webp", "caption": "Ground-floor showrooms"},
    {"url": SK + "site/location-map.webp", "caption": "Location in the Business District, Bahria Town Phase 8"},
]
skyra["floor_plans"] = [{"url": SK + "plans/floor-lg.webp", "caption": "Lower-ground clubhouse"},
                        {"url": SK + "plans/floor-g.webp", "caption": "Ground floor showrooms"},
                        {"url": SK + "plans/floor-1.webp", "caption": "Clinics and offices"},
                        {"url": SK + "plans/floor-3-7.webp", "caption": "Typical apartment floor (3rd–7th)"}] + [
    {"url": f"{SK}plans/type-{t.lower()}.webp", "caption": f"Apartment type {t}"} for t in "ABCDEFG"] + [
    {"url": f"{SK}plans/penthouse-{n}.webp", "caption": f"Duplex penthouse 0{n}"} for n in (1, 2, 3)]
for u in skyra["units"]:
    lay = u.get("layout")
    u["plan"] = (f"{SK}plans/type-{lay.lower()}.webp" if lay and lay[0] in "ABCDEFG" and len(lay) == 1 else
                 f"{SK}plans/penthouse-{lay[-1]}.webp" if lay and lay.startswith("PH") else
                 f"{SK}plans/floor-g.webp" if u["kind"] == "shop" else f"{SK}plans/floor-1.webp")

GB = "https://goldcrest-breeze.com/media/"
goldcrest["images"] = [
    {"url": GB + "site/hero-night.webp", "caption": "Goldcrest Breeze Overseas at dusk, Downtown Giga"},
    {"url": GB + "lifestyle/tower-day.webp", "caption": "The tower by day"},
    {"url": GB + "lifestyle/tower-dusk.webp", "caption": "The tower at dusk"},
    {"url": GB + "amenities/infinity-pool-premium.jpg", "caption": "Rooftop infinity pool (lifestyle visualisation)"},
    {"url": GB + "amenities/rooftop-lounge-premium.jpg", "caption": "Rooftop lounge (lifestyle visualisation)"},
    {"url": GB + "amenities/social-deck-premium.jpg", "caption": "Open-air social deck (lifestyle visualisation)"},
    {"url": GB + "orientation/outlook-margalla-cloudy-wide-v5.webp", "caption": "Margalla-facing outlook (conceptual)"},
    {"url": GB + "video/giga-city-film-poster.jpg", "caption": "Giga City, Islamabad"},
]
GB_PLANS = {"s1", "s1a", "1b1", "1b2", "1b3", "2b1", "2b1a", "2b1b", "2b2", "2b3", "2b4", "2b5", "3b1", "3b3", "tp"}
goldcrest["floor_plans"] = [{"url": f"{GB}units/{s}/plan.webp", "caption": f"Type {s.upper()}"} for s in sorted(GB_PLANS)]
for u in goldcrest["units"]:
    slug = "tp" if u["layout"].startswith("TP") else u["layout"].lower()
    u["plan"] = f"{GB}units/{slug}/plan.webp" if slug in GB_PLANS else None

data = {
    "note": ("New high-rise and mixed-use projects with their live unit inventories, from each project's official "
             "website. Prices, availability and plans change: the portal shows the date they were checked and every "
             "listing says to confirm at booking."),
    "checked": CHECKED,
    "projects": [china, skyra, goldcrest],
}

# ------------------------------------------------------------------ landmark malls and towers
# Completed or selling landmarks without a public unit inventory (researched 2026-10-19 from the
# developers' sites, Wikipedia and OpenStreetMap); photos are credited, Wikimedia Commons first.
LANDMARKS = HERE / "landmarks.json"
if LANDMARKS.exists():
    for r in json.loads(LANDMARKS.read_text(encoding="utf-8")):
        r.setdefault("units", [])
        r["images"] = [{"url": i["url"], "caption": i.get("credit") or ""} for i in r.get("images") or []]
        data["projects"].append(r)
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
for p in data["projects"]:
    prices = [u["price"] for u in p["units"]]
    print(p["name"], len(p["units"]), "available", *((min(prices), max(prices)) if prices else ()))
