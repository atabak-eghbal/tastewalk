"""Critic agent: explains why each stop fits, grounded in Qloo's own explanation of the pick.

Qloo's explainability scores say how much each of the user's favorites drove a recommendation;
code turns that into `because_of`. The LLM only phrases the explanation from those facts plus
Qloo's place description and vibe tags. Without an LLM, a template sentence is used.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from .llm import LLM, LLMError
from .schemas import Itinerary, Stop, TasteProfile

log = logging.getLogger(__name__)

MIN_SHARE = 0.2  # a favorite must drive at least 20% of the pick to be named


class StopWhy(BaseModel):
    qloo_id: str
    why: str


class CriticOutput(BaseModel):
    stops: list[StopWhy]


def because_of(stop: Stop, profile: TasteProfile) -> list[str]:
    """Favorites behind this pick, strongest first (from Qloo explainability)."""
    names = {e.qloo_id: e.name for e in profile.entities}
    scores = stop.place.signal_scores
    total = sum(scores.values()) or 1.0
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    return [names[i] for i, s in ranked if i in names and s / total >= MIN_SHARE][:2]


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def template_why(stop: Stop, profile: TasteProfile) -> str:
    names = stop.because_of or [e.name for e in profile.entities[:2]]
    parts = []
    if names:
        s = f"Qloo matches this to people who love {_join(names)}"
        if stop.place.affinity is not None:
            s += f" (affinity {stop.place.affinity:.2f})"
        parts.append(s + ".")
    if stop.place.vibe:
        parts.append(f"Expect: {', '.join(v.lower() for v in stop.place.vibe[:3])}.")
    return " ".join(parts)


def critique(itin: Itinerary, profile: TasteProfile, llm: LLM | None) -> Itinerary:
    for s in itin.stops:
        s.because_of = because_of(s, profile)
        s.why_it_fits = template_why(s, profile)
    if llm is None or not itin.stops:
        return itin
    favs = ", ".join(e.name for e in profile.entities)
    lines = []
    for s in itin.stops:
        p = s.place
        lines.append(
            f"- {p.qloo_id} | {p.name} | {p.category or '?'} | "
            f"driven most by: {', '.join(s.because_of) or 'overall taste'} | "
            f"vibe: {', '.join(p.vibe) or '-'} | about: {(p.description or '-')[:200]}"
        )
    try:
        out = llm.json(
            system=(
                "You explain to a traveler why each stop fits their taste, in one or two short, "
                "warm sentences per stop. Connect the place to the favorites that drove the pick. "
                "Use ONLY the facts given (favorites, vibe, description). Do not invent history, "
                "dishes, prices or awards."
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
