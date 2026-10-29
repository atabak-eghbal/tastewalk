"""Planner agent: picks a varied, walkable subset of Qloo candidates and schedules it.

Code narrows candidates to a compact walking area; the LLM (optional) picks which stops make a
good day; code validates the picks are real candidate IDs, orders them and computes times.
"""

from __future__ import annotations

import logging
from collections import Counter

from pydantic import BaseModel

from .llm import LLM, LLMError
from .routing import order_stops, schedule, walk_km
from .schemas import Itinerary, Place, TasteProfile, UserInput

log = logging.getLogger(__name__)

POOL_RADIUS_KM = 2.0
POOL_SIZE = 15
MAX_PER_CATEGORY = 2


class PlannerPicks(BaseModel):
    qloo_ids: list[str]
    reasoning: str = ""


def _score(p: Place, rank: int) -> float:
    return p.affinity if p.affinity is not None else 1.0 / (1 + rank)


def compact_pool(candidates: list[Place]) -> list[Place]:
    """Pick the anchor whose neighbourhood holds the most taste score, return that pool."""
    if not candidates:
        return []
    scores = {p.qloo_id: _score(p, i) for i, p in enumerate(candidates)}
    best_pool: list[Place] = []
    best_total = -1.0
    for anchor in candidates[:POOL_SIZE]:
        pool = [p for p in candidates if walk_km(anchor, p) <= POOL_RADIUS_KM][:POOL_SIZE]
        total = sum(scores[p.qloo_id] for p in pool)
        if total > best_total:
            best_pool, best_total = pool, total
    return best_pool


def pick_deterministic(pool: list[Place], n: int) -> list[Place]:
    per_cat: Counter[str] = Counter()
    picks = []
    for p in pool:
        cat = (p.category or "other").lower()
        if per_cat[cat] >= MAX_PER_CATEGORY:
            continue
        per_cat[cat] += 1
        picks.append(p)
        if len(picks) == n:
            break
    return picks


def pick_with_llm(llm: LLM, pool: list[Place], profile: TasteProfile, n: int) -> list[Place]:
    lines = [
        f"- {p.qloo_id} | {p.name} | {p.category or '?'} | "
        f"tags: {', '.join(t.name for t in p.tags[:6]) or '-'}"
        for p in pool
    ]
    favs = ", ".join(e.name for e in profile.entities)
    picks = llm.json(
        system=(
            "You plan a one-day walking itinerary. Choose ONLY from the candidate list by ID. "
            "Prefer variety (e.g. coffee, culture, shopping, food, a drink) and a natural day "
            "rhythm. Never invent places."
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


def plan(
    candidates: list[Place], profile: TasteProfile, user: UserInput, llm: LLM | None
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
    stops, check = schedule(order_stops(chosen[:n]), user.start_time)
    return Itinerary(
        city=user.city,
        start_time=user.start_time,
        stops=stops,
        total_km=check.total_km,
        total_walk_minutes=check.total_walk_minutes,
        check=check,
    )
