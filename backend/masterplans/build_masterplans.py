"""
Build the master-plan data the portal and the assistant use (DHA, Bahria Town and other
housing societies), from the PDFs / images and the georeferenced plans in a "Maps" folder::

    Maps/
      DHA Rawalpindi/PH-I Colours (14-04-25)-Model.pdf, …   the 8 DHA master-plan PDFs
      DHA Rawalpindi/Georeferenced/DHA_Phase_I/DHA_Phase_I_source.png, _EPSG3857.png/.pgw, _gcps.csv …
      DHA Rawalpindi/Georeferenced/accuracy_report.json
      Bahria Town/Georeferenced/…                     the same, one folder per group (GROUPS)
      Islamabad Societies/Georeferenced/…

A plan from an image (no PDF) gets no text labels; one from a PDF gets them like DHA's. For the
Bahria / society plans the source file and page come from the group's ``accuracy_report.json``.

Run from backend/ (a few minutes)::

    uv run --with pymupdf --with numpy python masterplans/build_masterplans.py --maps "C:/…/Maps"

Writes to ``media/masterplans`` (or ``--out``; the server reads ``MASTERPLANS_DIR``):

* ``plans.json``        one entry per plan: outline, bounds, transforms, accuracy, legend /
                        area-statement text, label counts
* ``labels.json.gz``    every text label on every plan (sector / block names, plot numbers and
                        sizes, road widths, parks, mosques, schools, commercial, utilities …)
                        placed on the ground (lat/lon) and classified
* ``<plan>/tiles/{z}/{x}/{y}.png``   the plan as a transparent map overlay (Web Mercator)
* ``<plan>/source/{cx}_{cy}.png``    the un-warped plan cut into 1024 px pieces, for readable
                                     close-ups ("share this part of the plan")
* ``<plan>/preview.png``             the whole plan, small

How labels get on the ground: the georeferenced ``_source.png`` is the PDF rendered at
8000 px on its long side and cropped; the crop is found by matching the rendering to the
PNG, then each label goes PDF points → PNG pixels → (ground control point fit) → lat/lon.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pymupdf
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE.parent / "media" / "masterplans"
R = 6378137.0
WORLD = 2 * math.pi * R
CHUNK = 1024

# group -> its sub-folder of --maps and the credit shown on the map
GROUPS: Dict[str, Dict[str, str]] = {
    "dha": {"dir": "DHA Rawalpindi", "attribution": "Master plan © DHA Islamabad-Rawalpindi"},
    "bahria": {"dir": "Bahria Town", "attribution": "Master plan © Bahria Town (Pvt) Ltd"},
    "societies": {"dir": "Islamabad Societies", "attribution": "Master plan © the society's developer"},
}

PLANS: List[Dict[str, Any]] = [
    {"key": "ph1", "folder": "DHA_Phase_I", "pdf": "PH-I Colours (14-04-25)-Model.pdf",
     "name": "DHA Phase I", "city": "Islamabad", "aliases": ["dha 1", "dha phase 1", "dha phase i", "dha ph 1", "phase 1 dha"]},
    {"key": "ph2", "folder": "DHA_Phase_II", "pdf": "PH-II Colours (14-04-25)-Model.pdf",
     "name": "DHA Phase II", "city": "Islamabad", "aliases": ["dha 2", "dha phase 2", "dha phase ii", "dha ph 2", "phase 2 dha"]},
    {"key": "ph3", "folder": "DHA_Phase_III", "pdf": "PH-III Colours(16-04-25)-Model 2.pdf",
     "name": "DHA Phase III", "city": "Rawalpindi", "aliases": ["dha 3", "dha phase 3", "dha phase iii", "dha ph 3"]},
    {"key": "ph5", "folder": "DHA_Phase_V", "pdf": "PH-V Colours(16-04-25)-Model.pdf",
     "name": "DHA Phase V", "city": "Islamabad", "aliases": ["dha 5", "dha phase 5", "dha phase v", "dha ph 5"]},
    {"key": "ph6", "folder": "DHA_Phase_VI", "pdf": "Master Plan  Ph-6 UPDATE ON 22 AUG 24-Model.pdf",
     "name": "DHA Phase VI", "city": "Islamabad", "aliases": ["dha 6", "dha phase 6", "dha phase vi", "dha ph 6"]},
    {"key": "me12", "folder": "DHA_ME-1_ME-2", "pdf": "Combine file Of ME-1 & ME-2 Updated-Model.pdf",
     "name": "DHA ME-1 & ME-2", "city": "Islamabad", "aliases": ["me-1", "me-2", "me 1", "me 2", "dha me", "dha me-1", "dha me-2"]},
    {"key": "rvn", "folder": "DHA_River_View_North", "pdf": "RVN,PH-4 Updated (22-04-25)-Model 2.pdf",
     "name": "DHA River View North", "city": "Rawalpindi",
     "aliases": ["river view north", "dha river view north", "dha phase 4", "dha phase iv", "dha 4", "rvn"]},
    {"key": "rvs", "folder": "DHA_River_View_South", "pdf": "RIVER VIEW SOUTH-Final.pdf",
     "name": "DHA River View South", "city": "Rawalpindi",
     "aliases": ["river view south", "dha river view south", "rvs", "dha phase 4 south"]},
]

# Bahria Town: "scheme" is the portal society the plan belongs to (geodata/pk_housing_schemes.json)
_B = "Bahria Town Phases 1-6 (Islamabad/Rawalpindi)"
PLANS += [dict(p, group="bahria") for p in [
    {"key": "bt16", "folder": "Bahria_Town_Phase_1-6", "name": "Bahria Town Phase 1-6", "city": "Rawalpindi", "scheme": _B,
     "aliases": ["bahria town phase 1", "bahria phase 1-6", "bahria town rawalpindi", "bahria town islamabad", "bahria phase 4", "bahria phase 6"]},
    {"key": "bt7", "folder": "Bahria_Town_Phase_7", "name": "Bahria Town Phase 7", "city": "Rawalpindi", "scheme": "Bahria Town Phase 7",
     "aliases": ["bahria phase 7", "bahria town phase vii", "bahria phase vii"]},
    {"key": "bt8", "folder": "Bahria_Town_Phase_8", "name": "Bahria Town Phase 8", "city": "Rawalpindi", "scheme": "Bahria Town Phase 8",
     "aliases": ["bahria phase 8", "bahria town phase viii", "bahria phase viii"]},
    {"key": "bt8sv", "folder": "Bahria_Town_Safari_Valley", "name": "Bahria Town Safari Valley", "city": "Rawalpindi",
     "scheme": "Bahria Town Phase 8", "aliases": ["safari valley", "bahria safari valley", "phase 8 safari valley"]},
    {"key": "btgc", "folder": "Bahria_Garden_City", "name": "Bahria Garden City", "city": "Islamabad", "scheme": "Bahria Garden City",
     "aliases": ["bahria garden city", "garden city bahria", "bgc"]},
    {"key": "bte", "folder": "Bahria_Enclave", "name": "Bahria Enclave Islamabad", "city": "Islamabad", "scheme": "Bahria Enclave Islamabad",
     "aliases": ["bahria enclave", "bahria enclave islamabad", "enclave 1"]},
    {"key": "bte2", "folder": "Bahria_Enclave_II", "name": "Bahria Enclave II", "city": "Islamabad", "scheme": "Bahria Enclave Islamabad",
     "aliases": ["bahria enclave 2", "bahria enclave ii", "enclave 2"]},
    {"key": "btpar", "folder": "Bahria_Paradise_Commercial", "name": "Bahria Paradise (GT Road)", "city": "Rawalpindi", "scheme": _B,
     "aliases": ["bahria paradise", "paradise bahria", "bahria paradise gt road", "paradise mall bahria"]},
    # Bahria Town Lahore's sheet is not one uniform scale: 10 sections, each fitted on its own, tiling along roads / canal
    *[{"key": f"btlhr{k}", "acc": f"btlhr_{k}", "folder": folder, "name": f"Bahria Town Lahore — {label}", "city": "Lahore",
       "scheme": "Bahria Town Lahore", "aliases": ["bahria town lahore", "bahria lahore", "btl"] if k == "ne" else []}
      for k, folder, label in [
        ("ne", "Bahria_Town_Lahore_NE", "North-East (Sectors B & C)"),
        ("nc", "Bahria_Town_Lahore_N_Central", "North-Central (Overseas A, Awais Qarni)"),
        ("nw", "Bahria_Town_Lahore_NW", "North-West (Sector D, Overseas B & C)"),
        ("wa", "Bahria_Town_Lahore_Sector_A", "Sector A"),
        ("wc", "Bahria_Town_Lahore_Canal_View", "Canal View Residency"),
        ("wg", "Bahria_Town_Lahore_GSS_Multan_Road", "GSS & Multan Road Block"),
        ("se", "Bahria_Town_Lahore_SE", "South-East (Sector E)"),
        ("sww", "Bahria_Town_Lahore_SW", "South-West (Overseas Ext., Talha)"),
        ("swe", "Bahria_Town_Lahore_S_Central", "South-Central (Iqbal, Nishtar, Shershah)"),
        ("s", "Bahria_Town_Lahore_South", "South (Golf View, Sector F)"),
    ]],
    {"key": "borch", "folder": "Bahria_Orchard", "name": "Bahria Orchard", "city": "Lahore", "scheme": "Bahria Orchard",
     "aliases": ["bahria orchard", "orchard lahore", "bahria orchard phase 1"]},
    {"key": "bemc", "folder": "Bahria_Education_Medical_City", "name": "Bahria Education & Medical City", "city": "Lahore",
     "scheme": "Bahria Town Lahore", "aliases": ["bahria education and medical city", "bemc", "bahria medical city"]},
    {"key": "bnash", "acc": "bnash_core", "folder": "Bahria_Nasheman", "name": "Bahria Nasheman", "city": "Lahore",
     "scheme": "Bahria Town Lahore", "aliases": ["bahria nasheman", "nasheman lahore"]},
    {"key": "bnashb", "acc": "bnash_blvd", "folder": "Bahria_Nasheman_Main_Boulevard", "name": "Bahria Nasheman — Main Boulevard",
     "city": "Lahore", "scheme": "Bahria Town Lahore", "aliases": ["bahria nasheman boulevard", "sunflower block nasheman"]},
    {"key": "brehm", "folder": "Bahria_Al_Rehmat", "name": "Bahria Al-Rehmat", "city": "Lahore", "scheme": "Bahria Town Lahore",
     "aliases": ["bahria rehmat", "bahria al-rehmat", "bahria al rehmat"]},
    {"key": "btk", "folder": "Bahria_Town_Karachi", "name": "Bahria Town Karachi", "city": "Karachi", "scheme": "Bahria Town Karachi",
     "aliases": ["bahria town karachi", "btk", "bahria karachi"]},
    *[{"key": f"btk{c}", "folder": f"Bahria_Town_Karachi_Side_{c.upper()}", "name": f"Bahria Town Karachi Side {c.upper()}",
       "city": "Karachi", "scheme": "Bahria Town Karachi", "aliases": [f"bahria town karachi side {c}", f"btk side {c}"]}
      for c in "abcd"],
    {"key": "btkc2", "folder": "Bahria_Town_Karachi_Side_C_North", "name": "Bahria Town Karachi Side C (P56-57)", "city": "Karachi",
     "scheme": "Bahria Town Karachi", "aliases": ["bahria town karachi precinct 56", "bahria town karachi precinct 57"]},
    {"key": "btkd2", "folder": "Bahria_Town_Karachi_Side_D_North", "name": "Bahria Town Karachi Side D North", "city": "Karachi",
     "scheme": "Bahria Town Karachi", "aliases": ["bahria greens karachi", "bahria town karachi valley block", "bahria town karachi precinct 40"]},
]]

# Other housing societies (Islamabad Expressway, Lehtrar Road, Murree Road, near the airport)
SOCIETIES: List[Dict[str, Any]] = [
    {"key": "topc", "folder": "Top_City-1", "name": "Top City-1", "city": "Rawalpindi", "scheme": "Top City-1",
     "aliases": ["top city", "top city 1", "topcity"]},
    {"key": "aamin", "folder": "Aamin_Housing_1", "name": "Aamin Housing 1", "city": "Rawalpindi", "scheme": None,
     "aliases": ["aamin housing", "aamin housing one"]},
    {"key": "eight", "folder": "Eighteen", "name": "Eighteen", "city": "Rawalpindi", "scheme": "Eighteen (Elite Reverie Housing)",
     "aliases": ["eighteen islamabad", "elite reverie", "18 islamabad"]},
    {"key": "unit", "folder": "University_Town", "name": "University Town", "city": "Rawalpindi", "scheme": "University Town",
     "aliases": ["university town islamabad"]},
    {"key": "mumtz", "folder": "Mumtaz_City", "name": "Mumtaz City", "city": "Rawalpindi", "scheme": None,
     "aliases": ["mumtaz city islamabad"]},
    {"key": "agg", "folder": "Airport_Green_Garden", "name": "Airport Green Garden", "city": "Rawalpindi", "scheme": None,
     "aliases": ["airport green garden", "agg"]},
    {"key": "khuda", "folder": "Khudadad_City", "name": "Khudadad City (Airport Enclave)", "city": "Rawalpindi", "scheme": None,
     "aliases": ["khudadad city", "airport enclave"]},
    {"key": "parad", "folder": "Paradise_City", "name": "Paradise City", "city": "Islamabad", "scheme": None,
     "aliases": ["paradise city islamabad"]},
    {"key": "teleg", "folder": "Tele_Gardens_F-17", "name": "Tele Gardens F-17", "city": "Islamabad", "scheme": None,
     "aliases": ["tele gardens", "f-17 tele gardens", "t&t echs f-17"]},
    {"key": "scehs", "folder": "Supreme_Court_EHS", "name": "Supreme Court Employees Housing Scheme", "city": "Islamabad", "scheme": None,
     "aliases": ["supreme court housing", "scehs"]},
    {"key": "fres", "folder": "Faisal_Residencia", "name": "Faisal Residencia", "city": "Islamabad", "scheme": None,
     "aliases": ["faisal residencia", "faisal residentia", "e-17 faisal"]},
    {"key": "ft1", "folder": "Faisal_Town_I", "name": "Faisal Town Phase I", "city": "Islamabad", "scheme": "Faisal Town Phase 1 (F-18)",
     "aliases": ["faisal town", "faisal town 1", "faisal town f-18"]},
    {"key": "ft2", "folder": "Faisal_Town_II", "name": "Faisal Town Phase II", "city": "Rawalpindi", "scheme": None,
     "aliases": ["faisal town 2", "faisal town phase 2"]},
    {"key": "fmc", "folder": "Faisal_Margalla_City", "name": "Faisal Margalla City", "city": "Rawalpindi", "scheme": None,
     "aliases": ["faisal margalla city", "fmc"]},
    {"key": "fh1", "folder": "Faisal_Hills_Phase_I", "name": "Faisal Hills Phase I", "city": "Rawalpindi", "scheme": None,
     "aliases": ["faisal hills", "faisal hills 1", "faisal hills phase 1"]},
    {"key": "fh2", "folder": "Faisal_Hills_Phase_II", "name": "Faisal Hills Phase II", "city": "Rawalpindi", "scheme": None,
     "aliases": ["faisal hills 2", "faisal hills phase 2"]},
    {"key": "mg17", "folder": "Multi_Gardens_B-17", "name": "Multi Gardens B-17 Phase I", "city": "Islamabad", "scheme": "B-17 Multi Gardens (MPCHS) Phase I",
     "aliases": ["b-17", "multi gardens b-17", "mpchs b-17"]},
    {"key": "mg18", "folder": "Multi_Gardens_B-18_DE", "name": "Multi Gardens B-18 Blocks D & E", "city": "Islamabad", "scheme": "B-17 Multi Gardens (MPCHS) Phase I",
     "aliases": ["b-18", "multi gardens b-18"]},
    {"key": "mgpb", "folder": "Multi_Gardens_Punjab", "name": "Multi Gardens Punjab Part", "city": "Rawalpindi", "scheme": "B-17 Multi Gardens (MPCHS) Phase I",
     "aliases": ["multi gardens punjab"]},
    {"key": "csc1", "folder": "Capital_Smart_City_Phase_1", "name": "Capital Smart City Phase 1", "city": "Rawalpindi", "scheme": "Capital Smart City",
     "aliases": ["capital smart city", "csc", "smart city islamabad"]},
    {"key": "csc2", "folder": "Capital_Smart_City_Phase_2", "name": "Capital Smart City Phase 2", "city": "Rawalpindi", "scheme": "Capital Smart City",
     "aliases": ["capital smart city phase 2", "csc phase 2"]},
    {"key": "qurt", "folder": "Qurtaba_City", "name": "Qurtaba City", "city": "Rawalpindi", "scheme": None,
     "aliases": ["qurtaba city"]},
    {"key": "bwc", "folder": "Blue_World_City_General_Block", "name": "Blue World City General Block", "city": "Rawalpindi", "scheme": "Blue World City",
     "aliases": ["blue world city", "bwc"]},
    {"key": "gbg", "folder": "Gulberg_Greens", "name": "Gulberg Greens", "city": "Islamabad", "scheme": "Gulberg Greens",
     "aliases": ["gulberg greens", "gulberg green"]},
    {"key": "gbr", "folder": "Gulberg_Residencia", "name": "Gulberg Residencia", "city": "Islamabad", "scheme": "Gulberg Residencia",
     "aliases": ["gulberg residencia", "gulberg islamabad"]},
    {"key": "nav", "folder": "Naval_Anchorage", "name": "Naval Anchorage", "city": "Islamabad", "scheme": "Naval Anchorage Islamabad",
     "aliases": ["naval anchorage"]},
    {"key": "jg1", "folder": "Jinnah_Garden_Phase_I_Ext", "name": "Jinnah Garden Phase I Extension", "city": "Islamabad", "scheme": "Jinnah Garden",
     "aliases": ["jinnah garden", "jinnah garden phase 1"]},
    {"key": "jg2", "folder": "Jinnah_Garden_Phase_II", "name": "Jinnah Garden Phase II", "city": "Islamabad", "scheme": "Jinnah Garden",
     "aliases": ["jinnah garden phase 2"]},
    {"key": "soan", "folder": "Soan_Garden", "name": "Soan Garden", "city": "Islamabad", "scheme": "Soan Garden",
     "aliases": ["soan garden", "soan gardens"]},
    {"key": "cbr", "folder": "CBR_Town_Phase_I", "name": "CBR Town Phase I", "city": "Islamabad", "scheme": "CBR Town Phase I",
     "aliases": ["cbr town", "cbr"]},
    {"key": "rivg", "folder": "River_Garden", "name": "River Garden", "city": "Islamabad", "scheme": None,
     "aliases": ["river garden islamabad"]},
    {"key": "opf", "folder": "OPF_Housing_Scheme", "name": "OPF Housing Scheme", "city": "Islamabad", "scheme": None,
     "aliases": ["opf housing", "opf zone 5"]},
    {"key": "senat", "folder": "Senate_Avenue", "name": "Senate Avenue", "city": "Islamabad", "scheme": None,
     "aliases": ["senate avenue"]},
    {"key": "pwd", "folder": "PWD_Housing_Society", "name": "PWD Housing Society", "city": "Islamabad", "scheme": "PWD Housing Scheme",
     "aliases": ["pwd", "pwd housing"]},
    {"key": "pvc", "folder": "Park_View_City", "name": "Park View City Islamabad", "city": "Islamabad", "scheme": "Park View City Islamabad",
     "aliases": ["park view city", "park view", "pvc"]},
    {"key": "pvcx", "folder": "Park_View_City_Extensions", "name": "Park View City Extensions", "city": "Islamabad", "scheme": "Park View City Islamabad",
     "aliases": ["park view city extension"]},
    {"key": "pke", "folder": "Park_Enclave_III", "name": "Park Enclave III", "city": "Islamabad", "scheme": None,
     "aliases": ["park enclave", "park enclave 3"]},
    {"key": "fgge", "folder": "FGEHA_Green_Enclave", "name": "FGEHA Green Enclave Bhara Kahu", "city": "Islamabad", "scheme": None,
     "aliases": ["green enclave", "fgeha bhara kahu"]},
    {"key": "navf", "folder": "Pakistan_Navy_Farms", "name": "Pakistan Navy Farms (Simly Dam Road)", "city": "Islamabad", "scheme": None,
     "aliases": ["navy farms", "pakistan navy farms"]},
    {"key": "anza", "folder": "Anza_Zephyr_Dale", "name": "Anza Zephyr Dale Agro Farms", "city": "Islamabad", "scheme": None,
     "aliases": ["anza zephyr", "zephyr dale"]},
    {"key": "alham", "folder": "Al-Hamra_Hills", "name": "Al-Hamra Hills Agro Farming", "city": "Islamabad", "scheme": None,
     "aliases": ["al-hamra hills", "al hamra hills"]},
    {"key": "rahm", "folder": "Rahman_Enclave", "name": "Rahman Enclave", "city": "Islamabad", "scheme": None,
     "aliases": ["rahman enclave"]},
    {"key": "taj", "folder": "Taj_Residencia", "name": "Taj Residencia", "city": "Islamabad", "scheme": "Taj Residencia",
     "aliases": ["taj residencia", "taj"]},
    {"key": "tajx", "folder": "Taj_Residencia_Sheikhpur_Extension", "name": "Taj Residencia Sheikhpur Extension", "city": "Rawalpindi", "scheme": "Taj Residencia",
     "aliases": ["taj residencia extension"]},
    {"key": "saff", "folder": "Saffron_City", "name": "Saffron City", "city": "Rawalpindi", "scheme": None,
     "aliases": ["saffron city"]},
    {"key": "gabad", "folder": "Gulshan-e-Abad", "name": "Gulshan-e-Abad", "city": "Rawalpindi", "scheme": "Gulshan-e-Abad",
     "aliases": ["gulshan abad", "gulshanabad"]},
    {"key": "rudn", "folder": "Rudn_Enclave", "name": "Rudn Enclave", "city": "Rawalpindi", "scheme": "Rudn Enclave",
     "aliases": ["rudn enclave", "rudn"]},
    {"key": "rudnx", "folder": "Rudn_Enclave_Executive", "name": "Rudn Enclave Executive Block", "city": "Rawalpindi", "scheme": "Rudn Enclave",
     "aliases": ["rudn executive"]},
    {"key": "rudnh", "folder": "Rudn_Enclave_H_Block", "name": "Rudn Enclave H-Block", "city": "Rawalpindi", "scheme": "Rudn Enclave",
     "aliases": ["rudn h block"]},
]
PLANS += [dict(p, group="societies") for p in SOCIETIES]


# ------------------------------------------------------------------ projections

def merc(lat: float, lon: float) -> Tuple[float, float]:
    x = math.radians(lon) * R
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * R
    return x, y


def unmerc(x: float, y: float) -> Tuple[float, float]:
    lon = math.degrees(x / R)
    lat = math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2)
    return lat, lon


# ------------------------------------------------------------------ ground control

def fit_transform(gcps: List[Tuple[float, float, float, float]], method: str) -> Dict[str, Any]:
    """Pixel (x, y) -> Web Mercator (X, Y). Affine: X = a x + b y + c, Y = d x + e y + f.
    Similarity (image y points down): X = a x + b y + c, Y = b x - a y + d."""
    px = np.array([[g[0], g[1]] for g in gcps], dtype=float)
    mm = np.array([merc(g[2], g[3]) for g in gcps], dtype=float)
    if method == "affine" and len(gcps) >= 3:
        A = np.column_stack([px[:, 0], px[:, 1], np.ones(len(px))])
        cx, *_ = np.linalg.lstsq(A, mm[:, 0], rcond=None)
        cy, *_ = np.linalg.lstsq(A, mm[:, 1], rcond=None)
        m = [[cx[0], cx[1], cx[2]], [cy[0], cy[1], cy[2]]]
    else:
        rows, rhs = [], []
        for (x, y), (X, Y) in zip(px, mm):
            rows.append([x, y, 1, 0]); rhs.append(X)
            rows.append([-y, x, 0, 1]); rhs.append(Y)
        a, b, c, d = np.linalg.lstsq(np.array(rows), np.array(rhs), rcond=None)[0]
        m = [[a, b, c], [b, -a, d]]
    M = np.array([m[0], m[1], [0, 0, 1]], dtype=float)
    inv = np.linalg.inv(M)
    pred = (M @ np.column_stack([px, np.ones(len(px))]).T).T[:, :2]
    # residuals in ground metres (Mercator metres × cos(lat))
    k = math.cos(math.radians(gcps[0][2]))
    res = [float(np.hypot(*(p - q)) * k) for p, q in zip(pred, mm)]
    return {"matrix": M[:2].tolist(), "inverse": inv[:2].tolist(), "residuals_m": [round(r, 1) for r in res],
            "m_per_px": float(math.sqrt(abs(np.linalg.det(M[:2, :2]))) * k)}


def apply(M: List[List[float]], x: float, y: float) -> Tuple[float, float]:
    return M[0][0] * x + M[0][1] * y + M[0][2], M[1][0] * x + M[1][1] * y + M[1][2]


# ------------------------------------------------------------------ PDF ↔ PNG alignment

def find_crop(page: "pymupdf.Page", source: Image.Image, ds: int = 8) -> Tuple[float, int, int, float]:
    """The scale and offset that turn the rendered PDF into ``_source.png``."""
    scale = 8000 / max(page.rect.width, page.rect.height)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale / ds, scale / ds), alpha=False)
    rend = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]
    rmask = (rend.min(axis=2) < 235).astype(np.float32)
    small = source.resize((max(1, source.width // ds), max(1, source.height // ds)), Image.BILINEAR)
    smask = (np.asarray(small.convert("RGBA"))[:, :, 3] > 20).astype(np.float32)
    H, W = rmask.shape
    h, w = smask.shape
    F = np.fft.rfft2(rmask, s=(H + h, W + w))
    G = np.fft.rfft2(smask[::-1, ::-1], s=(H + h, W + w))
    cc = np.fft.irfft2(F * G, s=(H + h, W + w))
    iy, ix = np.unravel_index(int(np.argmax(cc)), cc.shape)
    dy, dx = iy - (h - 1), ix - (w - 1)
    sub = rmask[max(dy, 0):dy + h, max(dx, 0):dx + w]
    sm = smask[max(-dy, 0):max(-dy, 0) + sub.shape[0], max(-dx, 0):max(-dx, 0) + sub.shape[1]]
    iou = float((sub * sm).sum() / max(1.0, ((sub + sm) > 0).sum()))
    return scale, int(dx) * ds, int(dy) * ds, iou


# ------------------------------------------------------------------ labels

FACILITY = [
    ("mosque", r"\b(MASJID|MOSQUE|JAMIA|IMAMBARGAH|EID ?GAH)\b"),
    ("education", r"\b(SCHOOL|COLLEGE|UNIVERSITY|ACADEMY|EDUCATION|INSTITUTE|MADRASSA|MONTESSORI)\b"),
    ("health", r"\b(HOSPITAL|CLINIC|MEDICAL|HEALTH|DISPENSARY|MATERNITY)\b"),
    ("graveyard", r"\b(GRAVEYARD|GRAVE YARD|CEMETERY|QABRISTAN)\b"),
    ("commercial", r"\b(COMMERCIAL|MARKET|MALL|SHOPS?|PLAZA|BUSINESS|BAZAAR|HYPER ?MARKET|CBD)\b"),
    ("mixed_use", r"\bMIXED ?USE\b"),
    ("apartments", r"\b(APARTMENTS?|FLATS|HIGH ?RISE|TOWERS?)\b"),
    ("community", r"\b(CLUB|COMMUNITY|SPORTS?|STADIUM|GYM|GOLF|CRICKET|FUTSAL|THEATRE|LIBRARY)\b"),
    ("park", r"\b(PARK|GREEN|PLAY ?GROUND|LAWN|GARDEN|ORCHARD|PIAZZA|PLAZA PARK|SITTING|WALKWAY|JOGGING)\b"),
    ("water", r"\b(LAKE|NULLAH|NALA|NALLAH|RIVER|POND|STREAM|KAS|DAM)\b"),
    ("gate", r"\b(GATE|ENTRANCE|ENTRY|CHECK ?POST|BARRIER)\b"),
    ("fuel", r"\b(PETROL|FUEL|CNG|FILLING STATION)\b"),
    ("amenity", r"\b(RESERVED|AMENITY|UTILITY|GRID|SUB ?STATION|WATER TANK|OVERHEAD TANK|TUBE ?WELL|DISPOSAL|"
                r"POLICE|FIRE|RESCUE|POST OFFICE|MONUMENT|PYLON AREA|TREATMENT|FILTRATION)\b"),
    ("parking", r"\bPARKING\b"),
]
ROAD = r"\b(STREET|ST\.|ST-|ROAD|RD\.?|AVENUE|AVE|BLVD|BOULEVARD|LANE|EXPRESSWAY|HIGHWAY|SERVICE|LINK|DRIVE|ROW|CUL)\b|\(\s*\d+(\.\d+)?'?\s*(W|WIDE)|\bWIDE\b"
PLOT_SIZE = r"\d+(\.\d+)?\s*'?\s*[X×]\s*\d+(\.\d+)?\s*'?|\b\d+(\.\d+)?\s*(KANAL|MARLA|SQ ?YD|SQYD|SFT|SFT\.)\b"
SECTOR = r"^(SECTOR|BLOCK|ZONE|POCKET|PHASE|PRECINCT|STREET)\s+[\w-]+$|^[A-Z]{1,2}-?\d{1,2}(-\d{1,3})?$|^SECTOR\b|^BLOCK\b|^ZONE\b"
INFRA = r"\b(TMH|WMH|GMH|EMH|SMH|TFR|TRF|SUMP|PYLON|STL|KVA|POLE|DRAIN|PIPE|MANHOLE|GRILL|FENCE|GABB?IA?ON|PICHING|PITCHING|RETAINING|WALL|STONE|RCC|STAIRS|SHUIT|SPEED BREAKER|CULVERT|BRIDGE|TRACK|LINE|10M|5\.06M)\b"
PLOT_NO = r"^\d{1,4}[A-Z]?(/\d+)?$|^[A-Z]-?\d{1,4}$"


def classify(text: str) -> str:
    t = text.upper()
    for cat, pat in FACILITY:
        if re.search(pat, t):
            return cat
    if re.match(r"^(ST|STREET|LANE|AVE|AVENUE|ROAD|RD)[\s.\-#]*\d+", t.strip()):
        return "road"
    if re.fullmatch(r"\d+(\.\d+)?\s*'(\s*-?\s*\d+(\.\d+)?\")?", t.strip()):
        return "dimension"  # a plot edge length, e.g. 35'
    if re.fullmatch(PLOT_NO, t.strip()):
        return "plot_number"
    if re.search(PLOT_SIZE, t):
        return "plot_size"
    if re.search(SECTOR, t.strip()):
        return "sector"
    if re.search(ROAD, t):
        return "road"
    if re.search(INFRA, t):
        return "infrastructure"
    return "label"


def drawn_mask(source: Image.Image, ds: int = 8, grow: int = 6) -> Tuple[np.ndarray, int]:
    """Where the cleaned plan has drawing (alpha), grown by ``grow`` × ``ds`` px so text on white
    roads (transparent) still counts — the large cut-away legend / table areas don't."""
    small = source.resize((max(1, source.width // ds), max(1, source.height // ds)), Image.BILINEAR)
    a = np.asarray(small.convert("RGBA"))[:, :, 3] > 20
    out = a.copy()
    for dyy in range(-grow, grow + 1):
        for dxx in range(-grow, grow + 1):
            out |= np.roll(np.roll(a, dyy, axis=0), dxx, axis=1)
    return out, ds


def extract_labels(page: "pymupdf.Page", scale: float, dx: int, dy: int, source_size: Tuple[int, int],
                   M: List[List[float]], keep: Optional[Tuple[np.ndarray, int]] = None) -> Tuple[List[List[Any]], List[str]]:
    labels, sheet = [], []
    d = page.get_text("dict")
    w, h = source_size
    for block in d.get("blocks", []):
        for line in block.get("lines", []):
            text = " ".join(s["text"].strip() for s in line.get("spans", []) if s["text"].strip())
            text = re.sub(r"\s+", " ", text).strip()
            if not text or not re.search(r"[A-Za-z0-9]", text):
                continue
            x0, y0, x1, y1 = line["bbox"]
            # Text positions are in the unrotated page; the rendering (and the image) is rotated.
            c = pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2) * page.rotation_matrix
            cx = c.x * scale - dx
            cy = c.y * scale - dy
            size = max((s.get("size", 0) for s in line.get("spans", [])), default=0)
            if not (0 <= cx < w and 0 <= cy < h) or (
                    keep is not None and not keep[0][min(int(cy) // keep[1], keep[0].shape[0] - 1), min(int(cx) // keep[1], keep[0].shape[1] - 1)]):
                if re.search(r"[A-Za-z]{3}", text):
                    sheet.append(text)  # title block, legend, area statement
                continue
            X, Y = apply(M, cx, cy)
            lat, lon = unmerc(X, Y)
            rm = page.rotation_matrix
            ddx = line["dir"][0] * rm.a + line["dir"][1] * rm.c
            ddy = line["dir"][0] * rm.b + line["dir"][1] * rm.d
            ang = round(math.degrees(math.atan2(-ddy, ddx)))
            labels.append([text[:120], classify(text), round(lat, 6), round(lon, 6), round(size, 1), ang])
    return labels, sheet


# ------------------------------------------------------------------ outline

def outline_from_warped(img: Image.Image, pgw: List[float]) -> List[List[float]]:
    """Convex hull of the plan's drawn area, as [[lat, lon], …]."""
    small = img.reduce(max(1, max(img.size) // 600))
    k = img.width / small.width
    a = np.asarray(small.convert("RGBA"))[:, :, 3] > 30
    ys, xs = np.nonzero(a)
    pts = sorted(set(zip(xs.tolist(), ys.tolist())))
    if len(pts) < 3:
        return []

    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    res, x0, y0 = pgw[0], pgw[4], pgw[5]
    return [[round(c, 6) for c in unmerc(x0 + (px + 0.5) * k * res, y0 - (py + 0.5) * k * res)] for px, py in hull]


# ------------------------------------------------------------------ tiles

def make_tiles(img: Image.Image, pgw: List[float], out: Path, zmin: int, zmax: int) -> int:
    res, X0, Y0 = pgw[0], pgw[4], pgw[5]
    X1, Y1 = X0 + img.width * res, Y0 - img.height * res
    count = 0
    level, level_res = img, res
    for z in range(zmax, zmin - 1, -1):
        tile_m = WORLD / 2 ** z
        tres = tile_m / 256
        while level_res * 2 <= tres and level.width > 512:  # work from a smaller copy at low zooms
            level = level.reduce(2)
            level_res *= 2
        tx0 = int((X0 + WORLD / 2) // tile_m)
        tx1 = int((X1 + WORLD / 2) // tile_m)
        ty0 = int((WORLD / 2 - Y0) // tile_m)
        ty1 = int((WORLD / 2 - Y1) // tile_m)
        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                bx0 = tx * tile_m - WORLD / 2
                by0 = WORLD / 2 - ty * tile_m
                px0 = (bx0 - X0) / level_res
                py0 = (Y0 - by0) / level_res
                span = tile_m / level_res
                box = (px0, py0, px0 + span, py0 + span)
                tile = level.transform((256, 256), Image.EXTENT, box, resample=Image.BILINEAR, fillcolor=(0, 0, 0, 0))
                if tile.getchannel("A").getbbox() is None:
                    continue
                p = out / str(z) / str(tx)
                p.mkdir(parents=True, exist_ok=True)
                tile.save(p / f"{ty}.png", optimize=True)
                count += 1
    return count


def make_chunks(src: Image.Image, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for cy in range(0, src.height, CHUNK):
        for cx in range(0, src.width, CHUNK):
            piece = src.crop((cx, cy, min(cx + CHUNK, src.width), min(cy + CHUNK, src.height)))
            if piece.getchannel("A").getbbox() is None:
                continue
            piece.save(out / f"{cx // CHUNK}_{cy // CHUNK}.png", optimize=True)


# ------------------------------------------------------------------ main

def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--maps", required=True, type=Path, help="folder with the PDFs and Georeferenced/")
    ap.add_argument("--out", type=Path, default=Path(os.getenv("MASTERPLANS_DIR") or DEFAULT_OUT))
    ap.add_argument("--plans", default=",".join(p["key"] for p in PLANS))
    ap.add_argument("--zmin", type=int, default=12)
    ap.add_argument("--zmax", type=int, default=17)
    ap.add_argument("--skip-images", action="store_true", help="labels and outlines only (fast)")
    args = ap.parse_args(argv)
    reports: Dict[str, Dict[str, Any]] = {}

    def report(group: str) -> Dict[str, Any]:
        if group not in reports:
            path = args.maps / GROUPS[group]["dir"] / "Georeferenced" / "accuracy_report.json"
            reports[group] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return reports[group]

    wanted = set(args.plans.split(","))
    args.out.mkdir(parents=True, exist_ok=True)
    meta_path = args.out / "plans.json"
    old = {p["key"]: p for p in json.loads(meta_path.read_text(encoding="utf-8"))["plans"]} if meta_path.exists() else {}
    labels_path = args.out / "labels.json.gz"
    old_labels: Dict[str, List[List[Any]]] = {}
    if labels_path.exists():
        with gzip.open(labels_path, "rt", encoding="utf-8") as f:
            old_labels = json.load(f)["plans"]

    plans_meta, all_labels = [], {}
    for cfg in PLANS:
        key = cfg["key"]
        if key not in wanted:
            if key in old:
                plans_meta.append(old[key])
                all_labels[key] = old_labels.get(key, [])
            continue
        t = time.time()
        group = cfg.get("group", "dha")
        base = args.maps / GROUPS[group]["dir"]
        acc = report(group).get(cfg.get("acc", key))  # the georeferencing report may use another key
        if acc is None:
            print(f"- {cfg['name']}: not georeferenced yet ({key} missing from the accuracy report)")
            if key in old:
                plans_meta.append(old[key])
                all_labels[key] = old_labels.get(key, [])
            continue
        folder = base / "Georeferenced" / (acc.get("folder") or cfg["folder"])
        cfg = dict(cfg, folder=folder.name)
        src_file = cfg.get("pdf") or acc.get("source") or ""
        pdf = base / src_file if src_file.lower().endswith(".pdf") else None
        with open(folder / f"{cfg['folder']}_gcps.csv", newline="", encoding="utf-8") as f:
            gcps = [(float(r["pixel_x"]), float(r["pixel_y"]), float(r["lat"]), float(r["lon"])) for r in csv.DictReader(f)]
        tf = fit_transform(gcps, acc.get("method", "affine"))
        source = Image.open(folder / f"{cfg['folder']}_source.png")
        labels, sheet, scale, dx, dy, iou = [], [], None, 0, 0, None
        if pdf is not None and pdf.exists():
            page = pymupdf.open(pdf)[int(acc.get("page") or cfg.get("page") or 0)]
            scale, dx, dy, iou = find_crop(page, source)
            if iou < 0.6:
                print(f"! {cfg['name']}: PDF and image don't line up (IoU {iou:.2f}); labels skipped")
            else:
                # plans cleaned of their legend / tables: text over the cut-away parts is sheet text
                keep = drawn_mask(source) if group != "dha" else None
                labels, sheet = extract_labels(page, scale, dx, dy, source.size, tf["matrix"], keep)
        pgw = [float(v) for v in (folder / f"{cfg['folder']}_EPSG3857.pgw").read_text().split()]
        warped = Image.open(folder / f"{cfg['folder']}_EPSG3857.png")
        outline = outline_from_warped(warped, pgw)
        lats = [p[0] for p in outline] or [g[2] for g in gcps]
        lons = [p[1] for p in outline] or [g[3] for g in gcps]
        counts: Dict[str, int] = {}
        for lab in labels:
            counts[lab[1]] = counts.get(lab[1], 0) + 1
        tiles = old.get(key, {}).get("tiles", 0) if args.skip_images else 0  # keep what a full build made
        if not args.skip_images:
            out_dir = args.out / key
            tiles = make_tiles(warped.convert("RGBA"), pgw, out_dir / "tiles", args.zmin, args.zmax)
            src_rgba = source.convert("RGBA")
            make_chunks(src_rgba, out_dir / "source")
            prev = src_rgba.copy()
            prev.thumbnail((2048, 2048))
            prev.save(out_dir / "preview.png", optimize=True)
        meta = {
            "key": key, "name": cfg["name"], "city": cfg["city"], "aliases": cfg["aliases"],
            "pdf": pdf.name if pdf is not None else None, "source": Path(src_file).name or None,
            "group": group, "attribution": cfg.get("attribution") or GROUPS[group]["attribution"],
            "scheme": cfg.get("scheme"), "developer": cfg.get("developer"),
            "outline": outline,
            "bounds": [round(min(lats), 6), round(min(lons), 6), round(max(lats), 6), round(max(lons), 6)],
            "center": [round((min(lats) + max(lats)) / 2, 6), round((min(lons) + max(lons)) / 2, 6)],
            "source_size": list(source.size), "chunk": CHUNK, "to_ground": tf["matrix"], "to_pixels": tf["inverse"],
            "m_per_px": round(tf["m_per_px"], 3), "zoom": [args.zmin, args.zmax], "tiles": tiles,
            "pdf_alignment": {"scale": round(scale, 5), "offset_px": [dx, dy], "overlap": round(iou, 3)} if scale else None,
            "accuracy": {"method": acc.get("method"), "gcps": len(gcps), "rmse_m": acc.get("rmse_m"),
                         "max_m": acc.get("max_m"), "residuals_m": tf["residuals_m"]},
            "label_counts": counts, "sheet_text": sheet[:600],
        }
        plans_meta.append(meta)
        all_labels[key] = labels
        print(f"{cfg['name']}: {len(labels)} labels, {tiles} tiles, alignment {iou if iou is None else round(iou, 2)}, "
              f"GCP residuals {tf['residuals_m']} m ({time.time() - t:.0f}s)")

    meta_path.write_text(json.dumps({"built": time.strftime("%Y-%m-%d"), "plans": plans_meta,
                                     "attribution": "Master plans © DHA Islamabad-Rawalpindi, Bahria Town and the societies' developers"},
                                    ensure_ascii=False, indent=1), encoding="utf-8")
    with gzip.open(labels_path, "wt", encoding="utf-8") as f:
        json.dump({"fields": ["text", "category", "lat", "lon", "font_size", "angle"], "plans": all_labels},
                  f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {meta_path} and {labels_path}")


if __name__ == "__main__":
    sys.exit(main())
