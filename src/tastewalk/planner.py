"""Planner agent: picks a varied, walkable subset of Qloo candidates and schedules it.

Code narrows candidates to a compact walking area that covers the most day slots; the LLM
(optional) picks which stops make a good day; code validates the picks are real candidate IDs,
orders them (coffee first, drinks last, shortest walk in between) and computes times.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date

from pydantic import BaseModel

from .llm import LLM, LLMError
from .qloo import city_today
from .routing import is_open, order_day, path_km, schedule, walk_km
from .schemas import Itinerary, Place, TasteProfile, UserInput
from .taste_agent import SLOT_ORDER

log = logging.getLogger(__name__)

POOL_RADIUS_KM = 1.2
NEARBY_KM = 0.6  # extra candidates this close to the pool can fill a missing kind of stop
DAY_ORDER_MAX_DETOUR = 1.3  # accept day-rhythm order if <= 30% longer than shortest
POOL_SIZE = 20
MAX_PER_CATEGORY = 2
SLOT_BONUS = 1.5  # worth more than one extra high-affinity place of a slot we already have


MEAL_WORDS = (
    "restaurant",
    "steak",
    "diner",
    "pizza",
    "sushi",
    "bbq",
    "barbecue",
    "bistro",
    "food",
    "deli",
    "eatery",
    "ramen",
    "noodle",
    "burger",
    "grill",
    "taqueria",
)
DRINK_WORDS = {"bar", "pub", "lounge", "cocktail", "brewery", "wine", "tavern", "nightclub"}
COFFEE_WORDS = ("cafe", "café", "coffee", "bakery", "tea", "patisserie", "pâtisserie")
KIND_SLOT = {"meal": "food", "drinks": "drinks", "coffee": "coffee"}
# Product choice: TasteWalk routes you to independent places. Qloo's popularity score can't do
# this (it rates La Belle Province 0.32 and the local Olive et Gourmando 0.99), so: a short list.
CHAINS = {
    "cos",
    "zara home",
    "h&m",
    "urban outfitters",
    "zara",
    "uniqlo",
    "gap",
    "starbucks",
    "tim hortons",
    "mcdonald's",
    "la belle province",
    "subway",
    "sephora",
    "lululemon",
    "apple store",
    "foot locker",
    "a&w",
    "second cup",
    "dollarama",
    "winners",
    "old navy",
}


def is_chain(p: Place) -> bool:
    return p.name.lower().split(" - ")[0].strip() in CHAINS


def kind(p: Place) -> str:
    """meal | drinks | coffee | other, from Qloo's category ('Italian restaurant', 'Lounge bar')."""
    cat = (p.category or "").lower()
    if "restaurant" in cat:
        return "meal"
    if DRINK_WORDS & set(re.findall(r"\w+", cat)) or "night club" in cat:
        return "drinks"
    if any(w in cat for w in MEAL_WORDS):
        return "meal"
    if any(w in cat for w in COFFEE_WORDS):
        return "coffee"
    return "other"


def balance(chosen: list[Place], pool: list[Place], n: int) -> list[Place]:
    """A day's rhythm: one coffee, one meal and one drinks stop when the pool has them (two
    coffees and meals from 7 stops); the rest culture and shopping; no chains. The planner's own
    picks come first. Never breaks the quotas: a shorter day beats three restaurants in a row.
    Slots are relabelled from the category, so a restaurant is never the "coffee" stop."""
    cap = 2 if n >= 7 else 1
    quota = {"meal": cap, "drinks": 1, "coffee": cap}
    options = [p for p in [*chosen, *pool] if not is_chain(p)]
    kept: list[Place] = []
    for k in ("coffee", "meal", "drinks"):
        first = next((p for p in options if kind(p) == k), None)
        if first is not None and len(kept) < n:
            kept.append(first)
    count = Counter(kind(p) for p in kept)
    for p in options:
        if len(kept) >= n:
            break
        k = kind(p)
        if p in kept or count[k] >= quota.get(k, n):
            continue
        kept.append(p)
        count[k] += 1
    return [_relabel(p) for p in kept]


def _relabel(p: Place) -> Place:
    k = kind(p)
    if k in KIND_SLOT:
        return p.model_copy(update={"slot": KIND_SLOT[k]})
    if p.slot in KIND_SLOT.values():
        return p.model_copy(update={"slot": None})
    return p


class PlannerPicks(BaseModel):
    qloo_ids: list[str]
    reasoning: str = ""


def _score(p: Place, rank: int) -> float:
    return p.affinity if p.affinity is not None else 1.0 / (1 + rank)


def compact_pool(candidates: list[Place]) -> list[Place]:
    """Choose the anchor whose walkable neighbourhood has the best taste score and slot mix."""
    if not candidates:
        return []
    scores = {p.qloo_id: _score(p, i) for i, p in enumerate(candidates)}
    best_pool: list[Place] = []
    best_total = -1.0
    for anchor in candidates:
        near = [p for p in candidates if walk_km(anchor, p) <= POOL_RADIUS_KM]
        pool = sorted(near, key=lambda p: -scores[p.qloo_id])[:POOL_SIZE]
        slots = {p.slot for p in pool if p.slot}
        total = sum(scores[p.qloo_id] for p in pool) + SLOT_BONUS * len(slots)
        if total > best_total:
            best_pool, best_total = pool, total
    return best_pool


