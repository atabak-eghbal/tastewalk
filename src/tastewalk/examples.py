"""Curated demo profiles shown as one-click examples. Their responses go in the seed cache.

Chosen so the Qloo vs LLM-only contrast is visible: niche-ish tastes where a generic model
tends to fall back on the same famous tourist spots.
"""

from __future__ import annotations

from datetime import time

from .schemas import Favorite, FavoriteType, UserInput


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
    "jazz": {
        "label": "Jazz & literary fiction",
        "input": UserInput(
            favorites=[
                _fav("Miles Davis", "artist"),
                _fav("Nina Simone", "artist"),
                _fav("Norwegian Wood", "book"),
                _fav("The Secret History", "book"),
            ],
            start_time=time(13, 0),
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
