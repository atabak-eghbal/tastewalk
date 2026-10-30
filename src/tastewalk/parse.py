"""Free text (typed or spoken) -> favorites. The LLM only extracts what the user said; Qloo then
resolves each name as usual, so anything it can't find is reported, not invented."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .llm import LLM
from .schemas import Favorite, FavoriteType

Kind = Literal["artist", "movie", "tv_show", "book", "brand", "podcast", "video_game"]


class _Fav(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: Kind


class _Parsed(BaseModel):
    favorites: list[_Fav] = Field(default_factory=list, max_length=8)


def parse_favorites(llm: LLM, text: str) -> list[Favorite]:
    out = llm.json(
        system=(
            "Extract the user's favorite things from their message: artists, movies, TV shows, "
            "books, brands, podcasts and video games. Only include things the user actually "
            "names; never add suggestions. Use the usual full title (e.g. 'The Legend of Zelda: "
            "Breath of the Wild'). At most 8."
        ),
        user=text,
        schema=_Parsed,
    )
    seen, favs = set(), []
    for f in out.favorites:
        key = f.name.strip().lower()
        if key and key not in seen:
            seen.add(key)
            favs.append(Favorite(name=f.name.strip(), type=FavoriteType[f.type]))
    return favs
