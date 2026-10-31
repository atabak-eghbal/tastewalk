"""Any city in the world: name -> centre, map box and local date, via OpenStreetMap (cached).

Vancouver and Montreal are configured in code; any other city is geocoded once with Nominatim
and registered in the same tables the agents already use (Qloo location filter, OpenStreetMap
search box, local date for opening hours, city words ignored when matching place names).
"""

from __future__ import annotations

import re

from . import fact_check, qloo
from . import osm as osm_mod
from .osm import OSMClient

MAX_BOX_DEG = 0.25  # keep fact-check lookups local even when a city's boundary is huge


def ensure_city(city: str, osm: OSMClient | None) -> str | None:
    """Register `city` if needed. Returns an error message, or None when the city is ready."""
    key = city.strip().lower()
    if key in qloo.CITY_CENTERS:
        return None
    hit = osm.geocode(city) if osm else None
    if hit is None:
        return f"Couldn't find a city called '{city}'. Try the city's English name, e.g. Seoul."
    lat, lon = float(hit["lat"]), float(hit["lon"])
    south, north, west, east = (float(x) for x in hit["boundingbox"])
    d = MAX_BOX_DEG
    west, east = max(west, lon - d), min(east, lon + d)
    south, north = max(south, lat - d), min(north, lat + d)
    qloo.CITY_CENTERS[key] = (lat, lon)
    qloo.CITY_UTC_OFFSET[key] = round(lon / 15)  # local date only; exact zones for known cities
    osm_mod.CITY_VIEWBOX[key] = f"{west},{north},{east},{south}"
    fact_check.GENERIC.update(re.findall(r"[a-z0-9]+", key))
    return None
