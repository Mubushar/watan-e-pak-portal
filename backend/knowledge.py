"""
The assistant's knowledge base: fast BM25 retrieval over everything the portal knows, with
numbered citations and a trust tier for every source.

Corpus (rebuilt automatically when the data changes): listings, cities, housing schemes (with
their approval status and sources), commercial / big projects, infrastructure mega projects,
news, the portal's guide pages and construction guidelines.

Queries are understood the way people in Pakistan ask: "5 marla house in Bahria under 2 crore",
"1 kanal plot DHA 3.5 cr", "2 bed flat kiraya Islamabad", Urdu script ("اسلام آباد میں گھر")
and Roman Urdu ("ghar", "makan", "kiraya"). Prices in crore / lakh / million / arab, sizes in
marla / kanal / sq ft / sq yd and bedrooms become hard filters on listings.

``search()`` returns ranked hits plus a ``context`` block with [1], [2] … markers that the model
quotes back, so every fact in an answer can be traced to its source.
"""

from __future__ import annotations

import math
import re
import threading
import time
import unicodedata
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

import sources

# ---------------------------------------------------------------- text

_URDU_FOLD = str.maketrans({
    "ي": "ی", "ى": "ی", "ك": "ک", "ة": "ہ", "ۀ": "ہ", "ھ": "ہ", "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ؤ": "و", "ئ": "ی", "ے": "ی", "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4", "۵": "5", "۶": "6",
    "۷": "7", "۸": "8", "۹": "9", "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4", "٥": "5", "٦": "6",
    "٧": "7", "٨": "8", "٩": "9", "،": ",", "٫": ".",
})
_DIACRITICS = re.compile("[ً-ٰٟۖ-ۭ]")

# Urdu / Roman Urdu words -> the English term the data uses.
SYNONYMS = {
    "گہر": "house", "گھر": "house", "مکان": "house", "ghar": "house", "makan": "house", "makaan": "house",
    "home": "house", "homes": "house", "houses": "house", "bungalow": "house", "villa": "house",
    "پلاٹ": "plot", "plots": "plot", "zameen": "plot", "زمین": "plot",
    "فلیٹ": "apartment", "flat": "apartment", "flats": "apartment", "apartments": "apartment",
    "اپارٹمنٹ": "apartment", "دکان": "shop", "dukan": "shop", "shops": "shop", "دفتر": "office",
    "daftar": "office", "offices": "office", "کرایہ": "rent", "کرای": "rent", "kiraya": "rent",
    "kiraye": "rent", "rental": "rent", "lease": "rent", "فروخت": "sale", "خرید": "buy", "kharid": "buy",
    "kharidna": "buy", "bechna": "sale", "selling": "sale", "مرلہ": "marla", "مرلی": "marla", "marlas": "marla",
    "کنال": "kanal", "kanals": "kanal", "کروڑ": "crore", "karor": "crore", "karore": "crore", "cr": "crore",
    "لاکھ": "lakh", "lac": "lakh", "lacs": "lakh", "lakhs": "lakh", "ارب": "arab", "اسلام": "islamabad",
    "لاہور": "lahore", "لاہور": "lahore", "کراچی": "karachi", "راولپنڈی": "rawalpindi", "پنڈی": "rawalpindi",
    "pindi": "rawalpindi", "isb": "islamabad", "lhr": "lahore", "khi": "karachi", "پشاور": "peshawar",
    "ملتان": "multan", "فیصل": "faisalabad", "بحریہ": "bahria", "ڈی": "dha", "defence": "dha",
    "منظور": "approved", "منظوری": "approval", "غیرقانونی": "illegal", "illegal": "illegal",
    "approved": "approved", "noc": "approval", "سکول": "school", "school": "school", "schools": "school",
    "مسجد": "mosque", "masjid": "mosque", "hospital": "hospital", "ہسپتال": "hospital",
    "کمرے": "bedroom", "کمرہ": "bedroom", "kamre": "bedroom", "kamra": "bedroom", "bedrooms": "bedroom",
    "beds": "bedroom", "bed": "bedroom", "bhk": "bedroom", "br": "bedroom",
    "motorway": "motorway", "موٹروے": "motorway", "ring": "ring", "road": "road", "roads": "road",
}
STOPWORDS = set("""
a an the of in on at to for from by with and or is are was were be been it its this that these those
i me my we our you your he she they them his her their what which who whom how when where why do does
did can could would should will shall may might must have has had any some all no not only more most
very just also please tell show give find get want need looking look like about near around within
there here than then into over under below above upto up as if so per sq
ka ki ke ko se mein me main hai hain tha thi kya kaun kahan kitna kitne chahiye chahye wala wali wale
aur ya bhi par pe liye mujhe hum ap aap koi kuch batao bataen dikhao
کا کی کے کو سے میں ہے ہیں تھا تھی کیا کون کہاں کتنا کتنے چاہیے والا والی والے اور یا بھی پر لیے مجھے ہم آپ کوئی کچھ بتائیں دکھائیں
""".split())


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or "")).translate(_URDU_FOLD)
    return _DIACRITICS.sub("", text).lower()


