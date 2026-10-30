"""Fact-checker: audits the LLM-only plan with Qloo data, so the comparison is measured, not claimed.

For each place the LLM named, Qloo search looks it up (strict name match, near the city); found
places get their real coordinates and hours, and one Qloo insights call scores them against the
user's favorites on the same affinity scale as our route. Walking distance and opening hours use
the same code as our planner. No LLM is involved.
"""

from __future__ import annotations

import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta

from .qloo import CITY_CENTERS, PLACE_TYPE, QlooClient, parse_place
from .routing import haversine_km, is_open, path_km, walk_minutes
from .schemas import BaselineAudit, BaselineItinerary, Itinerary, Place, StopCheck, TasteProfile

MAX_KM_FROM_CENTER = 25.0
DEFAULT_VISIT_MIN = 60
# Words that say what a place is, not which place it is: never enough for a match on their own.
_GENERIC_WORDS = (
    "the a an and et of le la les l de du des d montreal mtl inc "
    "cafe coffee restaurant bar pub store shop boutique record records bookstore book books librairie museum musee park "
    "parc gallery galerie market marche brasserie bistro bakery boulangerie club"
)
GENERIC = set(_GENERIC_WORDS.split())


def _distinctive(name: str) -> list[str]:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+", s.replace("'s", ""))
    return [w for w in words if w not in GENERIC]


def same_place(llm_name: str, qloo_name: str) -> bool:
    """Same distinctive words, or one name extends the other ('Café Olimpico - Vieux-Montréal').

    Extending at the front is not allowed: 'SAQ-Marché Jean-Talon' (a liquor store inside the
    market) is not 'Marché Jean-Talon'. A wrong match is worse than no match: it would make us
    claim the LLM's place is closed when it is not.
    """
    a, b = _distinctive(llm_name), _distinctive(qloo_name)
    if not a or not b:
        return False
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return set(a) == set(b) or long_[: len(short)] == short


def _parse_times(text: str | None) -> tuple[time, time] | None:
    """'11:00 - 12:30', '2:00 PM', '14h00'... -> (arrive, leave); leave defaults to +60 min."""
    if not text:
        return None
    found = re.findall(r"(\d{1,2})(?:[:h](\d{2}))?\s*([ap]\.?m\.?)?", text.lower())
    times = []
    for h, m, ampm in found:
        hour, minute = int(h), int(m or 0)
        if ampm.startswith("p") and hour < 12:
            hour += 12
        if ampm.startswith("a") and hour == 12:
            hour = 0
        if hour < 24 and minute < 60 and (m or ampm):
            times.append(time(hour, minute))
    if not times:
        return None
    arrive = times[0]
    leave = (
        times[1]
        if len(times) > 1
        else (datetime.combine(date.today(), arrive) + timedelta(minutes=DEFAULT_VISIT_MIN)).time()
    )
    return arrive, leave


LODGING = ("hotel", "hostel", "inn", "auberge")


def name_variants(name: str) -> list[str]:
    """LLMs decorate names ('Muji Montréal – Rue Saint-Denis'): try the whole, then the name part.

    Trailing parts are usually a street or neighbourhood, which would match the wrong place.
    """
    clean = re.sub(r"[\u2010-\u2015]", "-", name).strip()
    parts = [p.strip() for p in re.split(r"\s+-\s+|[(),:]", clean) if p.strip()]
    return list(dict.fromkeys([clean, *parts[:1]]))


def find_place(qloo: QlooClient, name: str, city: str, category: str | None = None) -> Place | None:
    center = CITY_CENTERS.get(city.lower())
    wants_lodging = any(w in f"{name} {category or ''}".lower() for w in LODGING)
    for variant in name_variants(name):
        for raw in qloo.search(f"{variant} {city}", PLACE_TYPE, take=5):
            place = parse_place(raw)
            if place is None or not same_place(variant, place.name):
                continue
            categories = " ".join(t.name for t in place.tags if "category" in t.type).lower()
            if not wants_lodging and any(w in categories for w in LODGING):
                continue  # 'Le Saint-Sulpice' the bar is not the Saint-Sulpice Hotel
            if center:
                c = Place(qloo_id="center", name="center", lat=center[0], lon=center[1])
                if haversine_km(place, c) > MAX_KM_FROM_CENTER:
                    continue
            return place
    return None


def _avg(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 3) if xs else None


def fact_check(
    qloo: QlooClient,
    baseline: BaselineItinerary,
    profile: TasteProfile,
    itin: Itinerary,
    day: date | None = None,
) -> BaselineAudit:
    weekday = (day or date.today()).weekday()
    with ThreadPoolExecutor(max_workers=6) as pool:
        places = list(
            pool.map(lambda s: find_place(qloo, s.name, baseline.city, s.category), baseline.stops)
        )

    found_ids = [p.qloo_id for p in places if p]
    scores: dict[str, float] = {}
    if found_ids and profile.entities:
        for raw in qloo.score_places([e.qloo_id for e in profile.entities], found_ids):
            aff = (raw.get("query") or {}).get("affinity")
            if raw.get("entity_id") and aff is not None:
                scores[raw["entity_id"]] = float(aff)

    checks, prev = [], None
    for stop, place in zip(baseline.stops, places, strict=True):
        if place is None:
            checks.append(StopCheck(name=stop.name, found=False))
            continue
        span = _parse_times(stop.time)
        checks.append(
            StopCheck(
                name=stop.name,
                found=True,
                qloo_id=place.qloo_id,
                qloo_name=place.name,
                address=place.address,
                lat=place.lat,
                lon=place.lon,
                open=is_open(place, weekday, *span) if span else None,
                affinity=scores.get(place.qloo_id),
                walk_minutes_from_prev=walk_minutes(prev, place) if prev else None,
            )
        )
        prev = place

    found = [p for p in places if p]
    legs = [c.walk_minutes_from_prev for c in checks if c.walk_minutes_from_prev is not None]
    return BaselineAudit(
        stops=checks,
        found=len(found),
        total=len(checks),
        closed=sum(1 for c in checks if c.open is False),
        walk_km=round(path_km(found), 2),
        longest_leg_min=max(legs, default=0),
        avg_affinity=_avg([c.affinity for c in checks if c.affinity is not None]),
        qloo_avg_affinity=_avg(
            [s.place.affinity for s in itin.stops if s.place.affinity is not None]
        ),
        qloo_km=itin.total_km,
    )
