"""Critic agent: explains why each stop fits, grounded in Qloo tags shared with the user's taste.

Matched tags are computed in code. The LLM only phrases the explanation and must mention at
least one supplied fact; if it is unavailable, a template explanation is used.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from .llm import LLM, LLMError
from .schemas import Itinerary, Stop, TasteProfile

log = logging.getLogger(__name__)


class StopWhy(BaseModel):
    qloo_id: str
    why: str


class CriticOutput(BaseModel):
    stops: list[StopWhy]


def matched_tags(stop: Stop, profile: TasteProfile) -> list[str]:
    taste = {t.id for t in profile.top_tags} | {t.name.lower() for t in profile.top_tags}
    return [t.name for t in stop.place.tags if t.id in taste or t.name.lower() in taste]


def template_why(stop: Stop, profile: TasteProfile) -> str:
    favs = ", ".join(e.name for e in profile.entities[:3])
    parts = []
    if stop.matched_tags:
        parts.append(f"shares {', '.join(stop.matched_tags[:3])} with your taste")
    if stop.place.affinity is not None:
        parts.append(f"Qloo affinity {stop.place.affinity:.2f} for fans of {favs}")
    elif favs:
        parts.append(f"recommended by Qloo for fans of {favs}")
    return (stop.place.name + ": " + "; ".join(parts) + ".") if parts else ""


def critique(itin: Itinerary, profile: TasteProfile, llm: LLM | None) -> Itinerary:
    for s in itin.stops:
        s.matched_tags = matched_tags(s, profile)
        s.why_it_fits = template_why(s, profile)
    if llm is None or not itin.stops:
        return itin
    favs = ", ".join(e.name for e in profile.entities)
    lines = []
    for s in itin.stops:
        aff = f"{s.place.affinity:.2f}" if s.place.affinity is not None else "n/a"
        lines.append(
            f"- {s.place.qloo_id} | {s.place.name} | {s.place.category or '?'} | "
            f"shared taste tags: {', '.join(s.matched_tags) or 'none'} | "
            f"other tags: {', '.join(t.name for t in s.place.tags[:6]) or '-'} | affinity: {aff}"
        )
    try:
        out = llm.json(
            system=(
                "You explain to a traveler why each stop fits their taste, in one or two short, "
                "warm sentences per stop. Use ONLY the facts given (tags, affinity, their "
                "favorites). Do not invent history, dishes or awards."
            ),
            user=f"Their favorites: {favs}\nStops:\n" + "\n".join(lines),
            schema=CriticOutput,
        )
    except LLMError as e:
        log.warning("critic LLM failed, keeping template text: %s", e)
        return itin
    by_id = {w.qloo_id: w.why.strip() for w in out.stops}
    for s in itin.stops:
        if by_id.get(s.place.qloo_id):
            s.why_it_fits = by_id[s.place.qloo_id]
    return itin
