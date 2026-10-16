"""
GIS engine for the Real Estate Portal
=====================================

Dependency-free geospatial toolkit:

* **Base maps** — Google Earth-style imagery (Google Satellite / Hybrid / Terrain,
  Esri World Imagery) plus OpenStreetMap, OpenTopoMap and Carto.
* **Layers** — GeoJSON layers attached to any entity (city / scheme / block /
  big project): housing-society master plans, society boundaries, zone layouts,
  plot layouts, roads, green belts.
* **Geometry** — geodesic area, centroid, bounding box, point-in-polygon,
  bearing, destination point, distance matrix.
* **Export** — GeoJSON, KML (opens in Google Earth), and a self-contained
  Leaflet HTML map preview.

Coordinate conventions
----------------------
* Python tool inputs use ``[lat, lon]`` pairs (matches the portal's
  ``latitude`` / ``longitude`` fields).
* GeoJSON output uses the standard ``[lon, lat]`` order.

This module holds no portal data; ``server.py`` combines it with the property
catalogue. It is deliberately importable on its own.
"""

import html
import json
import math
import heapq
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

EARTH_RADIUS_M = 6378137.0


# ============================================================
# FRONTEND FACILITIES: LANGUAGES (incl. RTL) + THEMES
# ============================================================
#
# Every HTML surface built by this module (map, report, ticker) accepts a
# ``lang`` and a ``theme`` argument. Text is looked up in ``TRANSLATIONS`` and
# falls back to the English source string, so adding a language is just another
# dictionary entry. Themes are CSS custom properties, so a single token table
# drives the map chrome, the printable report and the ticker alike.

SUPPORTED_LANGUAGES: List[Dict[str, str]] = [
    {
        "code": "en",
        "name": "English",
        "native_name": "English",
        "dir": "ltr",
        "font_stack": '"Segoe UI", system-ui, -apple-system, Roboto, sans-serif',
    },
    {
        "code": "ur",
        "name": "Urdu",
        "native_name": "اردو",
        "dir": "rtl",
        "font_stack": '"Noto Nastaliq Urdu", "Jameel Noori Nastaleeq", "Segoe UI", Tahoma, sans-serif',
    },
]

DEFAULT_LANGUAGE = "en"
RTL_LANGUAGES = {"ur", "ar", "fa", "he"}

SUPPORTED_THEMES: List[Dict[str, str]] = [
    {"code": "auto", "name": "Auto (follow system)"},
    {"code": "light", "name": "Light"},
    {"code": "dark", "name": "Dark"},
]

DEFAULT_THEME = "auto"

THEME_TOKENS: Dict[str, Dict[str, str]] = {
    "light": {
        "--bg": "#f5f7fa",
        "--surface": "#ffffff",
        "--surface-2": "#fbfdff",
        "--line": "#d9e2ec",
        "--ink": "#12263a",
        "--muted": "#5b6b7c",
        "--accent": "#1f6feb",
        "--accent-ink": "#ffffff",
        "--pill-bg": "#eaf2ff",
        "--pill-ink": "#1f6feb",
        "--ok-bg": "#e6f7ed", "--ok-ink": "#15803d",
        "--bad-bg": "#fdeaea", "--bad-ink": "#b91c1c",
        "--neu-bg": "#eef2f7", "--neu-ink": "#475569",
        "--shadow": "0 1px 4px rgba(0,0,0,.25)",
        "--ctrl-bg": "#ffffff", "--ctrl-ink": "#12263a", "--ctrl-line": "#d9e2ec",
        "--ticker-bg": "#0f172a", "--ticker-ink": "#e2e8f0", "--ticker-line": "#1e293b",
        "--ticker-label-bg": "#b91c1c", "--ticker-label-ink": "#ffffff", "--ticker-src": "#94a3b8",
        "--tk-pos": "#4ade80", "--tk-neg": "#f87171", "--tk-neu": "#e2e8f0",
        "--ad-bg": "#fffaf0", "--ad-line": "#f0d9a8", "--ad-ink": "#3a2c10",
        "--ad-badge-bg": "#fde9c8", "--ad-badge-ink": "#8a5a00",
        "--ad-cta-bg": "#1f6feb", "--ad-cta-ink": "#ffffff", "--ad-sponsor": "#8a5a00",
    },
    "dark": {
        "--bg": "#0b1220",
        "--surface": "#121c2e",
        "--surface-2": "#0f1728",
        "--line": "#26364f",
        "--ink": "#e6edf6",
        "--muted": "#94a3b8",
        "--accent": "#4c8dff",
        "--accent-ink": "#04101f",
        "--pill-bg": "#16243c",
        "--pill-ink": "#9cc0ff",
        "--ok-bg": "#0f2a1d", "--ok-ink": "#4ade80",
        "--bad-bg": "#301a1a", "--bad-ink": "#f87171",
        "--neu-bg": "#1c2637", "--neu-ink": "#cbd5e1",
        "--shadow": "0 1px 6px rgba(0,0,0,.55)",
        "--ctrl-bg": "#121c2e", "--ctrl-ink": "#e6edf6", "--ctrl-line": "#26364f",
        "--ticker-bg": "#060b14", "--ticker-ink": "#e2e8f0", "--ticker-line": "#1e293b",
        "--ticker-label-bg": "#b91c1c", "--ticker-label-ink": "#ffffff", "--ticker-src": "#94a3b8",
        "--tk-pos": "#4ade80", "--tk-neg": "#f87171", "--tk-neu": "#e2e8f0",
        "--ad-bg": "#171308", "--ad-line": "#3a2f14", "--ad-ink": "#f3e6c8",
        "--ad-badge-bg": "#3a2f14", "--ad-badge-ink": "#f5c451",
        "--ad-cta-bg": "#4c8dff", "--ad-cta-ink": "#04101f", "--ad-sponsor": "#f5c451",
    },
}

# English source string -> localised string. Unknown strings fall back to English.
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "ur": {
        # ---- chrome ----
        "Real Estate Portal": "رئیل اسٹیٹ پورٹل",
        "Real Estate Portal — GIS analysis report": "رئیل اسٹیٹ پورٹل — جی آئی ایس تجزیاتی رپورٹ",
        "Real Estate News": "رئیل اسٹیٹ خبریں",
        "Map": "نقشہ",
        "Legend": "رہنما",
        "Language": "زبان",
        "Theme": "تھیم",
        "Auto": "خودکار",
        "Light": "روشن",
        "Dark": "تاریک",
        "Generated": "تیار کردہ",
        "Report": "رپورٹ",
        "Investment Outlook": "سرمایہ کاری کا امکان",
        # ---- portal / content ----
        "Arz-e-Pak Real Estate Portal": "ارضِ پاک رئیل اسٹیٹ پورٹل",
        "Pakistan's smart, data-driven property marketplace": "پاکستان کی ذہین اور ڈیٹا پر مبنی پراپرٹی مارکیٹ",
        "Home": "ہوم",
        "About": "تعارف",
        "About us": "ہمارے بارے میں",
        "Mission": "مشن",
        "Services": "خدمات",
        "Why choose us": "ہمیں کیوں منتخب کریں",
        "Our team": "ہماری ٹیم",
        "Careers": "ملازمتیں",
        "Help": "مدد",
        "Our journey": "ہمارا سفر",
        "Success stories": "کامیابی کی کہانیاں",
        "Contact us": "ہم سے رابطہ کریں",
        "Portal at a glance": "ایک نظر میں پورٹل",
        "Highlights": "نمایاں خصوصیات",
        "Read more": "مزید پڑھیں",
        "Learn more": "مزید جانیں",
        "Get in touch": "رابطہ کریں",
        "Reach us": "ہم تک پہنچیں",
        "Call us": "ہمیں کال کریں",
        "Email us": "ہمیں ای میل کریں",
        "Visit us": "ہم سے ملیں",
        "Office hours": "دفتری اوقات",
        "WhatsApp": "واٹس ایپ",
        "Chat with us": "ہم سے چیٹ کریں",
        "FAQs": "عام سوالات",
        "Featured partners": "نمایاں شراکت دار",
        "Advertise here": "یہاں اشتہار دیں",
        "Advertise with us": "ہمارے ساتھ اشتہار دیں",
        "Reach thousands of buyers, investors and developers across Pakistan.":
            "پاکستان بھر کے ہزاروں خریداروں، سرمایہ کاروں اور ڈویلپرز تک پہنچیں۔",
        # ---- advertisement headings ----
        "Smart technology for modern living": "جدید طرزِ زندگی کے لیے ذہین ٹیکنالوجی",
        "Build smarter — modern construction techniques": "زیادہ ذہانت سے تعمیر — جدید تعمیراتی تکنیکیں",
        "Building materials — availability & rates": "تعمیراتی مصالحہ — دستیابی اور نرخ",
        "Solar & renewable energy": "شمسی اور قابلِ تجدید توانائی",
        "Home finance & mortgages": "ہاؤس فنانس اور رہن",
        "Security & access control": "سیکیورٹی اور رسائی کنٹرول",
        "Interiors, finishes & furnishing": "اندرونی سجاوٹ اور فرنشنگ",
        "Water supply, filtration & plumbing": "پانی کی فراہمی، فلٹریشن اور پلمبنگ",
        "Tools, machinery & equipment": "اوزار، مشینری اور سامان",
        # ---- advertisement categories ----
        "Smart home & building technology": "سمارٹ ہوم اور بلڈنگ ٹیکنالوجی",
        "Modern construction techniques": "جدید تعمیراتی تکنیکیں",
        "Building materials & availability": "تعمیراتی مصالحہ اور دستیابی",
        "Solar & renewable energy category": "شمسی اور قابلِ تجدید توانائی",
        "Property & title insurance": "پراپرٹی اور ٹائٹل انشورنس",
        "Legal, titling & documentation": "قانونی، ٹائٹلنگ اور دستاویزات",
        "Moving, maintenance & other services": "شفٹنگ، دیکھ بھال اور دیگر خدمات",
        "Landscaping & outdoor": "لینڈ اسکیپنگ اور آؤٹ ڈور",
        "Elevators, lifts & parking": "لفٹیں اور پارکنگ",
        # ---- advertisement slots ----
        "Homepage hero banner": "ہوم پیج ہیرو بینر",
        "Full-width banner": "مکمل چوڑائی بینر",
        "Sidebar tile": "سائیڈ بار ٹائل",
        "In-feed native ad": "فیڈ کے اندر اشتہار",
        "Footer strip": "فوٹر پٹی",
        "Newsletter block": "نیوز لیٹر بلاک",
        "Sponsored": "اشتہار",
        "Advertise": "اشتہار",
        # ---- section headings ----
        "Key figures": "اہم اعداد و شمار",
        "Area": "رقبہ",
        "Properties": "پراپرٹیز",
        "Valuation": "قدر",
        "Population": "آبادی",
        "Development cost": "ترقیاتی لاگت",
        "Economic impact": "معاشی اثرات",
        "Cost & development perspective": "لاگت اور ترقی کا تناظر",
        "Cost sensitivity — profit margin": "لاگت کی حساسیت — منافع کا مارجن",
        "Market outlook index": "مارکیٹ آؤٹ لک انڈیکس",
        "Expected path (probability-weighted)": "متوقع راستہ (امکانات کے مطابق)",
        "Drivers": "محرک عوامل",
        "Risks": "خطرات",
        "Recommendations": "سفارشات",
        "News & market sentiment": "خبریں اور مارکیٹ کا رجحان",
        "Latest headlines": "تازہ ترین سرخیاں",
        # ---- table columns ----
        "Category": "زمرہ",
        "Count": "تعداد",
        "Built sqft": "تعمیر شدہ مربع فٹ",
        "Component": "جزو",
        "Amount (PKR)": "رقم (روپے)",
        "Scenario": "منظرنامہ",
        "Prob.": "امکان",
        "Price CAGR": "قیمت میں سالانہ ترقی",
        "Price/marla": "قیمت فی مرلہ",
        "Market value": "مارکیٹ ویلیو",
        "Dev. cost": "ترقیاتی لاگت",
        "Year": "سال",
        "Rental value": "کرایہ ویلیو",
        "Headline": "سرخی",
        "Sentiment": "رجحان",
        "Impact": "اثر",
        "Positive / neutral / negative": "مثبت / غیر جانبدار / منفی",
        # ---- area ----
        "Square feet": "مربع فٹ",
        "Square metres": "مربع میٹر",
        "Marla": "مرلہ",
        "Kanal": "کنال",
        "Acres": "ایکڑ",
        # ---- valuation ----
        "Total market value (PKR)": "کل مارکیٹ ویلیو (روپے)",
        "Average price (PKR)": "اوسط قیمت (روپے)",
        "Median price (PKR)": "وسطی قیمت (روپے)",
        "Price / sqft (PKR)": "قیمت فی مربع فٹ (روپے)",
        "Price / marla (PKR)": "قیمت فی مرلہ (روپے)",
        # ---- population ----
        "Dwellings listed": "درج رہائشیں",
        "Population (from listings)": "آبادی (درج رہائشوں سے)",
        "Avg household size": "اوسط گھریلو حجم",
        "Occupancy rate": "رہائش کی شرح",
        "Density (/km²)": "کثافت (/کلومیٹر²)",
        "Projected population (total units)": "متوقع آبادی (کل یونٹس)",
        # ---- development cost ----
        "Land development": "زمین کی ترقی",
        "Infrastructure (roads, water, sewer, power)": "بنیادی ڈھانچہ (سڑکیں، پانی، گٹر، بجلی)",
        "Construction": "تعمیرات",
        "Total": "کل",
        # ---- economic impact ----
        "Direct investment (PKR)": "براہ راست سرمایہ کاری (روپے)",
        "Indirect + induced (PKR)": "بالواسطہ + پیدا شدہ (روپے)",
        "Total economic output (PKR)": "کل معاشی پیداوار (روپے)",
        "Economic multiplier": "معاشی ضارب",
        "Construction jobs": "تعمیراتی ملازمتیں",
        "Operational jobs": "عملی ملازمتیں",
        "Annual rental value (PKR)": "سالانہ کرایہ ویلیو (روپے)",
        "Commercial activity value (PKR)": "تجارتی سرگرمی کی ویلیو (روپے)",
        # ---- cost & development ----
        "Gross development value (PKR)": "مجموعی ترقیاتی ویلیو (روپے)",
        "Land cost (PKR)": "زمین کی لاگت (روپے)",
        "Development cost (PKR)": "ترقیاتی لاگت (روپے)",
        "Total cost (PKR)": "کل لاگت (روپے)",
        "Developer profit (PKR)": "ڈویلپر منافع (روپے)",
        "Profit margin": "منافع کا مارجن",
        "ROI (project)": "منصوبے پر منافع",
        "Annualised ROI": "سالانہ منافع",
        "Cost / marla (PKR)": "لاگت فی مرلہ (روپے)",
        "Break-even price / marla (PKR)": "بریک ایون قیمت فی مرلہ (روپے)",
        "Break-even uplift needed": "درکار بریک ایون اضافہ",
        "Payback (years, rental)": "واپسی (سال، کرایہ)",
        "Viability": "قابلِ عملیت",
        "Projected units": "متوقع یونٹس",
        "Projected GDV (PKR)": "متوقع مجموعی ترقیاتی ویلیو (روپے)",
        "Projected cost (PKR)": "متوقع لاگت (روپے)",
        "Projected margin": "متوقع مارجن",
        "Cost / unit (PKR)": "لاگت فی یونٹ (روپے)",
        "Value / unit (PKR)": "ویلیو فی یونٹ (روپے)",
        # ---- outlook index ----
        "Composite index (0-100)": "مجموعی انڈیکس (0-100)",
        "News momentum": "خبروں کی رفتار",
        "Base-case price CAGR": "بنیادی قیمت میں سالانہ ترقی",
        "Model confidence": "ماڈل کا اعتماد",
        # ---- news ----
        "Items considered": "زیرِ غور آئٹمز",
        "Average impact": "اوسط اثر",
        "Net sentiment": "خالص رجحان",
        # ---- risk flags ----
        "Political/regulatory instability may delay approvals or shift policy.":
            "سیاسی/ریگولیٹری عدم استحکام منظوریوں میں تاخیر یا پالیسی میں تبدیلی کا سبب بن سکتا ہے۔",
        "Weak regulatory/titling environment raises transaction risk.":
            "کمزور ریگولیٹری/ملکیتی نظام لین دین کا خطرہ بڑھاتا ہے۔",
        "Infrastructure gaps limit near-term liveability and price upside.":
            "بنیادی ڈھانچے کی کمی قلیل مدتی رہائش اور قیمتوں میں اضافے کو محدود کرتی ہے۔",
        "Economic/mortgage conditions may dampen demand.":
            "معاشی/رہن کے حالات طلب کو کم کر سکتے ہیں۔",
        "Recent news sentiment is net negative for this market.":
            "حالیہ خبروں کا رجحان اس مارکیٹ کے لیے مجموعی طور پر منفی ہے۔",
        "No material risk flags at current factor scores.":
            "موجودہ فیکٹر اسکورز پر کوئی نمایاں خطرہ نہیں۔",
        # ---- sentiment ----
        "positive": "مثبت", "neutral": "غیر جانبدار", "negative": "منفی",
        # ---- forecast factors ----
        "development": "ترقی", "infrastructure": "بنیادی ڈھانچہ", "economic": "معاشی",
        "social": "سماجی", "political": "سیاسی", "regulatory": "ریگولیٹری", "demand": "طلب",
        # ---- construction & maintenance wings ----
        "Construction": "تعمیرات",
        "Maintenance": "دیکھ بھال",
        "Construction wing": "تعمیراتی ونگ",
        "Maintenance wing": "دیکھ بھال ونگ",
        "Construction at a glance": "ایک نظر میں تعمیرات",
        "Maintenance at a glance": "ایک نظر میں دیکھ بھال",
        "About this wing": "اس ونگ کے بارے میں",
        "Techniques": "تکنیکیں",
        "Technique": "تکنیک",
        "Systems": "نظام",
        "Materials": "مصالحہ",
        "Material": "مصالحہ",
        "Element rates": "اجزاء کے نرخ",
        "Guidelines": "رہنما اصول",
        "Guideline": "رہنما اصول",
        "Approval steps": "منظوری کے مراحل",
        "Approval workflow": "منظوری کا طریقہ کار",
        "Quality tiers": "معیار کے درجے",
        "Quality tiers & base build rates": "معیار کے درجے اور بنیادی تعمیراتی نرخ",
        "Construction techniques & systems": "تعمیراتی تکنیکیں اور نظام",
        "Key materials & current rates": "اہم مصالحہ اور موجودہ نرخ",
        "Guidelines, codes & byelaws": "رہنما اصول، کوڈ اور ضوابط",
        "Site safety (HSE)": "سائٹ کی حفاظت",
        "Interactive cost calculator": "تعمیراتی لاگت کا حساب لگانے والا",
        "Interactive maintenance-cost calculator": "دیکھ بھال لاگت کا حساب لگانے والا",
        "Cost factor": "لاگت کا عنصر",
        "Speed": "رفتار",
        "Sustainability": "پائیداری",
        "Seismic": "زلزلی",
        "Availability": "دستیابی",
        "Lead time": "ترسیل کا وقت",
        "Unit": "اکائی",
        "Rate": "نرخ",
        "Approval": "منظوری",
        "Authority": "اتھارٹی",
        "Duration": "دورانیہ",
        "Requirement": "شرط",
        "Cost band": "لاگت کی حد",
        "Emergency": "ہنگامی",
        "Response": "جواب",
        "Service life": "کارآمد زندگی",
        "Replacement": "تبدیلی",
        "Criticality": "اہمیت",
        "Frequency": "تعدد",
        "Maintainable components": "دیکھ بھال کے قابل اجزاء",
        "Maintenance services & rates": "دیکھ بھال کی خدمات اور نرخ",
        "Annual maintenance rates (PKR / sqft / year)": "سالانہ دیکھ بھال نرخ (روپے فی مربع فٹ سالانہ)",
        "Defect catalogue": "نقص کی فہرست",
        "Defect": "نقص",
        "Severity": "شدت",
        "Urgency": "فوری ضرورت",
        "Repair": "مرمت",
        "Includes": "شامل",
        "AMC tiers": "معاہدہ دیکھ بھال کے درجے",
        "Maintenance guidelines": "دیکھ بھال کے رہنما اصول",
        "Property type": "پراپرٹی کی قسم",
        "Basic": "بنیادی",
        "Standard": "معیاری",
        "Premium": "اعلیٰ",
        "Comprehensive": "جامع",
        "Estimate summary": "تخمینے کا خلاصہ",
        "Assumptions": "مفروضات",
        "Element build-up": "اجزاء کی تفصیل",
        "Materials take-off": "مصالحے کی مقدار",
        "Construction timeline": "تعمیراتی ٹائم لائن",
        "Base rate / sqft": "بنیادی نرخ فی مربع فٹ",
        "Effective rate / sqft": "موثر نرخ فی مربع فٹ",
        "Building-type factor": "عمارت کی قسم کا عنصر",
        "City factor": "شہر کا عنصر",
        "Project cost": "منصوبے کی لاگت",
        "Total project cost": "کل منصوبے کی لاگت",
        "Cost / sqft": "لاگت فی مربع فٹ",
        "Duration": "دورانیہ",
        "Days": "دن",
        "Weight %": "وزن فیصد",
        "Share %": "حصہ فیصد",
        "Phase": "مرحلہ",
        "Quantity": "مقدار",
        "With wastage": "ضائع کے ساتھ",
        "Cost": "لاگت",
        "Construction cost report": "تعمیراتی لاگت رپورٹ",
        "Maintenance report": "دیکھ بھال رپورٹ",
        "Maintenance summary": "دیکھ بھال کا خلاصہ",
        "Annual cost": "سالانہ لاگت",
        "Annual cost by category": "زمرے کے مطابق سالانہ لاگت",
        "Preventive schedule (12 months)": "حفاظتی شیڈول (12 ماہ)",
        "Capital replacements (15 years)": "سرمائے کی تبدیلیاں (15 سال)",
        "Monthly": "ماہانہ",
        "Reserve / year": "سالانہ ذخیرہ",
        "Condition": "حالت",
        "Month": "مہینہ",
        "Techniques · cost analysis · codes & guidelines": "تکنیکیں · لاگت کا تجزیہ · کوڈ اور رہنما اصول",
        "Services · lifecycle · condition · cost": "خدمات · زندگی کا دورانیہ · حالت · لاگت",
        "Construction · cost estimation · codes": "تعمیرات · لاگت کا تخمینہ · کوڈ",
    }
}


