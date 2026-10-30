"""Fact-checker: audits the LLM-only plan with Qloo data, so the comparison is checked, not claimed.

For each place the LLM named, Qloo search looks it up (strict name match, near the city). Located
places get their coordinates and hours, and one Qloo insights call scores them against the user's
favorites. Places Qloo doesn't know are looked up in OpenStreetMap, so "not in Qloo" is never
presented as "made up". Chains with several matching branches are marked ambiguous and get no
hours or walking claims. Walking and opening hours use the same code as our planner. No LLM.
"""

from __future__ import annotations

import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta

from .osm import OSMClient
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


_SYNONYMS = {"st": "saint", "ste": "sainte", "mt": "mont", "mount": "mont"}


def _distinctive(name: str) -> list[str]:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+", s.replace("'s", ""))
    return [_SYNONYMS.get(w, w) for w in words if w not in GENERIC]


def _base(name: str) -> str:
    """'Café Olimpico - Vieux-Montréal' -> 'Café Olimpico' (branch or location suffix dropped)."""
    clean = re.sub(r"[\u2010-\u2015]", "-", name)
    return re.split(r"\s+-\s+|\(", clean)[0]


def same_place(llm_name: str, qloo_name: str) -> bool:
    """Same distinctive words, ignoring a branch suffix ('Café Olimpico - Vieux-Montréal').

    No partial matches: 'Atwater Market' is not 'Atwater Cocktail Club', 'Mile End' is not
    'Mile End Kitchen', and 'SAQ-Marché Jean-Talon' (a liquor store inside the market) is not
    'Marché Jean-Talon'. A wrong match is worse than no match: it would make us claim things
    about the wrong place.
    """
    a, b = _distinctive(llm_name), _distinctive(qloo_name)
    if not a or not b:
        return False
    return set(a) == set(b) or set(a) == set(_distinctive(_base(qloo_name)))


def _parse_times(text: str | None) -> tuple[time, time] | None:
    """'11:00 - 12:30', '2:00-3:30 PM', '2 - 4 PM', '14h00'... -> (arrive, leave).

    A trailing AM/PM also applies to an earlier bare time ('2:00-3:30 PM' is 14:00-15:30).
    Leave defaults to arrive + 60 min.
    """
    if not text:
        return None
    found = re.findall(r"(\d{1,2})(?:[:h](\d{2}))?\s*([ap])?\.?m?\.?", text.lower())
    raw = [
        (int(h), int(m or 0), bool(m), ap) for h, m, ap in found if int(h) < 24 and int(m or 0) < 60
    ]
    # Inherit AM/PM from the next time that has one.
    times: list[time] = []
    next_ap = ""
    for h, m, has_min, own_ap in reversed(raw):
        ap = own_ap or next_ap
        next_ap = ap
        if not (has_min or ap):
            continue  # a bare number like "6 stops" is not a time
        hour = h + 12 if ap == "p" and h < 12 else (0 if ap == "a" and h == 12 else h)
        if not own_ap and times and time(hour, m) > times[-1]:
            hour = h  # '11:00-1:00 PM': the PM belongs to 1:00 only
        times.append(time(hour, m))
    times.reverse()
    if not times:
        return None
    arrive = times[0]
    leave = (
        times[1]
        if len(times) > 1 and times[1] > arrive
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


def find_place(
    qloo: QlooClient, name: str, city: str, category: str | None = None
) -> tuple[Place | None, bool]:
    """(place, ambiguous). Ambiguous: several distinct branches match the name (a chain)."""
    center = CITY_CENTERS.get(city.lower())
    wants_lodging = any(w in f"{name} {category or ''}".lower() for w in LODGING)
    for variant in name_variants(name):
        matches: list[Place] = []
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
            if all(haversine_km(place, m) > 0.2 for m in matches):
                matches.append(place)
        if matches:
            return matches[0], len(matches) > 1
    return None, False


def osm_variants(name: str) -> list[str]:
    """Generous on purpose ('not found anywhere' is a strong claim): also try the core name.

    'Phonopolis Vinyl Record Store' -> 'Phonopolis'; 'Nike Montreal Flagship' -> 'Nike'.
    """
    first = name_variants(name)[-1]
    core = _distinctive(first)
    out = [first]
    if len(core) > 1:
        out.append(" ".join(core[:2]))
    if core and len(core[0]) >= 4:
        out.append(core[0])
    return list(dict.fromkeys(out))


def in_osm(osm: OSMClient, name: str, city: str) -> bool | None:
    """Does OpenStreetMap have a place with this name in the city? None if the lookup failed."""
    for variant in osm_variants(name):
        results = osm.search(variant, city)
        if results is None:
            return None
        if any(same_place(variant, r.get("name") or "") for r in results):
            return True
    return False


def _avg(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 3) if xs else None


def fact_check(
    qloo: QlooClient,
    baseline: BaselineItinerary,
    profile: TasteProfile,
    itin: Itinerary,
    day: date | None = None,
    osm: OSMClient | None = None,
) -> BaselineAudit:
    weekday = (day or date.today()).weekday()
    with ThreadPoolExecutor(max_workers=6) as pool:
        lookups = list(
            pool.map(lambda s: find_place(qloo, s.name, baseline.city, s.category), baseline.stops)
        )

    sure = [p for p, ambiguous in lookups if p and not ambiguous]
    scores: dict[str, float] = {}
    if sure and profile.entities:
        for raw in qloo.score_places(
            [e.qloo_id for e in profile.entities], [p.qloo_id for p in sure]
        ):
            aff = (raw.get("query") or {}).get("affinity")
            if raw.get("entity_id") and aff is not None:
                scores[raw["entity_id"]] = float(aff)

    checks, prev = [], None
    for stop, (place, ambiguous) in zip(baseline.stops, lookups, strict=True):
        if place is None:
            known = in_osm(osm, stop.name, baseline.city) if osm else None
            checks.append(StopCheck(name=stop.name, found=False, in_osm=known))
            continue
        if ambiguous:
            checks.append(
                StopCheck(name=stop.name, found=True, ambiguous=True, qloo_name=_base(place.name))
            )
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

    legs = [c.walk_minutes_from_prev for c in checks if c.walk_minutes_from_prev is not None]
    return BaselineAudit(
        stops=checks,
        found=sum(1 for c in checks if c.found),
        in_osm=sum(1 for c in checks if c.in_osm),
        nowhere=sum(1 for c in checks if c.in_osm is False),
        total=len(checks),
        closed=sum(1 for c in checks if c.open is False),
        hours_checked=sum(1 for c in checks if c.open is not None),
        walk_km=round(path_km(sure), 2),
        longest_leg_min=max(legs, default=0),
        avg_affinity=_avg([c.affinity for c in checks if c.affinity is not None]),
        qloo_avg_affinity=_avg(
            [s.place.affinity for s in itin.stops if s.place.affinity is not None]
        ),
        qloo_km=itin.total_km,
    )
