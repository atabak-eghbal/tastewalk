"""Qloo API client: entity search, place insights, response parsing, disk caching.

Verified against the hackathon API on 2026-10-30 (see docs/research/01-qloo-api.md):
- GET /search?query=&types=urn:entity:artist -> {"results": [entity, ...]}
- GET /v2/insights?filter.type=urn:entity:place&signal.interests.entities=...
  &filter.location=POINT(lon lat)&filter.location.radius=m&filter.tags=...
  &feature.explainability=true -> {"results": {"entities": [...]}}
- Places carry location.lat/lon, query.affinity, query.explainability (per-signal scores),
  properties.hours / short_description / neighborhood / image, and typed tags.
"""

from __future__ import annotations

import difflib
import logging
import re
import unicodedata
from datetime import UTC, date, datetime, time, timedelta
from time import sleep
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from .cache import DiskCache, request_key
from .schemas import Place, ResolvedEntity, Tag

log = logging.getLogger(__name__)

# --- Endpoints (verified) ------------------------------------------------------------------
QLOO_SEARCH_PATH = "/search"
QLOO_SEARCH_TYPE_PARAM = "types"
QLOO_INSIGHTS_PATH = "/v2/insights"
PLACE_TYPE = "urn:entity:place"

# Rough city centres; used for a location filter (point + radius) and as a sanity bound.
CITY_CENTERS: dict[str, tuple[float, float]] = {
    "vancouver": (49.2820, -123.1180),  # downtown: Gastown, Chinatown, Yaletown, West End
    "montreal": (45.5048, -73.5772),  # around Plateau / downtown
}
DEFAULT_RADIUS_M = 4000
CITY_TZ = {"vancouver": "America/Vancouver", "montreal": "America/Toronto"}


CITY_UTC_OFFSET: dict[str, int] = {}  # geocoded cities: hours from UTC, estimated from longitude


def city_today(city: str) -> date:
    """Today in the city (opening hours are local; the server runs in UTC)."""
    key = city.strip().lower()
    if key in CITY_TZ:
        return datetime.now(ZoneInfo(CITY_TZ[key])).date()
    return (datetime.now(UTC) + timedelta(hours=CITY_UTC_OFFSET.get(key, 0))).date()


_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class QlooError(RuntimeError):
    pass


class QlooClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        cache: DiskCache,
        transport: httpx.BaseTransport | None = None,
        offline: bool = False,
    ):
        self.cache = cache
        self.offline = offline  # cache-only mode, for demos/tests without a key
        self._http = httpx.Client(
            base_url=base_url,
            headers={"X-Api-Key": api_key},
            timeout=20,
            transport=transport,
        )

    # --- raw calls ---------------------------------------------------------------------
    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        key = request_key("qloo", {"path": path, "params": params})
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        if self.offline:
            raise QlooError(f"No QLOO_API_KEY (or --offline) and not cached: {path} {params}")
        for wait in (1, 2, 4, 0):  # Qloo rate limit: back off and retry, then give up
            r = self._http.get(path, params=params)
            if r.status_code != 429 or not wait:
                break
            sleep(wait)
        if r.status_code >= 400:
            raise QlooError(f"Qloo {path} -> {r.status_code}: {r.text[:300]}")
        data = r.json()
        self.cache.set(key, data)
        return data

    def search(self, query: str, entity_type: str, take: int = 5) -> list[dict[str, Any]]:
        data = self._get(
            QLOO_SEARCH_PATH,
            {"query": query, QLOO_SEARCH_TYPE_PARAM: entity_type, "take": take},
        )
        return _results_list(data)

    def place_insights(
        self,
        entity_ids: list[str],
        city: str,
        take: int = 40,
        category_tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "filter.type": PLACE_TYPE,
            "signal.interests.entities": ",".join(entity_ids),
            "feature.explainability": "true",
            "take": take,
        }
        center = CITY_CENTERS.get(city.lower())
        if center:
            lat, lon = center
            params["filter.location"] = f"POINT({lon} {lat})"
            params["filter.location.radius"] = DEFAULT_RADIUS_M
        else:
            params["filter.location.query"] = city
        if category_tags:
            params["filter.tags"] = ",".join(category_tags)
        return _results_list(self._get(QLOO_INSIGHTS_PATH, params))

    def score_places(self, signal_ids: list[str], place_ids: list[str]) -> list[dict[str, Any]]:
        """Score specific places against the user's favorites (verified: `filter.results.entities`)."""
        params = {
            "filter.type": PLACE_TYPE,
            "signal.interests.entities": ",".join(signal_ids),
            "filter.results.entities": ",".join(place_ids),
            "take": len(place_ids),
        }
        return _results_list(self._get(QLOO_INSIGHTS_PATH, params))

    # --- typed helpers -----------------------------------------------------------------
    def resolve(self, query: str, entity_type: str) -> ResolvedEntity | None:
        results = self.search(query, entity_type)
        # Qloo search always returns something; keep its ranking but require a similar name,
        # so a typo still resolves ('Radiohedd') and garbage doesn't ('<img ...>' -> 'Bell X1').
        best = next((r for r in results if _similar(query, r.get("name", ""))), None)
        if best is None:
            return None
        qid = best.get("entity_id") or best.get("id")
        if not qid:
            return None
        return ResolvedEntity(
            query=query,
            qloo_id=qid,
            name=best.get("name", query),
            type=entity_type,
            tags=_parse_tags(best),
        )

    def places_for(
        self,
        entity_ids: list[str],
        city: str,
        take: int = 40,
        category_tags: list[str] | None = None,
        slot: str | None = None,
    ) -> list[Place]:
        places = []
        for raw in self.place_insights(entity_ids, city, take=take, category_tags=category_tags):
            place = parse_place(raw, slot=slot)
            if place is not None:
                places.append(place)
        return places


