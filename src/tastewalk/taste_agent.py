"""Taste agent: resolves the user's favorites to Qloo entities, then asks Qloo for matching places.

This is where Qloo does the work the LLM can't: entity resolution plus taste-graph place
recommendations within a location. The output candidates are the only places downstream
agents may use.
"""

from __future__ import annotations

from collections import Counter

from .qloo import CITY_CENTERS, QlooClient, QlooError
from .routing import haversine_km
from .schemas import Place, TasteProfile, UserInput

MAX_KM_FROM_CENTER = 8.0


class NoTasteSignal(RuntimeError):
    pass


def build_profile(qloo: QlooClient, user: UserInput) -> TasteProfile:
    entities, unresolved = [], []
    errors: list[QlooError] = []
    for fav in user.favorites:
        try:
            ent = qloo.resolve(fav.name, fav.type.value)
        except QlooError as e:
            errors.append(e)
            ent = None
        if ent is None:
            unresolved.append(fav.name)
        else:
            entities.append(ent)
    if not entities and errors:
        raise errors[-1]  # an API/config problem, not "no match"
    counts = Counter()
    by_id = {}
    for ent in entities:
        for t in ent.tags:
            counts[t.id] += 1
            by_id[t.id] = t
    top_tags = [by_id[tid] for tid, _ in counts.most_common(12)]
    return TasteProfile(entities=entities, unresolved=unresolved, top_tags=top_tags)


def find_candidates(qloo: QlooClient, user: UserInput, profile: TasteProfile) -> list[Place]:
    if not profile.entities:
        raise NoTasteSignal("None of the favorites matched a Qloo entity")
    places = qloo.places_for([e.qloo_id for e in profile.entities], user.city)
    center = CITY_CENTERS.get(user.city.lower())
    if center:
        c = Place(qloo_id="_center", name="center", lat=center[0], lon=center[1])
        places = [p for p in places if haversine_km(c, p) <= MAX_KM_FROM_CENTER]
    # De-duplicate by id, keep Qloo's ranking order.
    seen, unique = set(), []
    for p in places:
        if p.qloo_id not in seen:
            seen.add(p.qloo_id)
            unique.append(p)
    return unique