def get_language(code: Optional[str]) -> Dict[str, str]:
    """Resolve a language code (``ur-PK`` -> ``ur``); unknown codes fall back to English."""
    c = (code or DEFAULT_LANGUAGE).split("-")[0].split("_")[0].strip().lower()
    return next((l for l in SUPPORTED_LANGUAGES if l["code"] == c), SUPPORTED_LANGUAGES[0])


def language_codes() -> List[str]:
    return [l["code"] for l in SUPPORTED_LANGUAGES]


def is_rtl(code: Optional[str]) -> bool:
    return get_language(code)["code"] in RTL_LANGUAGES


def normalize_theme(theme: Optional[str]) -> str:
    t = (theme or DEFAULT_THEME).strip().lower()
    return t if t in {x["code"] for x in SUPPORTED_THEMES} else DEFAULT_THEME


def translate(text: Any, lang: Optional[str] = DEFAULT_LANGUAGE) -> str:
    """Localise a UI string. Unknown strings (and English) pass through unchanged."""
    s = "" if text is None else str(text)
    if not s:
        return s
    code = get_language(lang)["code"]
    if code == DEFAULT_LANGUAGE:
        return s
    table = TRANSLATIONS.get(code, {})
    if s in table:
        return table[s]
    if code == "ur":
        m = re.match(r"^Future predictions — (\d+)-year scenarios$", s)
        if m:
            return f"مستقبل کی پیش گوئیاں — {m.group(1)} سالہ منظرنامے"
        m = re.match(r"^([a-z]+) \((\d+)/(\d+)\)$", s)
        if m and m.group(1) in table:
            return f"{table[m.group(1)]} ({m.group(2)}/{m.group(3)})"
        m = re.match(r"^Suggested stance: (.+)\.$", s)
        if m:
            return f"تجویز کردہ حکمتِ عملی: {m.group(1)}۔"
        m = re.match(r"^Plan on a base-case price CAGR of ([0-9.]+%)(.*)$", s)
        if m:
            return f"بنیادی منظرنامے میں قیمت کی سالانہ ترقی تقریباً {m.group(1)} متوقع ہے۔{m.group(2)}"
    return s


def _tokens_css(selector: str, tokens: Dict[str, str]) -> str:
    return f"{selector} {{ " + " ".join(f"{k}:{v};" for k, v in tokens.items()) + " }"


def theme_style(theme: Optional[str] = DEFAULT_THEME) -> str:
    """CSS that establishes the theme tokens for both the initial paint and the client toggle."""
    t = normalize_theme(theme)
    light = _tokens_css(":root", THEME_TOKENS["light"])
    dark = _tokens_css(":root", THEME_TOKENS["dark"])
    parts: List[str] = []
    if t == "dark":
        parts.append(dark)
    elif t == "light":
        parts.append(light)
    else:
        parts.append(light)
        parts.append(f"@media (prefers-color-scheme: dark) {{ {dark} }}")
    # `html[data-theme]` beats `:root`, so the client-side toggle always wins.
    parts.append(_tokens_css('html[data-theme="light"]', THEME_TOKENS["light"]))
    parts.append(_tokens_css('html[data-theme="dark"]', THEME_TOKENS["dark"]))
    return "<style>\n" + "\n".join(parts) + "\n</style>"


THEME_JS = """<script>
(function () {
  var KEY = 'portal-theme';
  function read() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function apply(t) {
    var root = document.documentElement;
    if (!t || t === 'auto') { root.removeAttribute('data-theme'); }
    else { root.setAttribute('data-theme', t); }
    // keep any embedded maps in step
    try {
      var frames = document.querySelectorAll('iframe');
      for (var i = 0; i < frames.length; i++) {
        try {
          var d = frames[i].contentDocument;
          if (!d) continue;
          if (!t || t === 'auto') { d.documentElement.removeAttribute('data-theme'); }
          else { d.documentElement.setAttribute('data-theme', t); }
        } catch (e) {}
      }
    } catch (e) {}
  }
  window.portalTheme = {
    current: function () { return read() || 'auto'; },
    set: function (t) {
      try { (t === 'auto') ? localStorage.removeItem(KEY) : localStorage.setItem(KEY, t); } catch (e) {}
      apply(t);
      return t;
    },
    cycle: function () {
      var cur = read() || 'auto';
      return window.portalTheme.set(cur === 'auto' ? 'light' : (cur === 'light' ? 'dark' : 'auto'));
    },
    init: function () { var t = read(); if (t) apply(t); }
  };
  window.portalSetLang = function (code) {
    try {
      var u = new URL(window.location.href);
      u.searchParams.set('lang', code);
      window.location.href = u.toString();
    } catch (e) {}
  };
  window.portalTheme.init();
})();
</script>"""


def lang_links_html(current: Optional[str] = DEFAULT_LANGUAGE, css_class: str = "langlink") -> str:
    """A small EN | اردو switch that preserves the rest of the query string."""
    cur = get_language(current)["code"]
    out = []
    for lang in SUPPORTED_LANGUAGES:
        active = " active" if lang["code"] == cur else ""
        out.append(
            f'<a href="?lang={lang["code"]}" class="{css_class}{active}" role="button" '
            f'data-lang="{lang["code"]}" aria-current="{"true" if active else "false"}">'
            f"{html.escape(lang['native_name'])}</a>"
        )
    return "".join(out)


# ============================================================
# BASE MAPS  (Google Earth-type imagery + open alternatives)
# ============================================================

