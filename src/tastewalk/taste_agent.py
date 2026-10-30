"""Taste agent: resolves the user's favorites to Qloo entities, then asks Qloo for matching places.

This is where Qloo does the work the LLM can't: entity resolution plus taste-graph place
recommendations within a location. Besides one general query, it asks Qloo for each "slot" of
a day (coffee, culture, shopping, food, drinks) using category tag filters, so the planner can
build a varied day. These candidates are the only places downstream agents may use.
"""

from __future__ import annotations

from collections import Counter

from .qloo import CITY_CENTERS, QlooClient, QlooError
from .routing import haversine_km
from .schemas import Place, TasteProfile, UserInput

MAX_KM_FROM_CENTER = 6.0
GENERAL_TAKE = 30
SLOT_TAKE = 15
# Categories that are not a place to visit on a walk (matched as substrings, lowercase).
SKIP_CATEGORIES = (
    "hotel",
    "event venue",
    "university",
    "school",
    "college",
    "office",
    "parking",
    "apartment",
    "hostel",
    "inn",
    "residence",
    "wedding",
    "conference",
    "corporate",
)

# Day slots in the order they usually happen, with Qloo category tag IDs (verified via /v2/tags).
SLOTS: dict[str, list[str]] = {
    "coffee": ["urn:tag:category:place:cafe", "urn:tag:category:place:bakery"],
    "culture": ["urn:tag:category:place:museum", "urn:tag:category:place:art_gallery"],
    "shopping": [
        "urn:tag:category:place:book_store",
        "urn:tag:category:place:record_store",
        "urn:tag:category:place:clothing_store",
    ],
    "food": ["urn:tag:category:place:restaurant"],
    "drinks": ["urn:tag:category:place:bar", "urn:tag:category:place:cocktail_bar"],
}
SLOT_ORDER = list(SLOTS)


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
    counts: Counter[str] = Counter()
    by_id = {}
    for ent in entities:
        for t in ent.tags:
            counts[t.id] += 1
            by_id[t.id] = t
    # Only themes shared by at least two favorites; a single film's plot tags are noise.
    shared = [by_id[tid] for tid, n in counts.most_common() if n >= 2]
    top_tags = list({t.name.lower(): t for t in reversed(shared)}.values())[::-1][:12]
    return TasteProfile(entities=entities, unresolved=unresolved, top_tags=top_tags)


def find_candidates(qloo: QlooClient, user: UserInput, profile: TasteProfile) -> list[Place]:
    if not profile.entities:
        raise NoTasteSignal("None of the favorites matched a Qloo entity")
    ids = [e.qloo_id for e in profile.entities]
    places: list[Place] = []
    for slot, tags in SLOTS.items():
        places += qloo.places_for(ids, user.city, take=SLOT_TAKE, category_tags=tags, slot=slot)
    places += qloo.places_for(ids, user.city, take=GENERAL_TAKE)

    center = CITY_CENTERS.get(user.city.lower())
    if center:
        c = Place(qloo_id="_center", name="center", lat=center[0], lon=center[1])
        places = [p for p in places if haversine_km(c, p) <= MAX_KM_FROM_CENTER]
    places = [
        p for p in places if not any(k in (p.category or "").lower() for k in SKIP_CATEGORIES)
    ]
    # De-duplicate by id; keep the first copy (slot queries come first, so slots stick).
    seen, unique = set(), []
    for p in places:
        if p.qloo_id not in seen:
            seen.add(p.qloo_id)
            unique.append(p)
    unique.sort(key=lambda p: -(p.affinity or 0))
    return unique