# The tables above are written in everyday spelling; match them in folded form.
SYNONYMS = {normalize(k): v for k, v in SYNONYMS.items()}

STOPWORDS = {normalize(w) for w in STOPWORDS}


# Place names written as two words in Urdu script.
PHRASES = {"اسلام آباد": " islamabad ", "فیصل آباد": " faisalabad ", "ایبٹ آباد": " abbottabad ", "حیدر آباد": " hyderabad ",
           "ڈی ایچ اے": " dha ", "بحریہ ٹاؤن": " bahria town ", "رنگ روڈ": " ring road ", "گوجر خان": " gujar khan "}

_FOLDED_PHRASES = {normalize(k): v for k, v in PHRASES.items()}


_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12}
_NUMBERED = re.compile(r"\b(phase|sector|block|zone|loop|step|precinct)\s*[-#]?\s*(\d{1,2}|[ivx]{1,4})\b")


def _numbered(m: "re.Match[str]") -> str:
    n = m.group(2)
    return f" {m.group(1)}{_ROMAN.get(n, n)} "  # "Phase II", "phase 2", "phase-2" -> "phase2"


def _phrases(text: str) -> str:
    for k, v in _FOLDED_PHRASES.items():
        if k in text:
            text = text.replace(k, v)
    return _NUMBERED.sub(_numbered, text)


_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?|[؀-ۿ]+")


def tokens(text: str, keep_stopwords: bool = False) -> List[str]:
    out = []
    for t in _TOKEN.findall(_phrases(normalize(text))):
        t = SYNONYMS.get(t, t)
        if not keep_stopwords and (t in STOPWORDS or len(t) < 2 and not t.isdigit()):
            continue
        if len(t) > 4 and t.endswith("s") and t.isascii() and not t.endswith("ss"):
            t = t[:-1]
        out.append(t)
    return out


# ---------------------------------------------------------------- query understanding

_UNITS = {"crore": 1e7, "arab": 1e9, "lakh": 1e5, "million": 1e6, "mn": 1e6, "m": 1e6, "billion": 1e9,
          "thousand": 1e3, "hazar": 1e3, "ہزار": 1e3, "k": 1e3}
_AMOUNT = re.compile(normalize(r"(\d+(?:[.,]\d+)*)\s*(crore|cr|karor|karore|کروڑ|arab|ارب|lakh|lakhs|lac|lacs|لاکھ|million|mn|m|billion|thousand|hazar|ہزار|k)?\b"))
_MAX_WORDS = ("under", "below", "less than", "max", "maximum", "upto", "up to", "within", "budget", "tak", "se kam",
              "سے کم", "تک", "کے اندر", "not more than", "no more than")
_MIN_WORDS = ("above", "over", "more than", "min", "minimum", "at least", "starting", "from", "se zyada", "سے زیادہ")
_SIZE = re.compile(normalize(r"(\d+(?:\.\d+)?)\s*(marla|مرلہ|kanal|کنال|sq\s*ft|sqft|square\s*feet|sq\s*yd|sq\s*yards?|square\s*yards?|yards|گز)"))
_BEDS = re.compile(normalize(r"(\d+)\s*(?:bed|beds|bedroom|bedrooms|br|bhk|kamre|kamra|کمرے|بیڈ)\b"))
CATEGORY_WORDS = {"house": "house", "plot": "plot", "apartment": "apartment", "shop": "shop", "office": "office",
                  "building": "building", "floor": "floor", "penthouse": "apartment", "farmhouse": "house"}


_MAX_WORDS = tuple(normalize(w) for w in _MAX_WORDS)
_MIN_WORDS = tuple(normalize(w) for w in _MIN_WORDS)
_UNITS = {normalize(k): v for k, v in _UNITS.items()}