BASE_MAPS: List[Dict[str, Any]] = [
    {
        "id": "google_satellite",
        "name": "Google Satellite",
        "provider": "Google",
        "type": "xyz",
        "url_template": "https://{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        "subdomains": ["mt0", "mt1", "mt2", "mt3"],
        "attribution": "Imagery © Google",
        "max_zoom": 21,
        "description": "Google Earth-style satellite imagery.",
    },
    {
        "id": "google_hybrid",
        "name": "Google Hybrid",
        "provider": "Google",
        "type": "xyz",
        "url_template": "https://{s}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        "subdomains": ["mt0", "mt1", "mt2", "mt3"],
        "attribution": "Imagery © Google",
        "max_zoom": 21,
        "description": "Satellite imagery with labels and roads.",
    },
    {
        "id": "google_terrain",
        "name": "Google Terrain",
        "provider": "Google",
        "type": "xyz",
        "url_template": "https://{s}.google.com/vt/lyrs=p&x={x}&y={y}&z={z}",
        "subdomains": ["mt0", "mt1", "mt2", "mt3"],
        "attribution": "Map data © Google",
        "max_zoom": 20,
        "description": "Terrain / physical map.",
    },
    {
        "id": "google_streets",
        "name": "Google Streets",
        "provider": "Google",
        "type": "xyz",
        "url_template": "https://{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
        "subdomains": ["mt0", "mt1", "mt2", "mt3"],
        "attribution": "Map data © Google",
        "max_zoom": 20,
        "description": "Google road map.",
    },
    {
        "id": "esri_world_imagery",
        "name": "Esri World Imagery",
        "provider": "Esri",
        "type": "xyz",
        "url_template": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "subdomains": None,
        "attribution": "Esri, Maxar, Earthstar Geographics",
        "max_zoom": 19,
        "description": "High-resolution global satellite imagery.",
    },
    {
        "id": "osm",
        "name": "OpenStreetMap",
        "provider": "OpenStreetMap",
        "type": "xyz",
        "url_template": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "subdomains": ["a", "b", "c"],
        "attribution": "© OpenStreetMap contributors",
        "max_zoom": 19,
        "description": "Community-maintained road map.",
    },
    {
        "id": "opentopomap",
        "name": "OpenTopoMap",
        "provider": "OpenTopoMap",
        "type": "xyz",
        "url_template": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        "subdomains": ["a", "b", "c"],
        "attribution": "© OpenTopoMap (CC-BY-SA)",
        "max_zoom": 17,
        "description": "Topographic map with contour lines.",
    },
    {
        "id": "carto_dark",
        "name": "Carto Dark Matter",
        "provider": "CARTO",
        "type": "xyz",
        "url_template": "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        "subdomains": ["a", "b", "c", "d"],
        "attribution": "© OpenStreetMap contributors © CARTO",
        "max_zoom": 20,
        "description": "Dark basemap, good for data overlays.",
    },
]

DEFAULT_BASE_MAP = "google_hybrid"


def get_base_map(base_map_id: str) -> Optional[Dict[str, Any]]:
    return next((b for b in BASE_MAPS if b["id"] == base_map_id), None)


def list_base_maps() -> List[Dict[str, Any]]:
    return BASE_MAPS


# ============================================================
# GEOMETRY HELPERS  (input lon/lat arrays in GeoJSON order)
# ============================================================

Coord = Tuple[float, float]


def _close_ring(ring: List[Coord]) -> List[Coord]:
    if ring and list(ring[0]) != list(ring[-1]):
        return list(ring) + [list(ring[0])]
    return list(ring)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return round((math.degrees(math.atan2(x, y)) + 360) % 360, 2)


def destination_point(lat: float, lon: float, bearing: float, distance_m: float) -> Coord:
    p1 = math.radians(lat)
    l1 = math.radians(lon)
    brg = math.radians(bearing)
    d = distance_m / EARTH_RADIUS_M
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(brg))
    l2 = l1 + math.atan2(math.sin(brg) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2))
    return (math.degrees(p2), math.degrees(l2))


def polygon_area_sqm(ring: List[Coord]) -> float:
    """Geodesic area of a polygon ring given as [(lon, lat), ...]."""
    ring = _close_ring(ring)
    if len(ring) < 4:
        return 0.0
    total = 0.0
    for i in range(len(ring) - 1):
        lon1, lat1 = ring[i]
        lon2, lat2 = ring[i + 1]
        total += math.radians(lon2 - lon1) * (2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2)))
    return abs(total) * EARTH_RADIUS_M * EARTH_RADIUS_M / 2.0


def polygon_centroid(ring: List[Coord]) -> Coord:
    """Centroid of a ring given as [(lon, lat), ...]; returns (lat, lon)."""
    ring = _close_ring(ring)
    n = len(ring)
    if n == 0:
        return (0.0, 0.0)
    a = cx = cy = 0.0
    for i in range(n - 1):
        x1, y1 = ring[i]
        x2, y2 = ring[i + 1]
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if a == 0:  # degenerate -> average
        lons = [c[0] for c in ring]
        lats = [c[1] for c in ring]
        return (sum(lats) / len(lats), sum(lons) / len(lons))
    a *= 0.5
    cx /= 6 * a
    cy /= 6 * a
    return (cy, cx)


def bbox_of_coords(points: List[Coord]) -> Dict[str, float]:
    """Bounding box of [(lon, lat), ...] -> {south, west, north, east}."""
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    return {"south": min(lats), "west": min(lons), "north": max(lats), "east": max(lons)}


def point_in_polygon(lat: float, lon: float, ring: List[Coord]) -> bool:
    """Ray-casting test; ring as [(lon, lat), ...]."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-18) + xi):
            inside = not inside
        j = i
    return inside


def coords_from_latlon_list(pairs: List[List[float]]) -> List[Coord]:
    """[[lat, lon], ...] -> [[lon, lat], ...] (GeoJSON order, lists not tuples)."""
    return [[float(p[1]), float(p[0])] for p in pairs]


# ============================================================
# GEOJSON BUILDERS
# ============================================================


def point_feature(lat: float, lon: float, properties: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": properties or {}}


def polygon_feature(pairs_latlon: List[List[float]], properties: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ring = _close_ring(coords_from_latlon_list(pairs_latlon))
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}, "properties": properties or {}}


def line_feature(pairs_latlon: List[List[float]], properties: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ring = coords_from_latlon_list(pairs_latlon)
    return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": ring}, "properties": properties or {}}


def bbox_polygon_pairs(south: float, west: float, north: float, east: float) -> List[List[float]]:
    return [[south, west], [south, east], [north, east], [north, west]]


def feature_collection(features: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}


def plan_footprint(north: float, south: float, east: float, west: float) -> Dict[str, Any]:
    return polygon_feature(bbox_polygon_pairs(south, west, north, east))


def geojson_bbox(geojson: Dict[str, Any]) -> Optional[Dict[str, float]]:
    pts: List[Coord] = []

    def walk(node: Any) -> None:
        if isinstance(node, (list, tuple)):
            if node and isinstance(node[0], (int, float)) and len(node) >= 2:
                pts.append((float(node[0]), float(node[1])))
            else:
                for child in node:
                    walk(child)

    if geojson.get("type") == "FeatureCollection":
        for f in geojson.get("features", []):
            walk(f.get("geometry", {}).get("coordinates"))
    else:
        walk(geojson.get("coordinates"))
    return bbox_of_coords(pts) if pts else None


# ============================================================
# GIS LAYER MODEL + STORE
# ============================================================


class GeoLayer(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    layer_type: str = "master_plan"  # master_plan | boundary | zone | plot_layout | road | green_area | annotation
    entity_type: str = "scheme"  # city | scheme | block | bigproject
    entity_id: str
    description: Optional[str] = None
    geojson: Dict[str, Any] = Field(default_factory=dict)  # FeatureCollection
    base_map: str = DEFAULT_BASE_MAP
    style: Dict[str, Any] = Field(
        default_factory=lambda: {"color": "#e6194b", "fillColor": "#e6194b", "fillOpacity": 0.25, "weight": 2, "opacity": 0.9}
    )
    visible: bool = True
    z_index: int = 0
    opacity: float = 1.0
    source_url: Optional[str] = None  # link to original master plan PDF/image
    image_url: Optional[str] = None  # rectified raster master plan
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


GIS_LAYERS: List[GeoLayer] = []


def find_layer(layer_id: str) -> Optional[GeoLayer]:
    return next((l for l in GIS_LAYERS if l.id == layer_id), None)


def list_layers(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    layer_type: Optional[str] = None,
) -> List[GeoLayer]:
    out = []
    for l in GIS_LAYERS:
        if entity_type and l.entity_type != entity_type:
            continue
        if entity_id and l.entity_id != entity_id:
            continue
        if layer_type and l.layer_type != layer_type:
            continue
        out.append(l)
    return sorted(out, key=lambda l: (l.z_index, l.created_at))


def add_layer(layer: GeoLayer) -> GeoLayer:
    GIS_LAYERS.append(layer)
    return layer


def delete_layer(layer_id: str) -> bool:
    l = find_layer(layer_id)
    if not l:
        return False
    GIS_LAYERS.remove(l)
    return True


# ============================================================
# KML EXPORT  (opens in Google Earth)
# ============================================================


def _kml_ring(coords: List[Coord]) -> str:
    return " ".join(f"{lon},{lat},0" for lon, lat in coords)


def _kml_geometry(geom: Dict[str, Any]) -> str:
    gtype = geom.get("type")
    c = geom.get("coordinates")
    if gtype == "Point":
        return f"<Point><coordinates>{c[0]},{c[1]},0</coordinates></Point>"
    if gtype == "LineString":
        return f"<LineString><coordinates>{_kml_ring(c)}</coordinates></LineString>"
    if gtype == "Polygon":
        outer = _kml_ring(c[0])
        holes = "".join(
            f"<innerBoundaryIs><LinearRing><coordinates>{_kml_ring(r)}</coordinates></LinearRing></innerBoundaryIs>"
            for r in c[1:]
        )
        return (
            "<Polygon><outerBoundaryIs><LinearRing><coordinates>"
            f"{outer}</coordinates></LinearRing></outerBoundaryIs>{holes}</Polygon>"
        )
    if gtype == "MultiPolygon":
        return "<MultiGeometry>" + "".join(_kml_geometry({"type": "Polygon", "coordinates": p}) for p in c) + "</MultiGeometry>"
    return ""


def _kml_color(hex_color: str, opacity: float = 1.0) -> str:
    """#rrggbb + opacity -> aabbggrr (KML order)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        h = "ff0000"
    r, g, b = h[0:2], h[2:4], h[4:6]
    aa = f"{max(0, min(255, int(opacity * 255))):02x}"
    return f"{aa}{b}{g}{r}"


def build_kml(name: str, layers: List[GeoLayer]) -> str:
    styles = []
    placemarks = []
    for idx, layer in enumerate(layers):
        style_id = f"style{idx}"
        color = layer.style.get("color", "#e6194b")
        fill = layer.style.get("fillColor", color)
        styles.append(
            f'<Style id="{style_id}">'
            f'<LineStyle><color>{_kml_color(color, layer.style.get("opacity", 0.9))}</color>'
            f'<width>{layer.style.get("weight", 2)}</width></LineStyle>'
            f'<PolyStyle><color>{_kml_color(fill, layer.style.get("fillOpacity", 0.25))}</color></PolyStyle>'
            f'<IconStyle><color>{_kml_color(color)}</color></IconStyle>'
            "</Style>"
        )
        for feature in layer.geojson.get("features", []):
            geom = feature.get("geometry", {})
            if not geom:
                continue
            props = feature.get("properties", {})
            fname = props.get("name") or layer.name
            desc = props.get("description") or layer.description or ""
            placemarks.append(
                f"<Placemark><name>{fname}</name><description>{desc}</description>"
                f"<styleUrl>#{style_id}</styleUrl>{_kml_geometry(geom)}</Placemark>"
            )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"<name>{name}</name>"
        + "".join(styles)
        + "".join(placemarks)
        + "</Document></kml>"
    )


# ============================================================
# INTERACTIVE MAP PREVIEW  (Leaflet, self-contained HTML)
# ============================================================

_LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
_LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"