def pick_deterministic(pool: list[Place], n: int) -> list[Place]:
    """Best place for each day slot first, then the highest-affinity rest, capped per category."""
    picks: list[Place] = []
    for slot in SLOT_ORDER:
        best = next((p for p in pool if p.slot == slot), None)
        if best and len(picks) < n:
            picks.append(best)
    per_cat = Counter((p.category or "other").lower() for p in picks)
    per_slot = Counter(p.slot for p in picks if p.slot)
    for p in pool:
        if len(picks) >= n:
            break
        cat = (p.category or "other").lower()
        if p in picks or per_cat[cat] >= MAX_PER_CATEGORY:
            continue
        if p.slot and per_slot[p.slot] >= MAX_PER_CATEGORY:
            continue
        per_cat[cat] += 1
        if p.slot:
            per_slot[p.slot] += 1
        picks.append(p)
    return picks


def pick_with_llm(llm: LLM, pool: list[Place], profile: TasteProfile, n: int) -> list[Place]:
    lines = [
        f"- {p.qloo_id} | {p.name} | slot: {p.slot or '-'} | {p.category or '?'} | "
        f"affinity {p.affinity or 0:.2f} | {(p.description or '')[:120]}"
        for p in pool
    ]
    favs = ", ".join(e.name for e in profile.entities)
    picks = llm.json(
        system=(
            "You plan a one-day walking itinerary. Choose ONLY from the candidate list, by ID. "
            "Prefer variety across slots (coffee, culture, shopping, food, drinks), higher "
            "affinity, and places that feel distinctive rather than generic. Never invent places."
        ),
        user=f"User loves: {favs}\nPick exactly {n} stops.\nCandidates:\n" + "\n".join(lines),
        schema=PlannerPicks,
    )
    by_id = {p.qloo_id: p for p in pool}
    chosen = [by_id[i] for i in dict.fromkeys(picks.qloo_ids) if i in by_id]
    dropped = [i for i in picks.qloo_ids if i not in by_id]
    if dropped:
        log.warning("planner LLM returned unknown IDs, dropped: %s", dropped)
    return chosen


def order_by_day(chosen: list[Place]) -> list[Place]:
    """Drinks always last (nobody starts a day at a bar; the pool is compact, so the cost is
    small). Coffee first too, unless that makes the walk much longer."""
    first = next((p for p in chosen if p.slot == "coffee"), None)
    last = next((p for p in chosen if p.slot == "drinks"), None) or next(
        (p for p in chosen if p.slot == "food"), None
    )
    day = order_day(chosen, first, last)
    no_coffee_pin = order_day(chosen, None, last)
    if path_km(day) <= DAY_ORDER_MAX_DETOUR * path_km(no_coffee_pin) + 0.2:
        return day
    return no_coffee_pin


def schedule_open(chosen: list[Place], pool: list[Place], user: UserInput, day: date):
    """Schedule; swap any stop that is closed on arrival for an open pool place (same slot first)."""
    chosen = list(chosen)
    for _ in range(2 * len(chosen) + 2):
        stops, check = schedule(order_by_day(chosen), user.start_time, day)
        closed = next(
            (s for s in stops if is_open(s.place, day.weekday(), s.arrive, s.leave) is False), None
        )
        if closed is None:
            return stops, check
        bad = closed.place
        taken = {kind(p) for p in chosen if p is not bad} - {"other"}
        spares = [
            p
            for p in pool
            if p not in chosen
            and not is_chain(p)
            and (kind(p) == kind(bad) or kind(p) not in taken)
        ]
        spares.sort(key=lambda p: (kind(p) != kind(bad), kind(p) in taken, -(p.affinity or 0)))
        fit = next(
            (
                p
                for p in spares
                if is_open(p, day.weekday(), closed.arrive, closed.leave) is not False
            ),
            None,
        )
        if fit is None and len(chosen) <= 2:
            return stops, check  # keep it; the route check will flag it
        chosen = (
            [fit if p is bad else p for p in chosen] if fit else [p for p in chosen if p is not bad]
        )
    return stops, check


def plan(
    candidates: list[Place],
    profile: TasteProfile,
    user: UserInput,
    llm: LLM | None,
    day: date | None = None,
) -> Itinerary:
    n = user.max_stops
    pool = compact_pool(candidates)
    chosen: list[Place] = []
    if llm is not None:
        try:
            chosen = pick_with_llm(llm, pool, profile, n)
        except LLMError as e:
            log.warning("planner LLM failed, using deterministic picks: %s", e)
    if len(chosen) < min(n, len(pool)):
        extra = [p for p in pick_deterministic(pool, len(pool)) if p not in chosen]
        chosen += extra[: n - len(chosen)]
    # Fill from the compact pool first, then from other candidates a short walk from it.
    nearby = [
        c
        for c in candidates
        if c not in pool and pool and min(walk_km(c, p) for p in pool) <= NEARBY_KM
    ]
    nearby.sort(key=lambda p: -(p.affinity or 0))
    pool = pool + nearby
    chosen = balance(chosen, pick_deterministic(pool, len(pool)), n)
    pool = [_relabel(p) for p in pool]
    stops, check = schedule_open(chosen, pool, user, day or city_today(user.city))
    return Itinerary(
        city=user.city,
        start_time=user.start_time,
        stops=stops,
        total_km=check.total_km,
        total_walk_minutes=check.total_walk_minutes,
        check=check,
    )