def _amount(num: str, unit: Optional[str]) -> Optional[float]:
    try:
        value = float(num.replace(",", "")) if num.count(",") != 1 or len(num.split(",")[1]) == 3 else float(num.replace(",", "."))
    except ValueError:
        return None
    unit = SYNONYMS.get(unit or "", unit or "")
    if unit in _UNITS:
        return value * _UNITS[unit]
    return value if value >= 100_000 else None  # a bare number is a price only when it looks like one


def parse_query(query: str) -> Dict[str, Any]:
    """Pull structured filters out of a free-text question."""
    q = normalize(query)
    out: Dict[str, Any] = {}
    sizes = [(m.start(), m.end()) for m in _SIZE.finditer(q)] + [(m.start(), m.end()) for m in _BEDS.finditer(q)]
    amounts: List[Tuple[int, float]] = []
    for m in _AMOUNT.finditer(q):
        if any(a <= m.start() < b for a, b in sizes):
            continue
        value = _amount(m.group(1), m.group(2))
        if value:
            amounts.append((m.start(), value))
    between = re.search(r"(?:between|from)\s+(.+?)\s+(?:and|to|-)\s+(.+)", q)
    if len(amounts) >= 2 and (between or re.search(r"\d\s*(?:-|to|se)\s*\d", q)):
        lo, hi = sorted(v for _, v in amounts[:2])
        out["min_price"], out["max_price"] = lo, hi
    elif amounts:
        pos, value = amounts[0]
        before = q[max(0, pos - 20):pos]
        after = q[pos:pos + 30]
        if any(w in before for w in _MIN_WORDS) or normalize("سے زیادہ") in after or "se zyada" in after:
            out["min_price"] = value
        elif any(w in before for w in _MAX_WORDS) or any(normalize(w) in after for w in ("سے کم", "تک", "tak", "se kam")):
            out["max_price"] = value
        else:  # "house 2 crore": a budget around that figure
            out["max_price"] = round(value * 1.15)
            out["budget"] = value
    m = _SIZE.search(q)
    if m:
        n, unit = float(m.group(1)), m.group(2)
        marla = n * 20 if unit in ("kanal", normalize("کنال")) else n / 225 if "ft" in unit or "feet" in unit else n * 9 / 225 if any(
            u in unit for u in ("yd", "yard", normalize("گز"))) else n
        out["marla"] = round(marla, 2)
    m = _BEDS.search(q)
    if m:
        out["bedrooms"] = int(m.group(1))
    words = set(tokens(query, keep_stopwords=True))
    for w, cat in CATEGORY_WORDS.items():
        if w in words:
            out["category"] = cat
            break
    if "rent" in words:
        out["purpose"] = "rent"
    elif words & {"sale", "buy"}:
        out["purpose"] = "sale"
    if words & {"commercial", "shop", "office", "plaza"}:
        out["use_type"] = "commercial"
    elif words & {"residential", "house", "apartment"}:
        out["use_type"] = "residential"
    return out


# ---------------------------------------------------------------- corpus


def _core() -> Any:
    import server  # late: server imports this module

    return server


def _join(*parts: Any) -> str:
    return " ".join(str(p) for p in parts if p not in (None, "", [], {}))


def _price_words(price: Optional[float]) -> str:
    if not price:
        return ""
    return f"{price / 1e7:.2f} crore" if price >= 1e7 else f"{price / 1e5:.0f} lakh"