_MAP_TEMPLATE = """<!DOCTYPE html>
<html lang="__LANG__" dir="__DIR__">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__</title>
  <link rel="stylesheet" href="__LEAFLET_CSS__" />
  __THEME_STYLE__
  <style>
    html, body, #map { height: 100%; margin: 0; }
    body { background: var(--bg, #f5f7fa); font-family: __FONT_STACK__; }
    .legend { background: var(--ctrl-bg, #fff); color: var(--ctrl-ink, #12263a);
              padding: 8px 10px; border-radius: 6px; font: 12px/1.5 __FONT_STACK__;
              box-shadow: var(--shadow, 0 1px 4px rgba(0,0,0,.3)); border: 1px solid var(--ctrl-line, #d9e2ec);
              max-height: 70vh; overflow: auto; }
    .legend .sw { display:inline-block; width:12px; height:12px; margin-right:6px; border-radius:2px; vertical-align:middle; }
    .legend .grp { margin-top: 6px; }
    .portal-ticker-slot { position: absolute; top: 0; left: 0; right: 0; z-index: 1000; }
    body.has-ticker .leaflet-top { top: 42px; }
    .portal-ui { background: var(--ctrl-bg, #fff); color: var(--ctrl-ink, #12263a);
                 border: 1px solid var(--ctrl-line, #d9e2ec); border-radius: 6px;
                 box-shadow: var(--shadow, 0 1px 4px rgba(0,0,0,.3)); padding: 5px 8px;
                 font: 12px/1.5 __FONT_STACK__; display: flex; gap: 8px; align-items: center; }
    .portal-ui button { font: inherit; color: inherit; background: transparent; cursor: pointer;
                        border: 1px solid var(--ctrl-line, #ccc); border-radius: 4px; padding: 1px 8px; }
    .langlink { color: inherit; text-decoration: none; padding: 1px 7px; border-radius: 4px; }
    .langlink.active { background: var(--pill-bg, #eaf2ff); color: var(--pill-ink, #1f6feb); font-weight: 600; }
  </style>
</head>
<body class="__BODY_CLASS__">
<div class="portal-ticker-slot">__TICKER__</div>
<div id="map"></div>
__THEME_JS__
<script src="__LEAFLET_JS__"></script>
<script>
  const TITLE = __TITLE_JSON__;
  const BASE_MAPS = __BASE_MAPS_JSON__;
  const OVERLAYS = __OVERLAYS_JSON__;
  const MARKERS = __MARKERS_JSON__;
  const DEFAULT_BASE = __DEFAULT_BASE__;
  const UI = __UI_JSON__;
  const LEGEND_LABEL = __LEGEND_LABEL__;

  const map = L.map('map').setView([__CENTER_LAT__, __CENTER_LON__], __ZOOM__);

  const baseLayers = {};
  let defaultBase = null;
  BASE_MAPS.forEach(b => {
    const opts = { attribution: b.attribution, maxZoom: b.maxZoom };
    if (b.subdomains) opts.subdomains = b.subdomains;
    const layer = L.tileLayer(b.url, opts);
    baseLayers[b.name] = layer;
    if (b.id === DEFAULT_BASE) defaultBase = layer;
  });
  (defaultBase || Object.values(baseLayers)[0]).addTo(map);

  const overlayLayers = {};
  const bounds = L.latLngBounds([]);

  OVERLAYS.forEach((ov, i) => {
    const styleFn = (feature) => {
      if (ov.choropleth && feature.properties && feature.properties._style) return feature.properties._style;
      return ov.style || { color: '#e6194b', fillColor: '#e6194b', fillOpacity: 0.25, weight: 2 };
    };
    const layer = L.geoJSON(ov.geojson, {
      style: styleFn,
      pointToLayer: (f, latlng) => L.circleMarker(latlng, { radius: 6, color: (ov.style && ov.style.color) || '#e6194b' }),
      onEachFeature: (f, lyr) => {
        const p = f.properties || {};
        const lines = [];
        if (p.name) lines.push('<b>' + p.name + '</b>');
        if (ov.valueProp && p[ov.valueProp] !== undefined && p[ov.valueProp] !== null) {
          lines.push((ov.valueLabel || ov.valueProp) + ': ' + p[ov.valueProp]);
        }
        if (p.description) lines.push(p.description);
        if (lines.length) lyr.bindPopup(lines.join('<br>'));
      }
    });
    if (!ov.choropleth && ov.name) layer.bindPopup(ov.name);
    layer.addTo(map);
    overlayLayers[ov.name || ('Layer ' + (i + 1))] = layer;
    try { const b = layer.getBounds(); if (b.isValid()) bounds.extend(b); } catch (e) {}
  });

  MARKERS.forEach(m => {
    const mk = L.marker([m.lat, m.lon]).addTo(map);
    if (m.title || m.description) mk.bindPopup('<b>' + (m.title || '') + '</b><br>' + (m.description || ''));
    bounds.extend([m.lat, m.lon]);
  });

  L.control.layers(baseLayers, overlayLayers, { collapsed: false }).addTo(map);
  L.control.scale().addTo(map);

  if (bounds.isValid()) map.fitBounds(bounds.pad(0.15));

  if (UI.controls) {
    const ctl = L.control({ position: 'topleft' });
    ctl.onAdd = function () {
      const div = L.DomUtil.create('div', 'portal-ui');
      L.DomEvent.disableClickPropagation(div);
      let h = '';
      if (UI.langLinks) h += '<span>' + UI.langLinks + '</span>';
      if (UI.themeToggle) h += '<button type="button" title="' + UI.themeLabel + '" onclick="window.portalTheme.cycle()">\\u25D0</button>';
      div.innerHTML = h;
      return div;
    };
    ctl.addTo(map);
  }
  document.querySelectorAll('.langlink').forEach(a => a.addEventListener('click', e => {
    e.preventDefault(); window.portalSetLang(a.dataset.lang);
  }));

  const legend = L.control({ position: 'bottomright' });
  legend.onAdd = function () {
    const div = L.DomUtil.create('div', 'legend');
    let html = '<b>' + TITLE + '</b>';
    const hasGrad = OVERLAYS.some(o => o.legend && o.legend.length);
    if (hasGrad) {
      OVERLAYS.forEach(o => {
        if (!(o.legend && o.legend.length)) return;
        html += '<div class="grp"><b>' + (o.name || '') + '</b>';
        o.legend.forEach(e => {
          html += '<div><span class="sw" style="background:' + e.color + '"></span>' + e.label + '</div>';
        });
        html += '</div>';
      });
    } else {
      html += '<br>' + OVERLAYS.map(o =>
        '<span class="sw" style="background:' + ((o.style && o.style.color) || '#e6194b') + '"></span>' + (o.name || '')).join('<br>');
    }
    div.innerHTML = html;
    return div;
  };
  legend.addTo(map);
</script>
</body>
</html>"""


def build_map_html(
    title: str,
    center_lat: float,
    center_lon: float,
    zoom: int = 14,
    base_map_id: str = DEFAULT_BASE_MAP,
    overlays: Optional[List[Dict[str, Any]]] = None,
    markers: Optional[List[Dict[str, Any]]] = None,
    ticker_html: str = "",
    lang: str = DEFAULT_LANGUAGE,
    theme: str = DEFAULT_THEME,
    lang_links: bool = True,
    theme_toggle: bool = True,
) -> str:
    """Return a self-contained Leaflet page with a base-map switcher and overlays.

    Overlays may be plain (``style``) or choropleth (``choropleth: true`` +
    per-feature ``properties._style`` + a ``legend`` list). ``ticker_html`` is an
    optional news-ticker fragment (see :func:`build_ticker_html`) pinned to the top.

    ``lang`` localises the UI chrome (RTL languages flip the document direction) and
    ``theme`` selects the light/dark token set; both render a switcher in the corner.
    """
    overlays = overlays or []
    markers = markers or []

    language = get_language(lang)
    body_class = "has-ticker" if ticker_html else ""
    ui = {
        "controls": bool(lang_links or theme_toggle),
        "langLinks": lang_links_html(language["code"]) if lang_links else "",
        "themeToggle": bool(theme_toggle),
        "themeLabel": translate("Theme", language["code"]),
    }

    base_maps_js = []
    for b in BASE_MAPS:
        base_maps_js.append(
            {
                "id": b["id"],
                "name": b["name"],
                "url": b["url_template"],
                "attribution": b["attribution"],
                "maxZoom": b.get("max_zoom", 19),
                **({"subdomains": b["subdomains"]} if b.get("subdomains") else {}),
            }
        )

    return (
        _MAP_TEMPLATE.replace("__LANG__", language["code"])
        .replace("__DIR__", language["dir"])
        .replace("__FONT_STACK__", language["font_stack"])
        .replace("__THEME_STYLE__", theme_style(theme))
        .replace("__THEME_JS__", THEME_JS if ui["controls"] else "")
        .replace("__BODY_CLASS__", body_class)
        .replace("__TITLE__", html.escape(str(title)))
        .replace("__TICKER__", ticker_html or "")
        .replace("__TITLE_JSON__", json.dumps(str(title)))
        .replace("__LEGEND_LABEL__", json.dumps(translate("Legend", language["code"])))
        .replace("__UI_JSON__", json.dumps(ui))
        .replace("__LEAFLET_CSS__", _LEAFLET_CSS)
        .replace("__LEAFLET_JS__", _LEAFLET_JS)
        .replace("__BASE_MAPS_JSON__", json.dumps(base_maps_js))
        .replace("__OVERLAYS_JSON__", json.dumps(overlays))
        .replace("__MARKERS_JSON__", json.dumps(markers))
        .replace("__DEFAULT_BASE__", json.dumps(base_map_id))
        .replace("__CENTER_LAT__", repr(float(center_lat)))
        .replace("__CENTER_LON__", repr(float(center_lon)))
        .replace("__ZOOM__", str(int(zoom)))
    )


# ============================================================
# PLANAR PROJECTION + BUFFERS  (geodesic area, planar math)
# ============================================================


def project(lat: float, lon: float, lat0: float, lon0: float) -> Coord:
    """WGS84 -> local equirectangular metres around (lat0, lon0)."""
    x = math.radians(lon - lon0) * math.cos(math.radians(lat0)) * EARTH_RADIUS_M
    y = math.radians(lat - lat0) * EARTH_RADIUS_M
    return (x, y)


def unproject(x: float, y: float, lat0: float, lon0: float) -> Coord:
    """Local metres -> WGS84; returns (lat, lon)."""
    lat = lat0 + math.degrees(y / EARTH_RADIUS_M)
    lon = lon0 + math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(lat0))))
    return (lat, lon)


def convex_hull(points: List[Coord]) -> List[Coord]:
    """Andrew's monotone chain. Points are (x, y) floats."""
    pts = sorted(set((round(p[0], 6), round(p[1], 6)) for p in points))
    if len(pts) <= 2:
        return pts

    def cross(o: Coord, a: Coord, b: Coord) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: List[Coord] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: List[Coord] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _each_position(coords: Any):
    if not coords:
        return
    if isinstance(coords[0], (int, float)):
        yield (float(coords[0]), float(coords[1]))
    else:
        for c in coords:
            yield from _each_position(c)


def geometry_positions(geometry: Dict[str, Any]) -> List[Coord]:
    """All (lon, lat) positions in any GeoJSON geometry."""
    return list(_each_position(geometry.get("coordinates")))


def circle_polygon(lat: float, lon: float, radius_m: float, segments: int = 64) -> Dict[str, Any]:
    ring: List[List[float]] = []
    for i in range(segments):
        brg = 360.0 * i / segments
        la, lo = destination_point(lat, lon, brg, radius_m)
        ring.append([lo, la])
    ring.append(list(ring[0]))
    return {"type": "Polygon", "coordinates": [ring]}


def buffer_geometry(geometry: Dict[str, Any], distance_m: float, segments: int = 48) -> Optional[Dict[str, Any]]:
    """Buffer a GeoJSON geometry by ``distance_m`` metres.

    Implemented as the convex hull of a circle swept along every vertex, which is
    exact for points/lines and for convex polygons, and an acceptable envelope
    for concave ones (concavities are filled).
    """
    positions = geometry_positions(geometry)
    if not positions or distance_m <= 0:
        return None
    lat0 = sum(p[1] for p in positions) / len(positions)
    lon0 = sum(p[0] for p in positions) / len(positions)

    pts: List[Coord] = []
    for lon, lat in positions:
        x, y = project(lat, lon, lat0, lon0)
        for i in range(segments):
            a = 2 * math.pi * i / segments
            pts.append((x + distance_m * math.cos(a), y + distance_m * math.sin(a)))

    hull = convex_hull(pts)
    if len(hull) < 3:
        return None
    ring: List[List[float]] = []
    for x, y in hull:
        lat, lon = unproject(x, y, lat0, lon0)
        ring.append([lon, lat])
    ring.append(list(ring[0]))
    return {"type": "Polygon", "coordinates": [ring]}


def multi_ring_buffer(lat: float, lon: float, radii_m: List[float], segments: int = 72) -> List[Dict[str, Any]]:
    """Concentric rings around a point; each is an annulus (outer ring + hole)."""
    out: List[Dict[str, Any]] = []
    prev = 0.0
    ordered = sorted(r for r in radii_m if r > 0)
    for i, r in enumerate(ordered):
        outer = circle_polygon(lat, lon, r, segments)["coordinates"][0]
        if prev <= 0:
            geom: Dict[str, Any] = {"type": "Polygon", "coordinates": [outer]}
        else:
            inner = circle_polygon(lat, lon, prev, segments)["coordinates"][0]
            geom = {"type": "Polygon", "coordinates": [outer, inner]}
        out.append({"index": i, "inner_m": prev, "outer_m": r, "geometry": geom})
        prev = r
    return out


def length_m(geometry: Dict[str, Any]) -> float:
    """Length of a LineString/MultiLineString/Polygon boundary in metres."""
    total = 0.0
    gtype = geometry.get("type")
    lines = []
    c = geometry.get("coordinates") or []
    if gtype == "LineString":
        lines = [c]
    elif gtype == "MultiLineString":
        lines = c
    elif gtype == "Polygon":
        lines = c
    elif gtype == "MultiPolygon":
        lines = [r for poly in c for r in poly]
    for line in lines:
        for i in range(len(line) - 1):
            lon1, lat1 = line[i]
            lon2, lat2 = line[i + 1]
            total += haversine_m(lat1, lon1, lat2, lon2)
    return total


# ============================================================
# THEMATIC MAPPING  (choropleth classification)
# ============================================================

CHOROPLETH_PALETTES: Dict[str, List[str]] = {
    "blues": ["#eff3ff", "#c6dbef", "#9ecae1", "#6baed6", "#4292c6", "#2171b5", "#084594"],
    "greens": ["#edf8e9", "#c7e9c0", "#a1d99b", "#74c476", "#41ab5d", "#238b45", "#005a32"],
    "reds": ["#fee5d9", "#fcae91", "#fb6a4a", "#de2d26", "#a50f15"],
    "oranges": ["#feedde", "#fdbe85", "#fd8d3c", "#e6550d", "#a63603"],
    "purples": ["#f2f0f7", "#dadaeb", "#bcbddc", "#9e9ac8", "#807dba", "#6a51a3", "#54278f"],
    "ylgnbu": ["#ffffd9", "#edf8b1", "#c7e9b4", "#7fcdbb", "#41b6c4", "#1d91c0", "#225ea8", "#0c2c84"],
    "spectral": ["#d53e4f", "#fc8d59", "#fee08b", "#e6f598", "#99d594", "#3288bd"],
}


def quantile_breaks(values: List[float], classes: int = 5) -> List[float]:
    """Return upper bounds that split ``values`` into up to ``classes`` quantile bins."""
    vals = sorted(v for v in values if v is not None)
    unique = sorted(set(vals))
    if not vals or len(unique) <= 1:
        return []
    classes = max(2, min(classes, len(unique)))
    if len(vals) <= classes:
        return unique[:-1]
    breaks = []
    for i in range(1, classes):
        breaks.append(vals[int(len(vals) * i / classes)])
    return sorted(set(breaks))


def _fmt_num(v: float) -> str:
    if v is None:
        return "—"
    if abs(v) >= 1e9:
        return f"{v/1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"{v/1e6:.2f}M"
    if abs(v) >= 1e3:
        return f"{v/1e3:.1f}k"
    return f"{v:,.2f}" if isinstance(v, float) else f"{v:,}"


