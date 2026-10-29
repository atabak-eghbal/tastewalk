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
from .llm import LLM, LLMError
from .planner import plan
from .qloo import QlooClient, QlooError
from .schemas import Comparison, UserInput
from .taste_agent import NoTasteSignal, build_profile, find_candidates


@dataclass
class Event:
    step: str  # taste | candidates | plan | critic | baseline | done | error
    message: str
    data: Any = None


def make_clients(settings: Settings, offline: bool = False) -> tuple[QlooClient, LLM | None]:
    cache = DiskCache(settings.cache_dir, settings.seed_cache_dir)
    qloo = QlooClient(
        settings.qloo_api_key,
        settings.qloo_base_url,
        cache,
        offline=offline or not settings.has_qloo,
    )
    llm = LLM(settings.llm_api_key, settings.llm_base_url, settings.llm_model, cache)
    return qloo, llm


def run(
    user: UserInput,
    qloo: QlooClient | None = None,
    llm: LLM | None = None,
    with_baseline: bool = True,
) -> Iterator[Event]:
    if qloo is None:
        qloo, llm = make_clients(load_settings())
    try:
        profile = build_profile(qloo, user)
        names = ", ".join(e.name for e in profile.entities) or "nothing"
        yield Event("taste", f"Matched {len(profile.entities)} favorites in Qloo: {names}", profile)

        candidates = find_candidates(qloo, user, profile)
        yield Event("candidates", f"Qloo found {len(candidates)} places in {user.city}", candidates)
        if not candidates:
            yield Event("error", f"Qloo returned no places in {user.city} for this taste")
            return

        itin = plan(candidates, profile, user, llm)
        yield Event("plan", f"Planned {len(itin.stops)} stops, {itin.total_km} km walking", itin)

        itin = critique(itin, profile, llm)
        yield Event("critic", "Explained each stop", itin)

        baseline = None
        if with_baseline and llm is not None:
            try:
                baseline = baseline_itinerary(llm, user)
                yield Event("baseline", "LLM-only itinerary ready", baseline)
            except LLMError as e:
                yield Event("baseline", f"LLM-only baseline unavailable: {e}")

        yield Event(
            "done",
            "Itinerary ready",
            Comparison(profile=profile, qloo_itinerary=itin, baseline_itinerary=baseline),
        )
    except (QlooError, NoTasteSignal) as e:
        yield Event("error", str(e))
