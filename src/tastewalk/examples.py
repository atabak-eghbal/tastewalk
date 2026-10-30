"""Curated demo profiles shown as one-click examples, warmed into the server cache at startup.

Chosen so the Qloo vs LLM-only contrast is visible: niche-ish tastes where a generic model
tends to fall back on the same famous tourist spots.
"""

from __future__ import annotations

import json
from datetime import time
from pathlib import Path

from .schemas import BaselineItinerary, Favorite, FavoriteType, UserInput


def _fav(name: str, kind: str) -> Favorite:
    return Favorite(name=name, type=FavoriteType[kind])


EXAMPLES: dict[str, dict] = {
    "indie": {
        "label": "Indie music & arthouse film",
        "input": UserInput(
            favorites=[
                _fav("Arcade Fire", "artist"),
                _fav("Radiohead", "artist"),
                _fav("Amélie", "movie"),
                _fav("Lost in Translation", "movie"),
            ],
            start_time=time(11, 0),
        ),
    },
    "design": {
        "label": "Design brands & food TV",
        "input": UserInput(
            favorites=[
                _fav("Aesop", "brand"),
                _fav("Muji", "brand"),
                _fav("The Bear", "tv_show"),
                _fav("Chef's Table", "tv_show"),
            ],
            start_time=time(10, 0),
        ),
    },
    "kculture": {
        "label": "K-pop & Korean film",
        "input": UserInput(
            favorites=[
                _fav("BTS", "artist"),
                _fav("Parasite", "movie"),
                _fav("Squid Game", "tv_show"),
                _fav("Gentle Monster", "brand"),
            ],
            start_time=time(12, 0),
        ),
    },
    "streetwear": {
        "label": "Hip-hop & streetwear",
        "input": UserInput(
            favorites=[
                _fav("Kendrick Lamar", "artist"),
                _fav("Supreme", "brand"),
                _fav("Nike", "brand"),
                _fav("Atlanta", "tv_show"),
            ],
            start_time=time(12, 0),
        ),
    },
}


# LLM-only plans for the examples, recorded once (LLM output, not Qloo data) so the live demo,
# README and video agree. Custom favorites always get a live LLM-only plan.
_DATA = json.loads((Path(__file__).with_name("example_baselines.json")).read_text())
_FROZEN = _DATA["plans"]
FROZEN_OSM: dict[str, bool] = _DATA.get("osm", {})  # OpenStreetMap verdicts for those names


def frozen_baseline(user: UserInput) -> BaselineItinerary | None:
    for ex_id, ex in EXAMPLES.items():
        if ex["input"] == user and ex_id in _FROZEN:
            return BaselineItinerary.model_validate(_FROZEN[ex_id])
    return None