def _docs() -> List[Dict[str, Any]]:
    core = _core()
    docs: List[Dict[str, Any]] = []
    city = {c.id: c for c in core.cities_db}
    scheme = {s.id: s for s in core.housing_schemes_db}

    for c in core.cities_db:
        tier = sources.tier_for_sources(getattr(c, "sources", None) or [])
        docs.append({
            "type": "city", "id": c.id, "title": c.name, "url": f"/cities/{quote(c.name)}", "tier": tier,
            "sources": getattr(c, "sources", None) or [],
            "text": _join(c.name, c.name_ur, c.state, c.district, c.description, c.development_authority,
                          f"population {c.population}" if c.population else "", c.population_note),
            "facts": _join(f"{c.name}, {c.state}." if c.state else f"{c.name}.",
                           f"Population {c.population:,}." if c.population else "",
                           f"Authority: {c.development_authority}." if c.development_authority else "", c.description),
        })
    for s in core.housing_schemes_db:
        tier = sources.tier_for_sources(s.sources or [])
        cname = city[s.city_id].name if s.city_id in city else ""
        docs.append({
            "type": "scheme", "id": s.id, "title": s.name, "url": f"/schemes?scheme={s.id}", "tier": tier,
            "sources": s.sources or [], "city": cname,
            "text": _join(s.name, s.name_ur, cname, s.developer, s.description, s.approval_status, s.approval_note,
                          s.approval_authority, s.possession_status, s.development_status,
                          " ".join(map(str, s.plot_sizes or [])), " ".join(map(str, s.utilities or []))),
            "facts": _join(f"{s.name} ({cname})." if cname else f"{s.name}.",
                           f"Developer: {s.developer.rstrip('.')}." if s.developer else "",
                           f"Approval: {s.approval_status}" + (f" ({s.approval_authority})" if s.approval_authority else "") + "."
                           if s.approval_status else "",
                           s.approval_note, f"Possession: {s.possession_status}." if s.possession_status else "",
                           f"Plot sizes: {', '.join(map(str, s.plot_sizes))}." if s.plot_sizes else "", s.description),
        })
    for p in core.properties_db:
        if getattr(p, "project_id", None):
            continue  # a project's units are summarised by its project entry (unit types, prices, plan)
        cname = city[p.city_id].name if p.city_id in city else ""
        sname = scheme[p.scheme_id].name if p.scheme_id in scheme else ""
        size = f"{p.marla_area:g} marla" if p.marla_area else ""
        docs.append({
            "type": "property", "id": p.id, "title": p.title, "url": f"/properties/{p.id}", "tier": "listing",
            "city": cname, "ref": p,
            "text": _join(p.title, p.title, p.description, p.use_type, p.category, cname, sname, p.sector, p.landmark,
                          size, f"{p.kanal_area:g} kanal" if p.kanal_area else "",
                          f"{p.bedrooms} bedroom" if p.bedrooms else "", _price_words(p.price)),
            "facts": _join(f"{p.title}.", f"PKR {_price_words(p.price)}." if p.price else "", size,
                           f"{p.bedrooms} bed." if p.bedrooms else "", f"{sname}, {cname}." if sname else f"{cname}."),
        })
    for b in core.big_projects_db:
        cname = city[b.city_id].name if b.city_id in city else ""
        refs = list(getattr(b, "sources", None) or [])
        plan = (getattr(b, "payment_plan", None) or {}).get("summary")
        types = "; ".join(f"{t.get('label')}: {t.get('available')} available, {_price_words(t.get('price_min'))}"
                          f"–{_price_words(t.get('price_max'))}, {t.get('sqft_min'):g}–{t.get('sqft_max'):g} sq ft"
                          for t in (getattr(b, "unit_types", None) or []))
        docs.append({
            "type": "big_project", "id": b.id, "title": b.name, "url": f"/projects?project={b.id}",
            # a developer's own website: the developer's claims, like a listing
            "tier": "listing" if refs else "unverified", "sources": refs, "city": cname,
            "text": _join(b.name, b.name, b.description, b.project_type, b.status, b.developer, getattr(b, "marketed_by", None),
                          getattr(b, "address", None), cname, types, plan, getattr(b, "offer", None)),
            "facts": _join(f"{b.name} ({b.project_type.replace('_', ' ')}, {b.status.replace('_', ' ')}).",
                           f"Developer: {b.developer}." if b.developer else "",
                           f"Address: {b.address}." if getattr(b, "address", None) else "",
                           f"{b.units_available} units available, {_price_words(b.price_from)} to {_price_words(b.price_to)}"
                           f" (inventory checked {b.inventory_checked})." if getattr(b, "units_available", None) else "",
                           f"Unit types: {types}." if types else "", f"Payment plan: {plan}." if plan else "",
                           getattr(b, "offer", None), b.description),
        })
    try:
        import megaprojects

        for m in megaprojects.all_projects():
            if m.get("portal_project"):
                continue  # already in the knowledge base as a project with its units
            refs = m.get("sources") or []
            docs.append({
                "type": "mega_project", "id": m["id"], "title": m["name"], "url": "/infrastructure",
                "tier": sources.tier_for_sources(refs) if refs else "reference", "sources": refs, "city": m.get("city"),
                "text": _join(m["name"], m.get("name_ur"), m.get("type"), m.get("status"), m.get("city"), m.get("province"),
                              m.get("authority"), m.get("summary"), m.get("impact")),
                "facts": _join(f"{m['name']} — {m.get('type')}, {m.get('status')}.",
                               f"Authority: {m.get('authority')}." if m.get("authority") else "",
                               f"Completion: {m.get('completion')}." if m.get("completion") else "",
                               m.get("summary"), m.get("impact")),
            })
    except Exception:
        pass
    for n in core.news_db:
        deep_link = bool(n.url and sources.site_of(n.url) and len((n.url.split("/", 3) + [""])[3].strip("/")) > 0)
        tier = "verified" if getattr(n, "verified", False) else (sources.tier_for_url(n.url) if deep_link else "unverified")
        docs.append({
            "type": "news", "id": n.id, "title": n.title, "url": n.url or "/news", "tier": tier,
            "sources": [{"title": n.source, "url": n.url}] if n.url else [],
            "text": _join(n.title, n.title, n.summary, n.source, n.category, " ".join(n.tags or [])),
            "facts": _join(f"{n.title}.", n.summary, f"({n.source}, {str(n.published_at)[:10]})" if n.source else ""),
            "date": str(n.published_at)[:10] if n.published_at else None,
        })
    try:
        import content

        for pg in content.pages_db:
            if getattr(pg, "status", "published") not in ("published", "active", None):
                continue
            body = _join(pg.summary, pg.body, " ".join(map(str, pg.highlights or [])), " ".join(map(str, pg.bullets or [])),
                         " ".join(f"{f.get('q', '')} {f.get('a', '')}" for f in (pg.faqs or []) if isinstance(f, dict)))
            docs.append({"type": "guide", "id": pg.id, "title": pg.title, "url": f"/pages/{pg.key}", "tier": "verified",
                         "text": _join(pg.title, pg.title, pg.subtitle, body), "facts": _join(pg.title + ".", pg.summary)})
    except Exception:
        pass
    try:
        import construction

        for g in getattr(construction, "guidelines_db", []):
            d = g.model_dump() if hasattr(g, "model_dump") else dict(g)
            title = d.get("title") or d.get("name") or "Construction guideline"
            docs.append({"type": "guideline", "id": str(d.get("id")), "title": title, "url": "/construction",
                         "tier": "reference" if d.get("source") or d.get("authority") else "verified",
                         "text": _join(title, d.get("summary"), d.get("description"), d.get("body"), d.get("authority")),
                         "facts": _join(title + ".", d.get("summary") or d.get("description"))})
    except Exception:
        pass
    return docs


