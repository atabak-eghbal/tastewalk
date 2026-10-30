"""Pydantic data contracts shared by every agent, the API and the UI (see docs/architecture.md)."""

from __future__ import annotations

from datetime import time
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FavoriteType(str, Enum):
    """Kinds of favorites a user can enter. Values are Qloo search type URNs (verified)."""

    artist = "urn:entity:artist"
    movie = "urn:entity:movie"
    tv_show = "urn:entity:tv_show"
    book = "urn:entity:book"
    brand = "urn:entity:brand"
    place = "urn:entity:place"
    podcast = "urn:entity:podcast"
    video_game = "urn:entity:videogame"


class Favorite(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    type: FavoriteType


class UserInput(BaseModel):
    city: Literal["Montreal"] = "Montreal"  # the only city with a configured centre and radius
    favorites: list[Favorite] = Field(min_length=1, max_length=8)
    start_time: time = time(10, 0)
    max_stops: int = Field(default=6, ge=2, le=10)


class Tag(BaseModel):
    id: str
    name: str
    type: str | None = None


class ResolvedEntity(BaseModel):
    """A favorite matched to a Qloo entity via search."""

    query: str
    qloo_id: str
    name: str
    type: str
    tags: list[Tag] = []


class TasteProfile(BaseModel):
    entities: list[ResolvedEntity]
    unresolved: list[str] = []
    top_tags: list[Tag] = []


class Place(BaseModel):
    qloo_id: str = Field(min_length=1)
    name: str
    category: str | None = None
    lat: float
    lon: float
    address: str | None = None
    tags: list[Tag] = []
    affinity: float | None = None
    # Weekday (0=Mon) -> list of (open, close) spans. None means Qloo gave no hours.
    hours: dict[int, list[tuple[time, time]]] | None = None
    slot: str | None = None  # day-plan bucket this came from: coffee, culture, shopping...
    neighborhood: str | None = None
    description: str | None = None
    image_url: str | None = None
    vibe: list[str] = []  # Qloo ambience / interest / setting tags
    # Qloo explainability: favorite entity ID -> share of this recommendation.
    signal_scores: dict[str, float] = {}


class Stop(BaseModel):
    place: Place
    arrive: time
    leave: time
    walk_minutes_from_prev: int = 0
    why_it_fits: str = ""
    because_of: list[str] = []  # favorites that drove this pick, strongest first


class RouteCheck(BaseModel):
    ok: bool
    total_walk_minutes: int
    total_km: float
    issues: list[str] = []


class Itinerary(BaseModel):
    city: str
    start_time: time
    stops: list[Stop]
    total_km: float
    total_walk_minutes: int
    check: RouteCheck | None = None


class BaselineStop(BaseModel):
    """LLM-only stop. No Qloo ID by design; the place may not exist."""

    name: str
    category: str | None = None
    why: str = ""
    time: str | None = None


class BaselineItinerary(BaseModel):
    city: str
    stops: list[BaselineStop]


class StopCheck(BaseModel):
    """Qloo's check of one LLM-only stop: does it exist, is it open, how far, how well it fits."""

    name: str
    found: bool
    qloo_id: str | None = None
    qloo_name: str | None = None
    address: str | None = None
    lat: float | None = None
    lon: float | None = None
    ambiguous: bool = False  # several branches match (a chain): no hours/walk claims
    in_osm: bool | None = None  # not in Qloo: does OpenStreetMap know it? None = not checked
    open: bool | None = None  # None: no hours from Qloo, or no time from the LLM
    affinity: float | None = None
    walk_minutes_from_prev: int | None = None  # from the previous located stop


class BaselineAudit(BaseModel):
    """The LLM-only plan, fact-checked with Qloo data and the same routing code as our plan."""

    stops: list[StopCheck]
    found: int  # located in Qloo
    in_osm: int  # not in Qloo, but OpenStreetMap has a place with that name
    nowhere: int  # neither Qloo nor OpenStreetMap could find it
    total: int
    closed: int
    hours_checked: int  # located stops whose opening hours could be checked at the LLM's time
    walk_km: float  # between located stops (unambiguous), in the LLM's order
    longest_leg_min: int
    avg_affinity: float | None = None
    qloo_avg_affinity: float | None = None  # our route, same Qloo scale
    qloo_km: float


class Comparison(BaseModel):
    profile: TasteProfile
    qloo_itinerary: Itinerary
    baseline_itinerary: BaselineItinerary | None = None
    baseline_audit: BaselineAudit | None = None