def choropleth_overlay(
    name: str,
    features: List[Dict[str, Any]],
    value_prop: str,
    palette: str = "blues",
    classes: int = 5,
    value_label: Optional[str] = None,
    unit: str = "",
) -> Dict[str, Any]:
    """Build a choropleth overlay dict (per-feature ``_style`` + legend)."""
    palette = CHOROPLETH_PALETTES.get(palette, CHOROPLETH_PALETTES["blues"])
    values = [f.get("properties", {}).get(value_prop) for f in features]
    numeric = [v for v in values if isinstance(v, (int, float))]
    breaks = quantile_breaks(numeric, classes)
    colors = palette[-len(breaks) - 1 :] if breaks else [palette[-1]]

    def bucket(v: Any) -> int:
        if not isinstance(v, (int, float)):
            return 0
        idx = 0
        for b in breaks:
            if v >= b:
                idx += 1
        return min(idx, len(colors) - 1)

    styled = []
    for f in features:
        f = {**f, "properties": {**f.get("properties", {})}}
        color = colors[bucket(f["properties"].get(value_prop))]
        f["properties"]["_style"] = {
            "color": "#555555",
            "weight": 1,
            "fillColor": color,
            "fillOpacity": 0.75,
            "opacity": 0.9,
        }
        styled.append(f)

    legend = []
    if not breaks:
        label = _fmt_num(numeric[0]) if numeric else "no data"
        legend = [{"color": colors[-1], "label": f"{label} {unit}".strip()}]
    else:
        edges = [None] + breaks + [None]
        for i, color in enumerate(colors):
            lo = edges[i] if i < len(edges) else None
            hi = edges[i + 1] if i + 1 < len(edges) else None
            if lo is None and hi is not None:
                label = f"< {_fmt_num(hi)}"
            elif lo is not None and hi is not None:
                label = f"{_fmt_num(lo)} – {_fmt_num(hi)}"
            elif lo is not None:
                label = f"≥ {_fmt_num(lo)}"
            else:
                label = "—"
            legend.append({"color": color, "label": f"{label} {unit}".strip()})

    return {
        "name": name,
        "geojson": feature_collection(styled),
        "choropleth": True,
        "valueProp": value_prop,
        "valueLabel": value_label or value_prop,
        "legend": legend,
    }


# ============================================================
# ROUTING  (on foot / bicycle / motor car — best + alternative routes)
# ============================================================

ROUTE_CONFIG: Dict[str, Any] = {
    "default_mode": "drive",
    "modes": ["walk", "bike", "drive"],
    "max_alternatives": 4,
    "snap_m": 800.0,
    "grid_spacing_m": 900.0,
    "arterial_every": 3,
    "traffic_factor": 1.25,                     # peak-hour multiplier for driving
    "speed_fallback_kmh": {"walk": 4.8, "bike": 15.0, "drive": 45.0},
}

# mode -> {label, icon, description}
TRAVEL_MODES: Dict[str, Dict[str, str]] = {
    "walk": {"label": "On foot", "icon": "🚶",
             "description": "Pedestrian routing along footpaths and streets."},
    "bike": {"label": "By bicycle", "icon": "🚲",
             "description": "Cycling routing; motorways excluded."},
    "drive": {"label": "By motor car", "icon": "🚗",
              "description": "Driving routing with class speeds and a traffic factor."},
}

# road_class -> per-mode speed (km/h); 0 means the mode may not use that class.
ROAD_CLASSES: Dict[str, Dict[str, Any]] = {
    "motorway":    {"label": "Motorway",         "drive": 95.0, "bike": 0.0,  "walk": 0.0, "one_way": True},
    "arterial":    {"label": "Main road",        "drive": 55.0, "bike": 17.0, "walk": 4.8, "one_way": False},
    "secondary":   {"label": "Secondary road",   "drive": 42.0, "bike": 16.0, "walk": 4.8, "one_way": False},
    "local":       {"label": "Local street",     "drive": 30.0, "bike": 14.0, "walk": 4.8, "one_way": False},
    "residential": {"label": "Residential street", "drive": 28.0, "bike": 14.0, "walk": 4.8, "one_way": False},
    "service":     {"label": "Service road",     "drive": 18.0, "bike": 12.0, "walk": 4.5, "one_way": False},
    "footpath":    {"label": "Footpath",         "drive": 0.0,  "bike": 8.0,  "walk": 5.2, "one_way": False},
    "steps":       {"label": "Steps",            "drive": 0.0,  "bike": 0.0,  "walk": 2.5, "one_way": False},
    "track":       {"label": "Track",            "drive": 15.0, "bike": 10.0, "walk": 4.0, "one_way": False},
}


def travel_modes() -> List[Dict[str, Any]]:
    return [{"mode": k, **v} for k, v in TRAVEL_MODES.items()]


def road_classes() -> List[Dict[str, Any]]:
    return [{"road_class": k, **v} for k, v in ROAD_CLASSES.items()]


def edge_speed_kmh(road_class: str, mode: str) -> float:
    spec = ROAD_CLASSES.get(road_class) or ROAD_CLASSES["local"]
    speed = float(spec.get(mode, 0.0) or 0.0)
    if speed <= 0.0:
        return 0.0
    return speed


def edge_time_s(distance_m: float, road_class: str, mode: str, traffic_factor: float = 1.0) -> float:
    """Travel time along an edge for a mode, or ``inf`` when the mode is barred."""
    speed = edge_speed_kmh(road_class, mode)
    if speed <= 0.0:
        return math.inf
    traffic = traffic_factor if mode == "drive" else 1.0
    return (distance_m / 1000.0) / speed * 3600.0 * traffic


def format_duration(seconds: float) -> str:
    if seconds is None or math.isinf(seconds):
        return "—"
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min" + (f" {sec} s" if sec else "")
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min"