# ---------------------------------------------------------------- index


class _Index:
    def __init__(self, docs: List[Dict[str, Any]]):
        self.docs = docs
        self.tf: List[Counter] = []
        self.lengths: List[int] = []
        df: Counter = Counter()
        for d in docs:
            toks = tokens(d["title"]) * 2 + tokens(d["text"])
            c = Counter(toks)
            self.tf.append(c)
            self.lengths.append(len(toks))
            df.update(c.keys())
        n = max(1, len(docs))
        self.avg = sum(self.lengths) / n if self.lengths else 1.0
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, q: List[str], k1: float = 1.4, b: float = 0.75) -> List[Tuple[float, int]]:
        out = []
        terms = Counter(q)
        for i, tf in enumerate(self.tf):
            s = 0.0
            for t, qn in terms.items():
                f = tf.get(t)
                if f:
                    s += self.idf.get(t, 0) * f * (k1 + 1) / (f + k1 * (1 - b + b * self.lengths[i] / self.avg))
            if s > 0:
                out.append((s, i))
        return out


_lock = threading.Lock()
_cache: Dict[str, Any] = {"sig": None, "at": 0.0, "index": None}
REBUILD_SECONDS = 30.0


def _signature() -> Tuple[Any, ...]:
    core = _core()
    stores = (core.cities_db, core.housing_schemes_db, core.properties_db, core.big_projects_db, core.news_db)
    return tuple((len(s), str(getattr(s[-1], "updated_at", "") or getattr(s[-1], "id", "")) if s else "") for s in stores)


def index() -> _Index:
    sig = _signature()
    with _lock:
        if _cache["index"] is None or _cache["sig"] != sig or time.monotonic() - _cache["at"] > REBUILD_SECONDS:
            _cache.update(index=_Index(_docs()), sig=sig, at=time.monotonic())
        return _cache["index"]


