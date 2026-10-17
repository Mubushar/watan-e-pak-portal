"""
Ad networks and app-side ad tracking.

The portal sells its own ad space to vendors (direct ads, ``content.py``); when a slot
has no direct ad, the app can fill it from Google:

* **AdSense** — the web build only (Google does not allow AdSense inside mobile or
  desktop apps).
* **AdMob** — the Android and iOS apps (a banner above the tab bar).
* The Windows / macOS desktop app shows direct ads only.

Settings (environment variables, or ``backend/.env``)::

    ADS_ADSENSE_CLIENT=ca-pub-1234567890123456   # AdSense publisher id (web)
    ADS_ADSENSE_SLOT_HOME=1234567890             # ad unit ids for each placement
    ADS_ADSENSE_SLOT_EXPLORE=
    ADS_ADSENSE_SLOT_DETAIL=
    ADS_ADMOB_ANDROID_BANNER=ca-app-pub-…/…      # AdMob banner unit ids
    ADS_ADMOB_IOS_BANNER=ca-app-pub-…/…
    ADS_ADMOB_TESTING=1                          # 1 = Google's test ads (no earnings); 0 = live
    ADS_CONTACT_EMAIL=ads@yourdomain.pk          # "Advertise with us"

The AdMob *app* id is not set here: it is compiled into the Android manifest and the
iOS Info.plist (see the Administration Guide).
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, Optional, Tuple

import envfile  # noqa: F401  (loads backend/.env)


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


ADSENSE_CLIENT = os.getenv("ADS_ADSENSE_CLIENT", "").strip()
ADSENSE_SLOTS = {
    "home": os.getenv("ADS_ADSENSE_SLOT_HOME", "").strip(),
    "explore": os.getenv("ADS_ADSENSE_SLOT_EXPLORE", "").strip(),
    "detail": os.getenv("ADS_ADSENSE_SLOT_DETAIL", "").strip(),
}
ADMOB_TESTING = _flag("ADS_ADMOB_TESTING", "1")
ADMOB_BANNERS = {
    "android": os.getenv("ADS_ADMOB_ANDROID_BANNER", "").strip(),
    "ios": os.getenv("ADS_ADMOB_IOS_BANNER", "").strip(),
}
# Google's published test units: always safe to show, never pay out.
ADMOB_TEST_BANNERS = {
    "android": "ca-app-pub-3940256099942544/9214589741",
    "ios": "ca-app-pub-3940256099942544/2435281174",
}
CONTACT_EMAIL = os.getenv("ADS_CONTACT_EMAIL", "").strip()


def config(house_title: str, house_body: str, sponsored_label: str) -> Dict[str, Any]:
    """What the app needs to render ad slots (only public ids)."""
    adsense = None
    if ADSENSE_CLIENT:
        adsense = {"client": ADSENSE_CLIENT, "slots": {k: v for k, v in ADSENSE_SLOTS.items() if v}}
    banners = ADMOB_TEST_BANNERS if ADMOB_TESTING else {k: v for k, v in ADMOB_BANNERS.items() if v}
    admob = {"testing": ADMOB_TESTING, "banner": banners} if banners else None
    return {
        "direct": True,
        "sponsored_label": sponsored_label,
        "advertise": {"title": house_title, "body": house_body, "email": CONTACT_EMAIL or None},
        "adsense": adsense,
        "admob": admob,
    }


def ads_txt() -> Optional[str]:
    """The ads.txt line Google needs at the root of the web site, if AdSense is set up."""
    if not ADSENSE_CLIENT.startswith("ca-pub-"):
        return None
    return f"google.com, {ADSENSE_CLIENT[3:]}, DIRECT, f08c47fec0942fa0\n"


# ---------------------------------------------------------------- app-side tracking

# Count an impression from the same viewer at most once per 10 minutes and a click once
# per 30 minutes, so refreshing or tapping repeatedly doesn't bill the advertiser.
WINDOWS = {"impression": 600.0, "click": 1800.0}
_seen: Dict[Tuple[str, str, str], float] = {}
_lock = threading.Lock()


def first_time(viewer: str, ad_id: str, event: str) -> bool:
    """True if this viewer's ``event`` on ``ad_id`` should be counted now."""
    now = time.monotonic()
    key = (viewer, ad_id, event)
    with _lock:
        if len(_seen) > 50_000:  # forget expired entries
            for k in [k for k, t in _seen.items() if now - t >= WINDOWS.get(k[2], 600.0)]:
                del _seen[k]
        last = _seen.get(key)
        if last is not None and now - last < WINDOWS[event]:
            return False
        _seen[key] = now
        return True


def reset() -> None:
    """Clear the tracking memory (tests)."""
    with _lock:
        _seen.clear()
