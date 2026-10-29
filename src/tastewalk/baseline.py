"""Baseline: the same request answered by the LLM alone, with no Qloo data. Shown side by side."""

from __future__ import annotations

from .llm import LLM
from .schemas import BaselineItinerary, UserInput


def baseline_itinerary(llm: LLM, user: UserInput) -> BaselineItinerary:
    favs = ", ".join(f"{f.name} ({f.type.name})" for f in user.favorites)
    return llm.json(
        system="You are a helpful travel planner.",
        user=(
            f"I love: {favs}. Plan a one-day walking itinerary in {user.city} starting at "
            f"{user.start_time:%H:%M} with {user.max_stops} stops that match my taste. "
            "For each stop give name, category, time and why it fits me."
        ),
        schema=BaselineItinerary,
    )
