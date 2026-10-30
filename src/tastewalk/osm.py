"""OpenStreetMap (Nominatim) lookup: does a place exist at all, when Qloo doesn't know it?

Used only by the fact-checker, so "not in Qloo" is never mistaken for "made up". Follows the
Nominatim usage policy: an identifying User-Agent, at most one request per second, and every
answer cached on disk. Network errors return None ("not checked"), never "doesn't exist".
"""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx

from .cache import DiskCache, request_key

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "TasteWalk/1.0 (Qloo hackathon demo; https://github.com/atabak-eghbal/tastewalk)"
# lon_min, lat_max, lon_max, lat_min
CITY_VIEWBOX = {"montreal": "-73.98,45.71,-73.47,45.40"}
MIN_INTERVAL_S = 1.1

_lock = threading.Lock()
_last_call = 0.0


class OSMClient:
    def __init__(self, cache: DiskCache, transport: httpx.BaseTransport | None = None):
        self.cache = cache
        self._http = httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=10, transport=transport
        )

    def search(self, query: str, city: str) -> list[dict[str, Any]] | None:
        params: dict[str, Any] = {"q": f"{query}, {city}", "format": "jsonv2", "limit": 5}
        box = CITY_VIEWBOX.get(city.lower())
        if box:
            params |= {"viewbox": box, "bounded": 1}
        key = request_key("osm", params)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        global _last_call
        try:
            with _lock:
                wait = MIN_INTERVAL_S - (time.monotonic() - _last_call)
                if wait > 0:
                    time.sleep(wait)
                _last_call = time.monotonic()
                r = self._http.get(NOMINATIM_URL, params=params)
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError):
            return None
        self.cache.set(key, data)
        return data