# --- parsing (defensive: unknown shapes are skipped, not guessed) -------------------------
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", s))


def _similar(query: str, name: str) -> bool:
    q, n = _norm(query), _norm(name)
    if not q or not n:
        return False
    return q in n or n in q or difflib.SequenceMatcher(None, q, n).ratio() >= 0.75


def _results_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    res = data.get("results", data)
    if isinstance(res, dict):
        res = res.get("entities", [])
    return res if isinstance(res, list) else []


def _parse_tags(raw: dict[str, Any]) -> list[Tag]:
    tags = []
    for t in raw.get("tags") or []:
        if isinstance(t, dict) and t.get("name"):
            tags.append(
                Tag(
                    id=str(t.get("id") or t.get("tag_id") or t["name"]),
                    name=t["name"],
                    type=t.get("type"),
                )
            )
    return tags


def _category(raw: dict[str, Any], tags: list[Tag]) -> str | None:
    for t in tags:
        if t.type == "urn:tag:category:place":
            return t.name
    sub = raw.get("subtype")
    return sub.rsplit(":", 1)[-1].replace("_", " ") if isinstance(sub, str) else None


def _parse_time(s: str) -> time | None:
    m = re.search(r"(\d{1,2}):(\d{2})", s or "")
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return time(23, 59) if h >= 24 else time(h, mi)


def _parse_hours(raw_hours: Any) -> dict[int, list[tuple[time, time]]] | None:
    """Parse {"monday": [{"opens": "T11:00:00", "closes": "T18:00:00", "closed": false}]}.

    A day listed only with closed spans maps to []; None means Qloo gave no hours at all.
    """
    if not isinstance(raw_hours, dict):
        return None
    out: dict[int, list[tuple[time, time]]] = {}
    for day, spans in raw_hours.items():
        if str(day).lower() not in _WEEKDAYS or not isinstance(spans, list):
            continue
        idx = _WEEKDAYS.index(str(day).lower())
        out[idx] = []
        for span in spans:
            if not isinstance(span, dict) or span.get("closed"):
                continue
            o, c = _parse_time(span.get("opens", "")), _parse_time(span.get("closes", ""))
            if o and c:
                out[idx].append((o, c))
    return out or None


# Place tag types worth showing as "vibe" chips (the rest are amenities, payments, etc.).
VIBE_TAG_TYPES = (
    "urn:tag:ambience:qloo",
    "urn:tag:interests:qloo",
    "urn:tag:setting:qloo",
    "urn:tag:decor:qloo",
)


def parse_place(raw: dict[str, Any], slot: str | None = None) -> Place | None:
    qid = raw.get("entity_id") or raw.get("id")
    loc = raw.get("location") or {}
    props = raw.get("properties") or {}
    if props.get("is_closed"):
        return None
    lat, lon = loc.get("lat") or loc.get("latitude"), loc.get("lon") or loc.get("longitude")
    if not qid or lat is None or lon is None:
        log.debug("skipping place without id/coords: %s", raw.get("name"))
        return None
    tags = _parse_tags(raw)
    query = raw.get("query") or {}
    affinity = query.get("affinity")
    signals = {
        s["entity_id"]: float(s["score"])
        for s in (query.get("explainability") or {}).get("signal.interests.entities", [])
        if isinstance(s, dict) and s.get("entity_id") and s.get("score") is not None
    }
    image = props.get("image")
    return Place(
        qloo_id=qid,
        name=raw.get("name", "?"),
        category=_category(raw, tags),
        lat=float(lat),
        lon=float(lon),
        address=props.get("address"),
        tags=tags,
        affinity=float(affinity) if affinity is not None else None,
        hours=_parse_hours(props.get("hours")),
        slot=slot,
        neighborhood=props.get("neighborhood"),
        description=props.get("short_description") or props.get("description"),
        image_url=image.get("url") if isinstance(image, dict) else None,
        vibe=[t.name for t in tags if t.type in VIBE_TAG_TYPES][:6],
        signal_scores=signals,
    )