def invalidate() -> None:
    with _lock:
        _cache["index"] = None


# ---------------------------------------------------------------- search

_FILTER_WORDS = {"crore", "lakh", "arab", "million", "thousand", "marla", "kanal", "bedroom", "rent", "sale", "buy",
                 "house", "plot", "apartment", "shop", "office", "between", "and"}
TYPE_BOOST = {"scheme": 1.15, "city": 1.1, "mega_project": 1.05, "guide": 1.0, "property": 1.0, "news": 0.95,
              "big_project": 0.95, "guideline": 0.9}
TIER_BOOST = {"official": 1.15, "verified": 1.1, "reference": 1.05, "listing": 1.0, "unverified": 0.9}


def _passes(p: Any, f: Dict[str, Any]) -> bool:
    if f.get("max_price") and p.price and p.price > f["max_price"]:
        return False
    if f.get("min_price") and p.price and p.price < f["min_price"]:
        return False
    if f.get("bedrooms") and (p.bedrooms or 0) < f["bedrooms"]:
        return False
    if f.get("marla") and p.marla_area and not (f["marla"] * 0.85 <= p.marla_area <= f["marla"] * 1.15):
        return False
    if f.get("category") and p.category and p.category != f["category"]:
        return False
    if f.get("use_type") and p.use_type not in (f["use_type"], "mix"):
        return False
    return True


def _snippet(text: str, q: Iterable[str], width: int = 240) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= width:
        return text
    low = normalize(text)
    pos = min((low.find(t) for t in q if t and low.find(t) >= 0), default=0)
    start = max(0, pos - width // 3)
    return ("…" if start else "") + text[start:start + width].strip() + "…"


def search(query: str, k: int = 6, types: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Ranked knowledge for a question, each hit with its source, tier and a citation number."""
    started = time.perf_counter()
    k = max(1, min(int(k or 6), 20))
    wanted = set(types or [])
    filters = parse_query(query)
    # Amounts and sizes are already filters; as words they would only match stray numbers.
    q = [t for t in tokens(query) if not (t.replace(".", "").isdigit() or (filters and t in _FILTER_WORDS))]
    listing_intent = bool(set(filters) & {"max_price", "min_price", "marla", "bedrooms", "category", "purpose"})
    idx = index()
    scored = []
    for s, i in idx.score(q):
        d = idx.docs[i]
        if wanted and d["type"] not in wanted:
            continue
        if d["type"] == "property":
            if not _passes(d["ref"], filters):
                continue
            s *= 2.5 if listing_intent else 1.0
        scored.append((s * TYPE_BOOST.get(d["type"], 1.0) * TIER_BOOST.get(d["tier"], 1.0), d))
    # A structured query with no word overlap still finds matching listings ("under 1 crore").
    if not scored and filters and (not wanted or "property" in wanted):
        scored = [(0.1, d) for d in idx.docs if d["type"] == "property" and _passes(d["ref"], filters)]
    scored.sort(key=lambda x: x[0], reverse=True)
    hits = []
    for rank, (s, d) in enumerate(scored[:k], start=1):
        hit = {"cite": f"[{rank}]", "score": round(s, 3), "type": d["type"], "id": d["id"], "title": d["title"],
               "url": d["url"], "tier": d["tier"], "trust": sources.describe(d["tier"]),
               "snippet": _snippet(d.get("facts") or d["text"], q), "city": d.get("city"),
               "sources": [x for x in (d.get("sources") or []) if isinstance(x, dict)][:3]}
        if d.get("date"):
            hit["date"] = d["date"]
        if d["type"] == "property":
            p = d["ref"]
            hit.update(price=p.price, marla=p.marla_area, bedrooms=p.bedrooms, category=p.category, use_type=p.use_type)
        hits.append(hit)
    context = "\n".join(
        f"{h['cite']} {h['title']} ({h['type'].replace('_', ' ')}; {h['trust']}"
        + (f"; {h['sources'][0].get('title')}" if h["sources"] else "") + f"): {h['snippet']}"
        for h in hits)
    return {"query": query, "filters": filters, "count": len(hits), "results": hits, "context": context,
            "took_ms": round((time.perf_counter() - started) * 1000, 1),
            "how_to_cite": "Quote facts with their [n] marker; prefer official / verified sources when they disagree."}
