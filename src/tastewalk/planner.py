"""Planner agent: picks a varied, walkable subset of Qloo candidates and schedules it.

Code narrows candidates to a compact walking area that covers the most day slots; the LLM
(optional) picks which stops make a good day; code validates the picks are real candidate IDs,
orders them (coffee first, drinks last, shortest walk in between) and computes times.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date

from pydantic import BaseModel

from .llm import LLM, LLMError
from .routing import is_open, order_day, order_stops, path_km, schedule, walk_km
from .schemas import Itinerary, Place, TasteProfile, UserInput
from .taste_agent import SLOT_ORDER

log = logging.getLogger(__name__)

POOL_RADIUS_KM = 1.2
DAY_ORDER_MAX_DETOUR = 1.3  # accept day-rhythm order if <= 30% longer than shortest
POOL_SIZE = 20
MAX_PER_CATEGORY = 2
SLOT_BONUS = 1.5  # worth more than one extra high-affinity place of a slot we already have


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
    """Coffee first and drinks (or food) last, unless that makes the walk much longer."""
    first = next((p for p in chosen if p.slot == "coffee"), None)
    last = next((p for p in chosen if p.slot == "drinks"), None) or next(
        (p for p in chosen if p.slot == "food"), None
    )
    shortest = order_stops(chosen)
    day = order_day(chosen, first, last)
    if path_km(day) <= DAY_ORDER_MAX_DETOUR * path_km(shortest) + 0.2:
        return day
    return shortest


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
        spares = [p for p in pool if p not in chosen and walk_km(p, bad) <= POOL_RADIUS_KM]
        spares.sort(key=lambda p: (p.slot != bad.slot, -(p.affinity or 0)))
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
    stops, check = schedule_open(chosen[:n], pool, user, day or date.today())
    return Itinerary(
        city=user.city,
        start_time=user.start_time,
        stops=stops,
        total_km=check.total_km,
        total_walk_minutes=check.total_walk_minutes,
        check=check,
    )
