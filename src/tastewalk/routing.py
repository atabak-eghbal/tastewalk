"""Walking distances, stop ordering, scheduling and route sanity checks. All in code, no LLM.

Distance is haversine x a detour factor (streets are not straight lines). OSRM is not used:
the public demo server is car-only and not meant for production traffic.
"""

from __future__ import annotations

import itertools
import math
from datetime import date, datetime, time, timedelta

from .schemas import Place, RouteCheck, Stop

DETOUR_FACTOR = 1.3
WALK_KMH = 4.5
MAX_LEG_MIN = 30
MAX_TOTAL_WALK_MIN = 120

# Minutes to spend at a stop, by keyword in its category. First match wins.
DWELL_BY_KEYWORD = [
    ("museum", 75),
    ("gallery", 45),
    ("restaurant", 75),
    ("bar", 60),
    ("cafe", 35),
    ("coffee", 35),
    ("bakery", 20),
    ("park", 40),
    ("book", 30),
    ("record", 30),
    ("shop", 25),
    ("store", 25),
    ("market", 40),
    ("theat", 90),
    ("cinema", 120),
]
DEFAULT_DWELL = 40


def haversine_km(a: Place, b: Place) -> float:
    r = 6371.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def walk_km(a: Place, b: Place) -> float:
    return haversine_km(a, b) * DETOUR_FACTOR


def walk_minutes(a: Place, b: Place) -> int:
    return max(1, round(walk_km(a, b) / WALK_KMH * 60))


def dwell_minutes(place: Place) -> int:
    cat = (place.category or "").lower()
    for kw, minutes in DWELL_BY_KEYWORD:
        if kw in cat:
            return minutes
    return DEFAULT_DWELL


def _path_km(path: list[Place]) -> float:
    return sum(walk_km(a, b) for a, b in itertools.pairwise(path))


def order_stops(places: list[Place]) -> list[Place]:
    """Shortest open path: try each start with nearest-neighbour, then improve with 2-opt."""
    if len(places) <= 2:
        return list(places)
    best: list[Place] | None = None
    for start in range(len(places)):
        rest = places[:start] + places[start + 1 :]
        path = [places[start]]
        while rest:
            nxt = min(rest, key=lambda p: haversine_km(path[-1], p))
            rest.remove(nxt)
            path.append(nxt)
        path = _two_opt(path)
        if best is None or _path_km(path) < _path_km(best):
            best = path
    assert best is not None
    return best


def _two_opt(path: list[Place]) -> list[Place]:
    improved = True
    while improved:
        improved = False
        for i in range(1, len(path) - 1):
            for j in range(i + 1, len(path)):
                cand = path[:i] + path[i : j + 1][::-1] + path[j + 1 :]
                if _path_km(cand) < _path_km(path) - 1e-9:
                    path, improved = cand, True
    return path


def _is_open(place: Place, day: int, arrive: time, leave: time) -> bool | None:
    """True/False if Qloo gave hours, None if unknown."""
    if place.hours is None:
        return None
    for o, c in place.hours.get(day, []):
        if o <= arrive and (leave <= c or c <= o):  # c <= o: closes after midnight
            return True
    return False


def schedule(
    ordered: list[Place], start: time, day: date | None = None
) -> tuple[list[Stop], RouteCheck]:
    day = day or date.today()
    clock = datetime.combine(day, start)
    stops: list[Stop] = []
    issues: list[str] = []
    total_km, total_walk = 0.0, 0
    for i, place in enumerate(ordered):
        walk = 0
        if i:
            walk = walk_minutes(ordered[i - 1], place)
            total_km += walk_km(ordered[i - 1], place)
            total_walk += walk
            if walk > MAX_LEG_MIN:
                issues.append(f"Long walk ({walk} min) to {place.name}")
            clock += timedelta(minutes=walk)
        arrive = clock.time()
        clock += timedelta(minutes=dwell_minutes(place))
        leave = clock.time()
        if _is_open(place, day.weekday(), arrive, leave) is False:
            issues.append(f"{place.name} may be closed at {arrive:%H:%M}")
        stops.append(Stop(place=place, arrive=arrive, leave=leave, walk_minutes_from_prev=walk))
        if clock.date() != day:
            issues.append("Itinerary runs past midnight")
            break
    if total_walk > MAX_TOTAL_WALK_MIN:
        issues.append(f"Total walking {total_walk} min is over {MAX_TOTAL_WALK_MIN} min")
    check = RouteCheck(
        ok=not issues, total_walk_minutes=total_walk, total_km=round(total_km, 2), issues=issues
    )
    return stops, check
