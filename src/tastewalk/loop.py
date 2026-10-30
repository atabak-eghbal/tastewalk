"""Orchestration: runs taste -> planner -> critic (+ baseline) and yields progress events.

The API streams these events over SSE; the CLI prints them. The last event is `done` with a
`Comparison` payload, or `error`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from .baseline import baseline_itinerary
from .cache import DiskCache
from .config import Settings, load_settings
from .critic import critique
from .examples import FROZEN_OSM, frozen_baseline
from .fact_check import fact_check
from .llm import LLM, LLMError
from .osm import OSMClient
from .planner import plan
from .qloo import QlooClient, QlooError
from .schemas import Comparison, UserInput
from .taste_agent import NoTasteSignal, build_profile, find_candidates


@dataclass
class Event:
    step: str  # taste | candidates | plan | critic | baseline | audit | done | error
    message: str
    data: Any = None


def make_clients(settings: Settings, offline: bool = False) -> tuple[QlooClient, LLM | None]:
    cache = DiskCache(settings.cache_dir)
    qloo = QlooClient(
        settings.qloo_api_key,
        settings.qloo_base_url,
        cache,
        offline=offline or not settings.has_qloo,
    )
    llm = LLM(
        settings.llm_api_key,
        settings.llm_base_url,
        settings.llm_model,
        cache,
        fallback_model=settings.llm_fallback_model,
    )
    return qloo, llm


def run(
    user: UserInput,
    qloo: QlooClient | None = None,
    llm: LLM | None = None,
    with_baseline: bool = True,
    osm: OSMClient | None = None,
) -> Iterator[Event]:
    """osm: OpenStreetMap lookups for LLM places Qloo doesn't know (None skips that check)."""
    if qloo is None:
        qloo, llm = make_clients(load_settings())
    try:
        profile = build_profile(qloo, user)
        if not profile.entities:
            missing = ", ".join(profile.unresolved)
            yield Event(
                "error",
                f"Qloo couldn't find: {missing}. Check the spelling, or the type "
                "(artist, movie, brand...).",
            )
            return
        names = ", ".join(e.name for e in profile.entities)
        missed = f" (not found: {', '.join(profile.unresolved)})" if profile.unresolved else ""
        yield Event(
            "taste", f"Matched {len(profile.entities)} favorites in Qloo: {names}{missed}", profile
        )

        candidates = find_candidates(qloo, user, profile)
        yield Event("candidates", f"Qloo found {len(candidates)} places in {user.city}", candidates)
        if not candidates:
            yield Event("error", f"Qloo returned no places in {user.city} for this taste")
            return

        # The examples use the code-only planner so their routes never drift with LLM quota or
        # model changes (the docs and video quote them); custom favorites get the LLM planner.
        example = frozen_baseline(user) is not None
        itin = plan(candidates, profile, user, None if example else llm)
        yield Event("plan", f"Planned {len(itin.stops)} stops, {itin.total_km} km walking", itin)

        itin = critique(itin, profile, llm)
        yield Event("critic", "Explained each stop", itin)

        baseline = frozen_baseline(user) if with_baseline else None
        if baseline is not None:
            yield Event("baseline", "LLM-only plan (recorded Oct 30 for this example)", baseline)
        elif with_baseline and llm is not None:
            try:
                baseline = baseline_itinerary(llm, user)
                yield Event("baseline", "LLM-only itinerary ready", baseline)
            except LLMError as e:
                yield Event("baseline", f"LLM-only baseline unavailable: {e}")

        audit = None
        if baseline is not None:
            try:
                audit = fact_check(qloo, baseline, profile, itin, osm=osm, osm_known=FROZEN_OSM)
                nowhere = (
                    f", {audit.nowhere} not found in Qloo or OpenStreetMap" if audit.nowhere else ""
                )
                yield Event(
                    "audit",
                    f"Fact-checked the LLM plan: Qloo located {audit.found} of {audit.total} "
                    f"places{nowhere}",
                    audit,
                )
            except QlooError as e:
                yield Event("audit", f"Fact-check unavailable: {e}")

        yield Event(
            "done",
            "Itinerary ready",
            Comparison(
                profile=profile,
                qloo_itinerary=itin,
                baseline_itinerary=baseline,
                baseline_audit=audit,
            ),
        )
    except (QlooError, NoTasteSignal) as e:
        yield Event("error", str(e))