def _compass(bearing: float) -> str:
    dirs = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]
    return dirs[int(((bearing % 360) + 22.5) // 45) % 8]


# ---- network ----


class RoadNetwork:
    """A routable graph: nodes (``id -> [lat, lon]``) and directed edges with a class."""

    def __init__(self, name: str = "network", source: str = "custom") -> None:
        self.name = name
        self.source = source
        self.nodes: Dict[str, List[float]] = {}
        self.adj: Dict[str, List[Dict[str, Any]]] = {}
        self.ways: List[Dict[str, Any]] = []

    def add_node(self, node_id: str, lat: float, lon: float) -> str:
        self.nodes.setdefault(node_id, [float(lat), float(lon)])
        self.adj.setdefault(node_id, [])
        return node_id

    def add_edge(self, a: str, b: str, road_class: str = "local", one_way: bool = False,
                 name: Optional[str] = None) -> None:
        if a not in self.nodes or b not in self.nodes or a == b:
            return
        lat1, lon1 = self.nodes[a]
        lat2, lon2 = self.nodes[b]
        dist = haversine_m(lat1, lon1, lat2, lon2)
        self.adj[a].append({"to": b, "road_class": road_class, "distance_m": round(dist, 1),
                            "name": name, "one_way": one_way})
        self.adj[b].append({"to": a, "road_class": road_class, "distance_m": round(dist, 1),
                            "name": name, "one_way": one_way})

    def info(self) -> Dict[str, Any]:
        edges = sum(len(v) for v in self.adj.values()) // 2
        return {"name": self.name, "source": self.source, "nodes": len(self.nodes), "edges": edges}


def build_grid_network(south: float, west: float, north: float, east: float,
                       spacing_m: Optional[float] = None, arterial_every: Optional[int] = None,
                       name: str = "synthetic-grid") -> RoadNetwork:
    """Build a synthetic street grid over a bounding box.

    Every ``arterial_every``-th row/column is a faster *arterial*; the rest are
    *local* streets. The grid is symmetric (two-way), so distinct *routes* between
    two points genuinely differ (e.g. north-then-east vs east-then-north).
    """
    spacing = float(spacing_m or ROUTE_CONFIG["grid_spacing_m"])
    every = int(arterial_every or ROUTE_CONFIG["arterial_every"])
    net = RoadNetwork(name=name, source="grid")
    lat_step = spacing / 111320.0
    mid_lat = (south + north) / 2.0
    lon_step = spacing / (111320.0 * max(0.15, math.cos(math.radians(mid_lat))))
    rows = max(1, int((north - south) / lat_step)) + 1
    cols = max(1, int((east - west) / lon_step)) + 1
    for r in range(rows):
        for c in range(cols):
            net.add_node(f"g{r}_{c}", south + r * lat_step, west + c * lon_step)
    for r in range(rows):
        for c in range(cols):
            if c + 1 < cols:
                cls = "arterial" if r % every == 0 else "local"
                net.add_edge(f"g{r}_{c}", f"g{r}_{c + 1}", road_class=cls)
            if r + 1 < rows:
                cls = "arterial" if c % every == 0 else "local"
                net.add_edge(f"g{r}_{c}", f"g{r + 1}_{c}", road_class=cls)
    net.ways = [{"kind": "grid", "spacing_m": spacing, "arterial_every": every,
                 "bbox": {"south": south, "west": west, "north": north, "east": east}}]
    return net


def network_from_ways(ways: List[Dict[str, Any]], name: str = "custom") -> RoadNetwork:
    """Build a network from explicit ``ways`` (polylines).

    Each way is ``{coordinates: [[lat, lon], ...], road_class?: str, name?: str,
    one_way?: bool}``; consecutive points become edges.
    """
    net = RoadNetwork(name=name, source="ways")
    for w in ways or []:
        coords = w.get("coordinates") or []
        road_class = w.get("road_class", "local")
        one_way = bool(w.get("one_way", ROAD_CLASSES.get(road_class, {}).get("one_way", False)))
        way_name = w.get("name")
        ids = []
        for lat, lon in coords:
            nid = f"w{len(net.nodes)}_{round(lat, 5)}_{round(lon, 5)}"
            net.add_node(nid, lat, lon)
            ids.append(nid)
        for a, b in zip(ids, ids[1:]):
            net.add_edge(a, b, road_class=road_class, one_way=one_way, name=way_name)
        net.ways.append({"kind": "way", "name": way_name, "road_class": road_class,
                         "points": len(coords)})
    return net


def snap_node(network: RoadNetwork, lat: float, lon: float) -> Tuple[Optional[str], float]:
    """Nearest graph node to a coordinate, and the offset distance (m)."""
    best_id, best_d = None, math.inf
    for nid, (nlat, nlon) in network.nodes.items():
        d = haversine_m(lat, lon, nlat, nlon)
        if d < best_d:
            best_id, best_d = nid, d
    return best_id, (0.0 if best_id is None else round(best_d, 1))


# ---- shortest paths ----


def _dijkstra(network: RoadNetwork, start: str, end: str, mode: str,
              traffic_factor: float, blocked: frozenset = frozenset()) -> Optional[List[str]]:
    if start not in network.nodes or end not in network.nodes:
        return None
    dist: Dict[str, float] = {start: 0.0}
    prev: Dict[str, str] = {}
    pq: List[Tuple[float, str]] = [(0.0, start)]
    seen: set = set()
    while pq:
        d, node = heapq.heappop(pq)
        if node in seen:
            continue
        seen.add(node)
        if node == end:
            break
        for edge in network.adj.get(node, []):
            if (node, edge["to"]) in blocked:
                continue
            tt = edge_time_s(edge["distance_m"], edge["road_class"], mode, traffic_factor)
            if math.isinf(tt):
                continue
            nd = d + tt
            if nd < dist.get(edge["to"], math.inf):
                dist[edge["to"]] = nd
                prev[edge["to"]] = node
                heapq.heappush(pq, (nd, edge["to"]))
    if end not in dist:
        return None
    path = [end]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    return path


def _path_metrics(network: RoadNetwork, path: List[str], mode: str,
                  traffic_factor: float) -> Dict[str, Any]:
    distance = 0.0
    duration = 0.0
    classes: Dict[str, float] = {}
    for a, b in zip(path, path[1:]):
        for edge in network.adj.get(a, []):
            if edge["to"] == b:
                tt = edge_time_s(edge["distance_m"], edge["road_class"], mode, traffic_factor)
                if math.isinf(tt):
                    continue
                distance += edge["distance_m"]
                duration += tt
                classes[edge["road_class"]] = classes.get(edge["road_class"], 0.0) + edge["distance_m"]
                break
    return {"distance_m": round(distance, 1), "duration_s": round(duration, 1),
            "by_road_class": {k: round(v, 1) for k, v in classes.items()}}


def _k_shortest(network: RoadNetwork, start: str, end: str, mode: str,
                traffic_factor: float, k: int) -> List[List[str]]:
    """Yen's loopless k-shortest paths (by travel time)."""
    first = _dijkstra(network, start, end, mode, traffic_factor)
    if not first:
        return []
    A: List[List[str]] = [first]
    B: List[Tuple[float, List[str]]] = []
    for _ in range(1, max(1, k)):
        prev_path = A[-1]
        for i in range(len(prev_path) - 1):
            spur_node = prev_path[i]
            root = prev_path[: i + 1]
            blocked = set()
            for p in A:
                if len(p) > i and p[: i + 1] == root:
                    blocked.add((p[i], p[i + 1]))
            spur = _dijkstra(network, spur_node, end, mode, traffic_factor, frozenset(blocked))
            if not spur:
                continue
            total = root[:-1] + spur
            if total in A or any(total == p for _, p in B):
                continue
            metrics = _path_metrics(network, total, mode, traffic_factor)
            B.append((metrics["duration_s"], total))
        if not B:
            break
        B.sort(key=lambda t: t[0])
        A.append(B.pop(0)[1])
    return A


def _path_geometry(network: RoadNetwork, path: List[str]) -> List[List[float]]:
    return [list(network.nodes[n]) for n in path if n in network.nodes]


def _steps(network: RoadNetwork, path: List[str], mode: str, destination_label: str = "destination") -> List[Dict[str, Any]]:
    geom = _path_geometry(network, path)
    if len(geom) < 2:
        return []
    steps: List[Dict[str, Any]] = []
    leg_start = 0
    leg_class = _edge_class(network, path, 0)
    leg_distance = 0.0
    for i in range(len(geom) - 1):
        leg_distance += haversine_m(geom[i][0], geom[i][1], geom[i + 1][0], geom[i + 1][1])
        is_last = i == len(geom) - 2
        turn = None
        if not is_last:
            b1 = bearing_deg(geom[i - 1][0], geom[i - 1][1], geom[i][0], geom[i][1]) if i > 0 else \
                bearing_deg(geom[i][0], geom[i][1], geom[i + 1][0], geom[i + 1][1])
            b2 = bearing_deg(geom[i][0], geom[i][1], geom[i + 1][0], geom[i + 1][1])
            delta = (b2 - b1 + 540) % 360 - 180
            if abs(delta) > 30:
                turn = "right" if delta > 0 else "left"
        if turn or is_last:
            heading = bearing_deg(geom[leg_start][0], geom[leg_start][1],
                                  geom[leg_start + 1][0], geom[leg_start + 1][1]) if leg_start + 1 < len(geom) else 0.0
            steps.append({
                "instruction": (f"Turn {turn} onto {ROAD_CLASSES.get(leg_class, {}).get('label', leg_class)}"
                                if not is_last else f"Arrive at {destination_label}"),
                "heading": _compass(heading),
                "road_class": leg_class,
                "distance_m": round(leg_distance, 1),
            })
            leg_start = i + 1
            leg_distance = 0.0
            leg_class = _edge_class(network, path, min(i + 1, len(path) - 2))
    if steps:
        steps[0]["instruction"] = f"Head {steps[0]['heading']} on " \
                                  f"{ROAD_CLASSES.get(steps[0]['road_class'], {}).get('label', steps[0]['road_class'])}"
    return steps


def _edge_class(network: RoadNetwork, path: List[str], idx: int) -> str:
    if idx + 1 >= len(path):
        return "local"
    a, b = path[idx], path[idx + 1]
    for edge in network.adj.get(a, []):
        if edge["to"] == b:
            return edge["road_class"]
    return "local"


def _route_dict(network: RoadNetwork, path: List[str], mode: str, traffic_factor: float,
                label: str, destination_label: str) -> Dict[str, Any]:
    metrics = _path_metrics(network, path, mode, traffic_factor)
    return {
        "label": label,
        "mode": mode,
        "mode_label": TRAVEL_MODES.get(mode, {}).get("label", mode),
        "distance_m": metrics["distance_m"],
        "distance_km": round(metrics["distance_m"] / 1000.0, 3),
        "duration_s": metrics["duration_s"],
        "duration_min": round(metrics["duration_s"] / 60.0, 1),
        "duration_text": format_duration(metrics["duration_s"]),
        "average_speed_kmh": round((metrics["distance_m"] / 1000.0) / (metrics["duration_s"] / 3600.0), 1)
        if metrics["duration_s"] else 0.0,
        "geometry": _path_geometry(network, path),
        "steps": _steps(network, path, mode, destination_label),
        "by_road_class": metrics["by_road_class"],
    }


def route(network: RoadNetwork, origin: Tuple[float, float], destination: Tuple[float, float],
          mode: Optional[str] = None, alternatives: int = 2,
          traffic_factor: Optional[float] = None,
          origin_label: str = "origin", destination_label: str = "destination") -> Dict[str, Any]:
    """Compute the best route plus up to ``alternatives`` additional distinct routes.

    ``origin`` / ``destination`` are ``(lat, lon)`` pairs. Modes: ``walk`` (on foot),
    ``bike`` and ``drive`` (motor car).
    """
    mode = (mode or ROUTE_CONFIG["default_mode"]).lower()
    if mode not in TRAVEL_MODES:
        return {"error": f"mode must be one of {list(TRAVEL_MODES)}"}
    traffic = float(ROUTE_CONFIG["traffic_factor"] if traffic_factor is None else traffic_factor)
    k = max(1, min(int(alternatives) + 1, int(ROUTE_CONFIG["max_alternatives"]) + 1))

    start, start_off = snap_node(network, origin[0], origin[1])
    end, end_off = snap_node(network, destination[0], destination[1])
    if not start or not end:
        return {"error": "Road network has no nodes to snap to"}
    if start == end:
        direct = haversine_m(origin[0], origin[1], destination[0], destination[1])
        tt = edge_time_s(direct, "local", mode, traffic)
        return {"mode": mode, "mode_label": TRAVEL_MODES[mode]["label"],
                "best": {"label": "Direct", "mode": mode, "distance_m": round(direct, 1),
                         "distance_km": round(direct / 1000.0, 3), "duration_s": round(tt, 1),
                         "duration_min": round(tt / 60.0, 1), "duration_text": format_duration(tt),
                         "geometry": [list(origin), list(destination)], "steps": []},
                "alternatives": [], "network": network.info()}

    path = _dijkstra(network, start, end, mode, traffic)
    if not path:
        return {"error": f"No {mode} route found — the network may not connect these points",
                "mode": mode, "network": network.info()}

    paths = _k_shortest(network, start, end, mode, traffic, k)
    # trim to genuinely distinct geometries
    distinct: List[List[str]] = []
    for p in paths:
        geo = _path_geometry(network, p)
        if all(_geometry_difference(geo, _path_geometry(network, q)) > 60.0 for q in distinct):
            distinct.append(p)
    if not distinct:
        distinct = [path]

    best = _route_dict(network, distinct[0], mode, traffic, "Best route", destination_label)
    alts = []
    for i, p in enumerate(distinct[1:], start=1):
        r = _route_dict(network, p, mode, traffic, f"Alternative {i}", destination_label)
        r["vs_best"] = {
            "extra_distance_m": round(r["distance_m"] - best["distance_m"], 1),
            "extra_duration_min": round((r["duration_s"] - best["duration_s"]) / 60.0, 1),
        }
        alts.append(r)

    return {
        "mode": mode,
        "mode_label": TRAVEL_MODES[mode]["label"],
        "traffic_factor": traffic if mode == "drive" else None,
        "origin": {"latitude": origin[0], "longitude": origin[1], "label": origin_label,
                   "snap_distance_m": start_off},
        "destination": {"latitude": destination[0], "longitude": destination[1],
                        "label": destination_label, "snap_distance_m": end_off},
        "best": best,
        "alternatives": alts,
        "alternative_count": len(alts),
        "network": network.info(),
    }


def _geometry_difference(a: List[List[float]], b: List[List[float]]) -> float:
    """Rough difference between two polylines: mean distance of A's points to B."""
    if not a or not b:
        return math.inf
    total = 0.0
    for lat, lon in a:
        total += min(haversine_m(lat, lon, bl, bo) for bl, bo in b)
    return total / len(a)


def compare_modes(network: RoadNetwork, origin: Tuple[float, float], destination: Tuple[float, float],
                  modes: Optional[List[str]] = None,
                  alternatives: int = 1) -> Dict[str, Any]:
    """Best distance/time for each travel mode between two points."""
    out: Dict[str, Any] = {}
    for mode in (modes or list(TRAVEL_MODES)):
        if mode not in TRAVEL_MODES:
            continue
        r = route(network, origin, destination, mode=mode, alternatives=alternatives)
        if "error" in r:
            out[mode] = {"error": r["error"]}
            continue
        b = r["best"]
        out[mode] = {"mode_label": r["mode_label"], "distance_m": b["distance_m"],
                     "distance_km": b["distance_km"], "duration_s": b["duration_s"],
                     "duration_min": b["duration_min"], "duration_text": b["duration_text"],
                     "average_speed_kmh": b["average_speed_kmh"],
                     "by_road_class": b["by_road_class"]}
    if out:
        fastest = min((m for m in out if "duration_s" in out[m]), key=lambda m: out[m]["duration_s"], default=None)
        for m, row in out.items():
            row["fastest"] = (m == fastest)
    return {"origin": list(origin), "destination": list(destination), "modes": out}


def route_overlays(routes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Turn route dicts into Leaflet overlays (LineString GeoJSON) for the map builder."""
    styles = [
        {"color": "#1f6feb", "weight": 6, "opacity": 0.9},
        {"color": "#0ea5e9", "weight": 4, "opacity": 0.75, "dashArray": "8 6"},
        {"color": "#a855f7", "weight": 4, "opacity": 0.65, "dashArray": "4 6"},
        {"color": "#f97316", "weight": 4, "opacity": 0.6, "dashArray": "2 6"},
    ]
    overlays = []
    # draw alternatives first so the best route renders on top
    ordered = list(routes[1:]) + [routes[0]] if routes else []
    for i, r in enumerate(ordered):
        geom = r.get("geometry") or []
        if len(geom) < 2:
            continue
        feature = {
            "type": "Feature",
            "properties": {"name": r.get("label", "route"),
                           "description": f"{r.get('distance_km')} km · {r.get('duration_text')}"},
            "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in geom]},
        }
        style = styles[i % len(styles)]
        overlays.append({"name": f"{r.get('label', 'Route')} ({r.get('distance_km')} km, {r.get('duration_text')})",
                         "geojson": {"type": "FeatureCollection", "features": [feature]},
                         "style": style})
    return overlays


# ============================================================
# REPORT BUILDER  (printable HTML)
# ============================================================

_REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="__LANG__" dir="__DIR__">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__</title>
  __THEME_STYLE__
  <style>
    * { box-sizing: border-box; }
    body { margin:0; background:var(--bg); color:var(--ink);
           font:14px/1.55 __FONT_STACK__; }
    .wrap { max-width: 1180px; margin: 0 auto; padding: 28px 22px 60px; }
    header { border-bottom:3px solid var(--accent); padding-bottom:14px; margin-bottom:22px; }
    h1 { margin:0 0 4px; font-size:26px; }
    .sub { color:var(--muted); }
    .meta { color:var(--muted); font-size:12px; margin-top:6px; }
    .ctrlbar { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:12px 0 2px; }
    .ctrlbar .grow { flex:1 1 auto; }
    .ctrbtn { font:inherit; color:var(--ink); background:var(--surface); border:1px solid var(--line);
              border-radius:6px; padding:3px 10px; cursor:pointer; }
    .langlink { color:var(--ink); text-decoration:none; padding:2px 9px; border-radius:6px; border:1px solid var(--line); }
    .langlink.active { background:var(--pill-bg); color:var(--pill-ink); border-color:transparent; font-weight:600; }
    section { background:var(--surface); border:1px solid var(--line); border-radius:10px;
              padding:18px 20px; margin-bottom:18px; }
    h2 { font-size:16px; margin:0 0 12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
    .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; }
    .card { border:1px solid var(--line); border-radius:8px; padding:12px 14px; background:var(--surface-2); }
    .card .lbl { font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
    .card .val { font-size:20px; font-weight:600; margin-top:4px; }
    .card .sub { font-size:11px; color:var(--muted); }
    table { width:100%; border-collapse:collapse; }
    th, td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); }
    th { font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); background:var(--surface-2); }
    td.num, th.num { text-align:right; font-variant-numeric: tabular-nums; }
    html[dir="rtl"] th, html[dir="rtl"] td { text-align:right; }
    html[dir="rtl"] td.num, html[dir="rtl"] th.num { text-align:left; }
    .kv { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:6px 22px; }
    .kv div { display:flex; justify-content:space-between; gap:16px;
              border-bottom:1px dashed var(--line); padding:6px 0; }
    .kv span:last-child { font-weight:600; font-variant-numeric: tabular-nums; }
    iframe.map { width:100%; height:460px; border:1px solid var(--line); border-radius:8px; background:var(--surface-2); }
    .pill { display:inline-block; background:var(--pill-bg); color:var(--pill-ink); border-radius:999px;
            padding:2px 10px; font-size:12px; margin:0 6px 6px 0; }
    .badge { display:inline-block; border-radius:4px; padding:1px 8px; font-size:11px; font-weight:600; }
    .badge.pos { background:var(--ok-bg); color:var(--ok-ink); }
    .badge.neg { background:var(--bad-bg); color:var(--bad-ink); }
    .badge.neu { background:var(--neu-bg); color:var(--neu-ink); }
    .big { font-size:15px; font-weight:600; }
    footer { color:var(--muted); font-size:12px; text-align:center; margin-top:26px; }
    @media print { body { background:#fff; color:#000; } section { break-inside: avoid; } .ctrlbar { display:none; } }
  </style>
</head>
<body>
__TICKER__
<div class="wrap">
  <header>
    <h1>__TITLE__</h1>
    <div class="sub">__SUBTITLE__</div>
    <div class="ctrlbar">
      <span class="grow"></span>
      <span>__LANG_LINKS__</span>
      <button class="ctrbtn" type="button" title="__THEME_LABEL__" data-theme-cycle
              data-auto="__THEME_AUTO__" data-light="__THEME_LIGHT__" data-dark="__THEME_DARK__">&#9680;
        <span id="themeName">__THEME_CURRENT__</span></button>
    </div>
    <div class="meta">__GENERATED_LABEL__ __GENERATED__ · __SITE__ GIS</div>
  </header>
  __BODY__
  <footer>__FOOTER__</footer>
</div>
__THEME_JS__
<script>
  document.querySelectorAll('[data-theme-cycle]').forEach(function (b) {
    b.addEventListener('click', function () {
      var t = window.portalTheme.cycle();
      var el = document.getElementById('themeName');
      if (el) el.textContent = b.dataset[t] || t;
    });
  });
  document.querySelectorAll('.langlink').forEach(function (a) {
    a.addEventListener('click', function (e) {
      e.preventDefault();
      try {
        var u = new URL(window.location.href);
        u.searchParams.set('lang', a.dataset.lang);
        window.location.href = u.toString();
      } catch (err) { window.location.search = '?lang=' + a.dataset.lang; }
    });
  });
</script>
</body>
</html>"""


def _render_card(label: str, value: str, sub: str = "") -> str:
    sub_html = f'<div class="sub">{html.escape(sub)}</div>' if sub else ""
    return (
        f'<div class="card"><div class="lbl">{html.escape(label)}</div>'
        f'<div class="val">{html.escape(str(value))}</div>{sub_html}</div>'
    )


def render_section(section: Dict[str, Any], lang: str = DEFAULT_LANGUAGE) -> str:
    kind = section.get("kind", "kv")
    heading = html.escape(translate(section.get("heading", ""), lang))
    body = ""

    if kind == "cards":
        cards = []
        for item in section.get("items", []):
            label = translate(item[0], lang)
            value = item[1] if len(item) > 1 else ""
            sub = item[2] if len(item) > 2 else ""
            cards.append(_render_card(label, value, sub))
        body = '<div class="cards">' + "".join(cards) + "</div>"
    elif kind == "kv":
        body = '<div class="kv">' + "".join(
            f"<div><span>{html.escape(translate(k, lang))}</span><span>{html.escape(str(v))}</span></div>"
            for k, v in section.get("items", [])
        ) + "</div>"
    elif kind == "table":
        cols = section.get("columns", [])
        numeric = section.get("numeric", [])
        head = "".join(
            f'<th class="{"num" if c in numeric else ""}">{html.escape(translate(c, lang))}</th>' for c in cols
        )
        rows = ""
        for row in section.get("rows", []):
            cells = "".join(
                f'<td class="{"num" if cols[i] in numeric else ""}">{html.escape(str(row[i]))}</td>'
                for i in range(len(cols))
            )
            rows += f"<tr>{cells}</tr>"
        body = f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"
    elif kind == "text":
        body = f"<p>{html.escape(translate(section.get('text', ''), lang))}</p>"
    elif kind == "pills":
        body = "".join(
            f'<span class="pill">{html.escape(translate(str(p), lang))}</span>' for p in section.get("items", [])
        )
    elif kind == "news":
        rows = ""
        for item in section.get("items", []):
            sent = item.get("sentiment", "neutral")
            cls = {"positive": "pos", "negative": "neg"}.get(sent, "neu")
            title = html.escape(str(item.get("title", "")))
            if item.get("url"):
                title = f'<a href="{html.escape(str(item["url"]), quote=True)}" target="_blank" rel="noopener">{title}</a>'
            src = html.escape(str(item.get("source", "")))
            when = html.escape(str(item.get("published_at", ""))[:16].replace("T", " "))
            impact = item.get("impact_score", 0)
            rows += (
                f'<tr><td>{title}<div class="sub" style="color:var(--muted);font-size:11px">'
                f'{src} · {when} · {html.escape(str(item.get("category", "")))}</div></td>'
                f'<td class="num"><span class="badge {cls}">{html.escape(translate(sent, lang))}</span></td>'
                f'<td class="num">{impact:+.0f}</td></tr>'
            )
        body = (
            f"<table><thead><tr><th>{html.escape(translate('Headline', lang))}</th>"
            f"<th class='num'>{html.escape(translate('Sentiment', lang))}</th>"
            f"<th class='num'>{html.escape(translate('Impact', lang))}</th></tr></thead><tbody>{rows}</tbody></table>"
        )
    elif kind == "html":
        body = section.get("html", "")
    elif kind == "ads":
        return render_ad_section(section, lang)

    return f"<section><h2>{heading}</h2>{body}</section>"


def build_report_html(
    title: str,
    subtitle: str = "",
    sections: Optional[List[Dict[str, Any]]] = None,
    map_html: Optional[str] = None,
    generated_at: Optional[str] = None,
    ticker_html: str = "",
    lang: str = DEFAULT_LANGUAGE,
    theme: str = DEFAULT_THEME,
) -> str:
    """Return a printable HTML report; an optional map is embedded in an iframe.

    ``lang`` localises headings, labels and the report chrome (RTL supported) and
    ``theme`` chooses the light/dark token set; a switcher is rendered in the header.
    """
    language = get_language(lang)
    code = language["code"]
    parts = []
    if map_html:
        parts.append(
            f'<section><h2>{html.escape(translate("Map", code))}</h2>'
            f'<iframe class="map" srcdoc="{html.escape(map_html, quote=True)}"></iframe></section>'
        )
    for section in sections or []:
        parts.append(render_section(section, code))
    return (
        _REPORT_TEMPLATE.replace("__LANG__", code)
        .replace("__DIR__", language["dir"])
        .replace("__FONT_STACK__", language["font_stack"])
        .replace("__THEME_STYLE__", theme_style(theme))
        .replace("__THEME_JS__", THEME_JS)
        .replace("__TITLE__", html.escape(str(title)))
        .replace("__SUBTITLE__", html.escape(str(subtitle)))
        .replace("__TICKER__", ticker_html or "")
        .replace("__LANG_LINKS__", lang_links_html(code))
        .replace("__THEME_LABEL__", html.escape(translate("Theme", code)))
        .replace("__THEME_AUTO__", html.escape(translate("Auto", code)))
        .replace("__THEME_LIGHT__", html.escape(translate("Light", code)))
        .replace("__THEME_DARK__", html.escape(translate("Dark", code)))
        .replace("__THEME_CURRENT__", html.escape(translate(normalize_theme(theme).capitalize()
                                                          if normalize_theme(theme) != "auto" else "Auto", code)))
        .replace("__GENERATED_LABEL__", html.escape(translate("Generated", code)))
        .replace("__SITE__", html.escape(translate("Real Estate Portal", code)))
        .replace("__GENERATED__", html.escape(str(generated_at or datetime.now().isoformat(timespec="seconds"))))
        .replace("__FOOTER__", html.escape(translate("Real Estate Portal — GIS analysis report", code)))
        .replace("__BODY__", "".join(parts))
    )


# ============================================================
# NEWS TICKER  (self-contained, embeddable fragment)
# ============================================================

_TICKER_TEMPLATE = """<style>
.portal-ticker { display:flex; align-items:stretch; background:var(--ticker-bg, #0f172a);
  color:var(--ticker-ink, #e2e8f0); font:13px/1.4 "Segoe UI", system-ui, sans-serif;
  overflow:hidden; border-bottom:1px solid var(--ticker-line, #1e293b); }
.portal-ticker .tk-label { flex:0 0 auto; display:flex; align-items:center;
  background:var(--ticker-label-bg, #b91c1c); color:var(--ticker-label-ink, #ffffff);
  font-weight:700; padding:0 14px; text-transform:uppercase; letter-spacing:.07em; font-size:11px; }
.portal-ticker .tk-label::before { content:""; width:8px; height:8px; border-radius:50%;
  background:currentColor; margin-right:8px; animation: tk-pulse 1.4s infinite; }
.portal-ticker .tk-viewport { flex:1 1 auto; overflow:hidden; }
.portal-ticker .tk-track { display:inline-flex; white-space:nowrap; padding:9px 0;
  animation-name: portal-ticker-scroll; animation-timing-function:linear; animation-iteration-count:infinite; }
.portal-ticker:hover .tk-track { animation-play-state:paused; }
.portal-ticker .tk-item { display:inline-block; padding:0 22px; border-right:1px solid var(--ticker-line, #1e293b); }
.portal-ticker .tk-src { color:var(--ticker-src, #94a3b8); font-size:11px; margin-inline-start:6px; }
.portal-ticker .tk-pos { color:var(--tk-pos, #4ade80); }
.portal-ticker .tk-neg { color:var(--tk-neg, #f87171); }
.portal-ticker .tk-neu { color:var(--tk-neu, #e2e8f0); }
@keyframes portal-ticker-scroll { from { transform: translateX(0); } to { transform: translateX(-50%); } }
@keyframes tk-pulse { 0%,100% { opacity:1; } 50% { opacity:.25; } }
@media (prefers-reduced-motion: reduce) { .portal-ticker .tk-track { animation:none; } }
</style>
<div class="portal-ticker" role="marquee" aria-label="__LABEL__" dir="__DIR__">
  <span class="tk-label">__LABEL__</span>
  <div class="tk-viewport"><div class="tk-track" style="animation-duration:__SPEED__s">__ITEMS__</div></div>
</div>"""


def build_ticker_html(
    items: List[Dict[str, Any]],
    label: str = "Real Estate News",
    speed_seconds: float = 70.0,
    lang: str = DEFAULT_LANGUAGE,
) -> str:
    """Build a self-contained scrolling news-ticker HTML fragment.

    Each item may provide ``title``, ``source``, ``url``, ``sentiment``
    (positive/neutral/negative) and ``impact_score``. Colours come from the
    ``--ticker-*`` theme tokens when the host page defines them (see
    :func:`theme_style`) and fall back to dark defaults otherwise, so the fragment
    works both standalone and embedded in a themed map or report.
    """
    if not items:
        return ""
    language = get_language(lang)
    rows = []
    for item in items:
        sent = item.get("sentiment", "neutral")
        cls = {"positive": "tk-pos", "negative": "tk-neg"}.get(sent, "tk-neu")
        arrow = {"positive": "▲", "negative": "▼"}.get(sent, "•")
        title = html.escape(str(item.get("title", "")))
        if item.get("url"):
            title = f'<a href="{html.escape(str(item["url"]), quote=True)}" target="_blank" rel="noopener" style="color:inherit;text-decoration:none">{title}</a>'
        src = f'<span class="tk-src">— {html.escape(str(item.get("source", "")))}</span>' if item.get("source") else ""
        rows.append(f'<span class="tk-item {cls}">{arrow} {title}{src}</span>')
    body = "".join(rows)
    # duplicate so translateX(-50%) loops seamlessly
    return (
        _TICKER_TEMPLATE.replace("__LABEL__", html.escape(translate(label, language["code"])))
        .replace("__DIR__", language["dir"])
        .replace("__SPEED__", f"{max(10.0, float(speed_seconds)):g}")
        .replace("__ITEMS__", body + body)
    )


# ============================================================
# PORTAL PAGE  (content + advertisement sections)
# ============================================================


def _ad_card_html(ad: Dict[str, Any], lang: str = DEFAULT_LANGUAGE) -> str:
    """One advertisement creative card."""
    code = get_language(lang)["code"]
    badge = html.escape(str(ad.get("category_label") or ad.get("category") or "Sponsored"))
    advertiser = html.escape(str(ad.get("advertiser") or ""))
    sponsor = html.escape(translate("Sponsored", code))
    headline = html.escape(str(ad.get("headline") or ad.get("title") or ""))
    body = html.escape(str(ad.get("body") or ""))
    meta_bits = [b for b in (ad.get("price_text"), ad.get("phone"), ad.get("offer")) if b]
    meta = " · ".join(html.escape(str(b)) for b in meta_bits)
    ad_id = html.escape(str(ad.get("id") or ""))
    cta_label = html.escape(str(ad.get("cta_label") or translate("Learn more", code)))
    cta_url = ad.get("cta_url")
    if cta_url:
        cta = (f'<a class="ad-cta" data-ad-id="{ad_id}" data-ad-event="click" '
               f'href="{html.escape(str(cta_url), quote=True)}" target="_blank" rel="noopener">'
               f"{cta_label}</a>")
    else:
        cta = f'<span class="ad-cta" data-ad-id="{ad_id}">{cta_label}</span>'
    return (
        f'<div class="ad-card" data-ad-id="{ad_id}" data-ad-slot="{html.escape(str(ad.get("slot") or ""))}">'
        f'<div class="ad-top"><span class="ad-badge">{badge}</span>'
        f'<span class="ad-sponsor">{sponsor}{" · " + advertiser if advertiser else ""}</span></div>'
        f'<div class="ad-headline">{headline}</div>'
        + (f'<div class="ad-body">{body}</div>' if body else "")
        + (f'<div class="ad-meta">{meta}</div>' if meta else "")
        + f'<div class="ad-foot">{cta}</div></div>'
    )


def render_ad_section(section: Dict[str, Any], lang: str = DEFAULT_LANGUAGE) -> str:
    """An advertisement *section*: heading + a grid of creatives (or a house ad)."""
    code = get_language(lang)["code"]
    heading = section.get("heading") or section.get("slot_label") or section.get("slot") or "Sponsored"
    slot = str(section.get("slot") or "infeed")
    ads = section.get("ads") or []
    cards = [_ad_card_html(a, code) for a in ads]
    if not cards:
        house = (
            f'<div class="ad-card house-ad"><div class="ad-top">'
            f'<span class="ad-badge">{html.escape(translate("Advertise", code))}</span></div>'
            f'<div class="ad-headline">{html.escape(translate("Advertise here", code))}</div>'
            f'<div class="ad-body">{html.escape(translate(ADS_HOUSE_BODY, code))}</div>'
            f'<div class="ad-foot"><span class="ad-cta">{html.escape(translate("Get in touch", code))}</span></div></div>'
        )
        cards = [house]
    return (
        f'<section class="ad-section ad-slot-{html.escape(slot)}" data-ad-slot="{html.escape(slot)}">'
        f'<h2>{html.escape(translate(heading, code))}</h2>'
        f'<div class="ad-grid">{"".join(cards)}</div></section>'
    )


ADS_HOUSE_BODY = "Reach thousands of buyers, investors and developers across Pakistan."


def _render_timeline(block: Dict[str, Any], lang: str) -> str:
    code = get_language(lang)["code"]
    items = ""
    for h in block.get("items", []):
        when = str(h.get("year", ""))
        if h.get("month"):
            when = f"{when}-{int(h['month']):02d}"
        kind = html.escape(str(h.get("kind", "")))
        items += (
            f'<div class="tl-item"><div class="tl-when">{html.escape(when)}</div>'
            f'<div class="tl-body"><div class="tl-title">{html.escape(str(h.get("title", "")))}'
            f'<span class="tl-kind">{html.escape(translate(kind, code))}</span></div>'
            f'<div class="tl-desc">{html.escape(str(h.get("description", "")))}</div></div></div>'
        )
    return (
        f'<section><h2>{html.escape(translate(block.get("heading", "Our journey"), code))}</h2>'
        f'<div class="timeline">{items}</div></section>'
    )


def _render_stories(block: Dict[str, Any], lang: str) -> str:
    code = get_language(lang)["code"]
    cards = ""
    for s in block.get("items", []):
        metrics = "".join(
            f'<div><span>{html.escape(str(m.get("label", "")))}</span>'
            f'<span>{html.escape(str(m.get("value", "")))}</span></div>'
            for m in s.get("metrics", [])
        )
        quote = ""
        if s.get("quote"):
            stars = ""
            if s.get("rating"):
                stars = f'<div class="stars">{"★" * int(round(float(s["rating"])))}</div>'
            who = " · ".join(x for x in (s.get("client_name"), s.get("client_role")) if x)
            quote = (f'<blockquote class="story-quote">{html.escape(str(s["quote"]))}</blockquote>'
                     f'{stars}<div class="story-who">{html.escape(str(who))}</div>')
        narrative = "".join(f"<p>{html.escape(str(n))}</p>" for n in s.get("narrative", []))
        loc = html.escape(str(s.get("location") or ""))
        cards += (
            f'<article class="story"><div class="story-top">'
            f'<span class="ad-badge">{html.escape(translate(str(s.get("story_type", "")), code))}</span>'
            + (f'<span class="story-loc">{loc}</span>' if loc else "")
            + f'</div><h3>{html.escape(str(s.get("title", "")))}</h3>'
            + (f'<div class="kv story-metrics">{metrics}</div>' if metrics else "")
            + narrative + quote + "</article>"
        )
    return (
        f'<section><h2>{html.escape(translate(block.get("heading", "Success stories"), code))}</h2>'
        f'<div class="stories">{cards}</div></section>'
    )


def _render_contact(block: Dict[str, Any], lang: str) -> str:
    code = get_language(lang)["code"]
    cards = ""
    icon = {"phone": "☎", "helpline": "☎", "email": "✉", "whatsapp": "✆", "address": "⌂",
            "office": "⌂", "hours": "◷", "social": "◆", "website": "⌘", "chat": "✆"}
    for c in block.get("items", []):
        ctype = str(c.get("channel_type", ""))
        val = html.escape(str(c.get("value", "")))
        url = c.get("url")
        if url:
            val = f'<a href="{html.escape(str(url), quote=True)}" target="_blank" rel="noopener">{val}</a>'
        hours = f'<div class="sub">{html.escape(str(c["hours"]))}</div>' if c.get("hours") else ""
        cards += (
            f'<div class="contact-card {html.escape(ctype)}">'
            f'<div class="c-icon">{html.escape(icon.get(ctype, "•"))}</div>'
            f'<div class="c-label">{html.escape(translate(str(c.get("label", "")), code))}</div>'
            f'<div class="c-value">{val}</div>{hours}</div>'
        )
    return (
        f'<section><h2>{html.escape(translate(block.get("heading", "Contact us"), code))}</h2>'
        f'<div class="contact-grid">{cards}</div></section>'
    )


def _render_stats(block: Dict[str, Any], stats: Optional[List[Dict[str, Any]]], lang: str) -> str:
    code = get_language(lang)["code"]
    cards = [
        _render_card(translate(str(s.get("label", "")), code), str(s.get("value", "")), str(s.get("sub", "")))
        for s in (stats or [])
    ]
    return (
        f'<section><h2>{html.escape(translate(block.get("heading", "Portal at a glance"), code))}</h2>'
        f'<div class="cards">{"".join(cards)}</div></section>'
    )


def _render_page_block(block: Dict[str, Any], lang: str) -> str:
    code = get_language(lang)["code"]
    page = block.get("page", {})
    title = html.escape(translate(str(page.get("title", "")), code))
    subtitle = f'<div class="sub">{html.escape(str(page["subtitle"]))}</div>' if page.get("subtitle") else ""
    parts = []
    for p in page.get("body", []):
        parts.append(f"<p>{html.escape(str(p))}</p>")
    highlights = page.get("highlights") or []
    if highlights:
        cards = "".join(
            _render_card(translate(str(h.get("label", "")), code), str(h.get("value", "")), str(h.get("sub", "")))
            for h in highlights
        )
        parts.append(f'<div class="cards">{cards}</div>')
    bullets = page.get("bullets") or []
    if bullets:
        parts.append('<ul class="bullets">' + "".join(f"<li>{html.escape(str(b))}</li>" for b in bullets) + "</ul>")
    faqs = page.get("faqs") or []
    if faqs:
        parts.append('<div class="faqs">' + "".join(
            f'<details><summary>{html.escape(str(f.get("question", "")))}</summary>'
            f'<div>{html.escape(str(f.get("answer", "")))}</div></details>'
            for f in faqs
        ) + "</div>")
    key = html.escape(str(page.get("key", "")))
    return f'<section id="{key}"><h2>{title}</h2>{subtitle}{"".join(parts)}</section>'


def render_portal_block(block: Dict[str, Any], lang: str = DEFAULT_LANGUAGE,
                        stats: Optional[List[Dict[str, Any]]] = None) -> str:
    kind = block.get("kind")
    if kind == "ads":
        return render_ad_section(block, lang)
    if kind == "timeline":
        return _render_timeline(block, lang)
    if kind == "stories":
        return _render_stories(block, lang)
    if kind == "contact":
        return _render_contact(block, lang)
    if kind == "stats":
        return _render_stats(block, stats, lang)
    if kind == "page":
        return _render_page_block(block, lang)
    return ""


def build_portal_html(
    site: Dict[str, Any],
    ticker_html: str = "",
    stats: Optional[List[Dict[str, Any]]] = None,
    lang: str = DEFAULT_LANGUAGE,
    theme: str = DEFAULT_THEME,
    generated_at: Optional[str] = None,
) -> str:
    """Render the bilingual, themed portal front page from a ``content.build_site`` dict.

    The editorial content (about / services / why-us), the company history
    timeline, success stories and the contact directory are interleaved with
    advertisement sections driven by ``PORTAL_LAYOUT`` — so the sponsored slots
    are *decorated into* the reading flow rather than bolted on the side.
    """
    language = get_language(lang)
    code = language["code"]
    config = site.get("config", {})
    site_name = html.escape(str(config.get("site_name", "Real Estate Portal")))
    tagline = html.escape(translate(str(config.get("tagline", "")), code))

    nav_items = "".join(
        f'<a href="#{html.escape(str(n.get("key", "")))}">{html.escape(translate(str(n.get("label", "")), code))}</a>'
        for n in site.get("navigation", [])
    )
    nav = f'<nav class="site-nav"><span class="brand">{site_name}</span><span class="nav-links">{nav_items}</span></nav>'

    blocks = []
    hero = next((b for b in site.get("layout", []) if b.get("kind") == "hero"), None)
    for block in site.get("layout", []):
        if block.get("kind") == "hero" and hero is not None:
            hero_heading = html.escape(translate(str(block.get("heading") or site_name), code))
            hero_sub = html.escape(translate(str(block.get("subheading") or tagline), code))
            hero_ad = render_ad_section(
                {"slot": "hero", "heading": "Featured partners", "ads": block.get("ads") or []}, code
            ) if block.get("ads") else ""
            blocks.append(
                f'<section class="hero"><h1>{hero_heading}</h1><p>{hero_sub}</p>{hero_ad}</section>'
            )
            continue
        blocks.append(render_portal_block(block, code, stats))

    return (
        _PORTAL_TEMPLATE.replace("__LANG__", code)
        .replace("__DIR__", language["dir"])
        .replace("__FONT_STACK__", language["font_stack"])
        .replace("__THEME_STYLE__", theme_style(theme))
        .replace("__THEME_JS__", THEME_JS)
        .replace("__TITLE__", site_name)
        .replace("__NAV__", nav)
        .replace("__TICKER__", ticker_html or "")
        .replace("__LANG_LINKS__", lang_links_html(code))
        .replace("__THEME_LABEL__", html.escape(translate("Theme", code)))
        .replace("__THEME_AUTO__", html.escape(translate("Auto", code)))
        .replace("__THEME_LIGHT__", html.escape(translate("Light", code)))
        .replace("__THEME_DARK__", html.escape(translate("Dark", code)))
        .replace("__THEME_CURRENT__", html.escape(translate("Auto", code)))
        .replace("__GENERATED_LABEL__", html.escape(translate("Generated", code)))
        .replace("__GENERATED__", html.escape(str(generated_at or datetime.now().isoformat(timespec="seconds"))))
        .replace("__FOOTER__", html.escape(translate("Real Estate Portal", code)) + " · " + site_name)
        .replace("__BODY__", "".join(blocks))
    )


_PORTAL_TEMPLATE = """<!DOCTYPE html>
<html lang="__LANG__" dir="__DIR__">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__</title>
  __THEME_STYLE__
  <style>
    * { box-sizing: border-box; }
    body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.6 __FONT_STACK__; }
    .wrap { max-width: 1120px; margin: 0 auto; padding: 0 22px 60px; }
    .site-nav { position:sticky; top:0; z-index:20; display:flex; align-items:center; gap:18px;
                flex-wrap:wrap; padding:12px 22px; background:var(--surface);
                border-bottom:1px solid var(--line); box-shadow:var(--shadow); }
    .site-nav .brand { font-weight:700; font-size:17px; color:var(--accent); }
    .site-nav .nav-links { display:flex; gap:14px; flex-wrap:wrap; margin-inline-start:auto; }
    .site-nav a { color:var(--ink); text-decoration:none; font-size:13px; }
    .site-nav a:hover { color:var(--accent); }
    .hero { background:linear-gradient(135deg,var(--surface),var(--surface-2));
            border:1px solid var(--line); border-radius:14px; padding:30px 26px; margin:22px 0 18px; }
    .hero h1 { margin:0 0 6px; font-size:30px; }
    .hero p { margin:0 0 16px; color:var(--muted); font-size:15px; }
    section { background:var(--surface); border:1px solid var(--line); border-radius:10px;
              padding:18px 20px; margin-bottom:18px; }
    h2 { font-size:16px; margin:0 0 12px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
    h3 { margin:0 0 6px; font-size:16px; }
    .sub { color:var(--muted); }
    .ctrlbar { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin:0 0 10px; }
    .ctrlbar .grow { flex:1 1 auto; }
    .ctrbtn { font:inherit; color:var(--ink); background:var(--surface); border:1px solid var(--line);
              border-radius:6px; padding:3px 10px; cursor:pointer; }
    .langlink { color:var(--ink); text-decoration:none; padding:2px 9px; border-radius:6px; border:1px solid var(--line); }
    .langlink.active { background:var(--pill-bg); color:var(--pill-ink); border-color:transparent; font-weight:600; }
    .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin-top:12px; }
    .card { border:1px solid var(--line); border-radius:8px; padding:12px 14px; background:var(--surface-2); }
    .card .lbl { font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
    .card .val { font-size:20px; font-weight:600; margin-top:4px; }
    .card .sub { font-size:11px; color:var(--muted); }
    ul.bullets { margin:12px 0 0; padding-inline-start:20px; }
    ul.bullets li { margin:4px 0; }
    /* ---- advertisements ---- */
    .ad-section { background:var(--ad-bg); border:1px solid var(--ad-line); }
    .ad-section > h2 { color:var(--ad-sponsor); }
    .ad-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:14px; }
    .ad-slot-banner .ad-grid, .ad-slot-hero .ad-grid, .ad-slot-footer .ad-grid {
      grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); }
    .ad-card { display:flex; flex-direction:column; gap:8px; background:var(--surface);
               border:1px solid var(--ad-line); border-radius:10px; padding:14px 16px;
               border-inline-start:4px solid var(--ad-sponsor); }
    .ad-card.house-ad { border-style:dashed; }
    .ad-top { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
    .ad-badge { background:var(--ad-badge-bg); color:var(--ad-badge-ink); border-radius:999px;
                padding:2px 10px; font-size:11px; font-weight:700; letter-spacing:.03em; }
    .ad-sponsor { color:var(--ad-sponsor); font-size:11px; text-transform:uppercase; letter-spacing:.06em; }
    .ad-headline { font-size:16px; font-weight:700; color:var(--ad-ink); }
    .ad-body { color:var(--muted); font-size:13px; }
    .ad-meta { font-size:12px; color:var(--ad-sponsor); font-variant-numeric:tabular-nums; }
    .ad-foot { margin-top:auto; }
    .ad-cta { display:inline-block; background:var(--ad-cta-bg); color:var(--ad-cta-ink);
              border-radius:7px; padding:7px 14px; font-size:13px; font-weight:600;
              text-decoration:none; }
    /* ---- timeline ---- */
    .timeline { display:flex; flex-direction:column; gap:0; margin-top:6px; }
    .tl-item { display:grid; grid-template-columns:96px 1fr; gap:14px; padding:10px 0;
               border-bottom:1px dashed var(--line); }
    html[dir="rtl"] .tl-item { grid-template-columns:1fr 96px; }
    .tl-when { font-weight:700; color:var(--accent); font-variant-numeric:tabular-nums; }
    .tl-title { font-weight:600; }
    .tl-kind { margin-inline-start:8px; font-size:11px; color:var(--muted); text-transform:uppercase; }
    .tl-desc { color:var(--muted); font-size:13px; }
    /* ---- success stories ---- */
    .stories { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:14px; }
    .story { border:1px solid var(--line); border-radius:10px; padding:16px 18px; background:var(--surface-2); }
    .story-top { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
    .story-loc { margin-inline-start:auto; color:var(--muted); font-size:12px; }
    .story-metrics { margin:8px 0; }
    .story-quote { margin:10px 0 4px; padding-inline-start:12px; border-inline-start:3px solid var(--accent);
                   font-style:italic; color:var(--ink); }
    .story-who { color:var(--muted); font-size:12px; }
    .stars { color:#eab308; letter-spacing:2px; }
    /* ---- contact ---- */
    .contact-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:14px; }
    .contact-card { border:1px solid var(--line); border-radius:10px; padding:14px 16px; background:var(--surface-2); }
    .c-icon { font-size:20px; color:var(--accent); }
    .c-label { font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); margin-top:4px; }
    .c-value { font-weight:600; margin-top:2px; }
    .faqs details { border:1px solid var(--line); border-radius:8px; padding:8px 12px; margin-top:8px; background:var(--surface-2); }
    .faqs summary { cursor:pointer; font-weight:600; }
    footer { color:var(--muted); font-size:12px; text-align:center; margin-top:26px; }
    @media print { .site-nav, .ctrlbar { display:none; } body { background:#fff; color:#000; } }
  </style>
</head>
<body>
__TICKER__
__NAV__
<div class="wrap">
  <div style="display:flex;justify-content:flex-end;padding-top:8px">
    <div class="ctrlbar">
      <span>__LANG_LINKS__</span>
      <button class="ctrbtn" type="button" title="__THEME_LABEL__" data-theme-cycle
              data-auto="__THEME_AUTO__" data-light="__THEME_LIGHT__" data-dark="__THEME_DARK__">&#9680;
        <span id="themeName">__THEME_CURRENT__</span></button>
    </div>
  </div>
  __BODY__
  <footer>__FOOTER__ · __GENERATED_LABEL__ __GENERATED__</footer>
</div>
__THEME_JS__
<script>
  document.querySelectorAll('[data-theme-cycle]').forEach(function (b) {
    b.addEventListener('click', function () {
      var t = window.portalTheme.cycle();
      var el = document.getElementById('themeName');
      if (el) el.textContent = b.dataset[t] || t;
    });
  });
  document.querySelectorAll('.langlink').forEach(function (a) {
    a.addEventListener('click', function (e) {
      e.preventDefault();
      try {
        var u = new URL(window.location.href);
        u.searchParams.set('lang', a.dataset.lang);
        window.location.href = u.toString();
      } catch (err) { window.location.search = '?lang=' + a.dataset.lang; }
    });
  });
</script>
</body>
</html>"""


# ============================================================
# FORECAST HELPERS
# ============================================================


def growth_series(base: float, cagr: float, years: int, start_year: Optional[int] = None) -> List[Dict[str, Any]]:
    """Compound-growth projection: returns one row per year (year 0 .. years)."""
    y0 = start_year if start_year is not None else datetime.now().year
    return [
        {"year": y0 + y, "offset": y, "value": round(base * (1 + cagr) ** y, 2)}
        for y in range(0, years + 1)
    ]
