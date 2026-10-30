"""End-to-end and unit tests using a fake Qloo server (httpx.MockTransport). No network, no keys.

The fake responses follow the shapes qloo.py assumes; update them together once the real
API shape is confirmed by scripts/smoke_test_qloo.py.
"""

from __future__ import annotations

from datetime import time

import httpx
import pytest

from tastewalk.cache import DiskCache
from tastewalk.critic import critique
from tastewalk.dev_fake import FAKE_KEY, FAKE_PLACES, fake_client
from tastewalk.dev_fake import handler as fake_handler
from tastewalk.dev_fake import place_json as _place_json
from tastewalk.loop import run
from tastewalk.qloo import QlooClient, parse_place
from tastewalk.routing import order_stops, schedule, walk_minutes
from tastewalk.schemas import Favorite, FavoriteType, Place, UserInput


@pytest.fixture
def qloo(tmp_path):
    return fake_client(tmp_path)


def user(*names, stops=4):
    return UserInput(
        favorites=[Favorite(name=n, type=FavoriteType.artist) for n in names], max_stops=stops
    )


def test_pipeline_without_llm(qloo):
    events = list(run(user("Radiohead", "Nobody"), qloo, llm=None))
    steps = [e.step for e in events]
    assert steps == ["taste", "candidates", "plan", "critic", "done"]
    result = events[-1].data
    assert result.profile.unresolved == ["Nobody"]
    stops = result.qloo_itinerary.stops
    assert len(stops) == 4
    ids = {s.place.qloo_id for s in stops}
    assert "FAR" not in ids  # filtered by distance
    assert all(s.place.qloo_id.startswith("P") for s in stops)  # only Qloo candidates
    cats = [s.place.category for s in stops]
    assert cats.count("Cafe") <= 2  # variety cap
    assert all(s.because_of and s.why_it_fits for s in stops)
    assert len({s.place.slot for s in stops}) >= 3  # varied day: several slots


def test_no_matches_is_an_error(qloo):
    events = list(run(user("Nobody"), qloo, llm=None))
    assert events[-1].step == "error"


def test_qloo_responses_are_cached(tmp_path):
    calls = []

    def counting(req):
        calls.append(req.url.path)
        return fake_handler(req)

    cache = DiskCache(tmp_path)
    c1 = QlooClient(FAKE_KEY, "https://fake.qloo", cache, transport=httpx.MockTransport(counting))
    c1.search("Radiohead", "urn:entity:artist")
    c1.search("Radiohead", "urn:entity:artist")
    assert calls == ["/search"]
    offline = QlooClient(FAKE_KEY, "https://fake.qloo", cache, offline=True)
    assert offline.search("Radiohead", "urn:entity:artist")[0]["entity_id"] == "E-Radiohead"


def test_parse_place_requires_id_and_coords():
    assert parse_place({"entity_id": "x", "name": "no coords"}) is None
    p = parse_place(_place_json(*FAKE_PLACES[0]))
    assert p.category == "Cafe" and p.affinity == 0.95
    assert p.hours[0] == [(time(8, 0), time(23, 0))]


def _p(pid, lat, lon, cat="Cafe", hours=None):
    return Place(qloo_id=pid, name=pid, category=cat, lat=lat, lon=lon, hours=hours)


def test_order_stops_avoids_zigzag():
    a, b, c, d = (
        _p("a", 45.50, -73.60),
        _p("b", 45.51, -73.60),
        _p("c", 45.52, -73.60),
        _p("d", 45.53, -73.60),
    )
    ordered = [p.qloo_id for p in order_stops([c, a, d, b])]
    assert ordered in (["a", "b", "c", "d"], ["d", "c", "b", "a"])


def test_schedule_times_and_closed_check():
    closed = {i: [(time(18, 0), time(23, 0))] for i in range(7)}
    a, b = _p("a", 45.52, -73.58), _p("b", 45.53, -73.58, hours=closed)
    stops, check = schedule([a, b], time(10, 0))
    assert stops[0].arrive == time(10, 0)
    assert stops[1].walk_minutes_from_prev == walk_minutes(a, b)
    assert stops[1].arrive > stops[0].leave
    assert not check.ok and "may be closed" in check.issues[0]


def test_critic_template_without_llm(qloo):
    events = list(run(user("Radiohead"), qloo, llm=None, with_baseline=False))
    itin = critique(events[-1].data.qloo_itinerary, events[-1].data.profile, None)
    assert "Radiohead" in itin.stops[0].why_it_fits


def test_day_order_pins_coffee_and_drinks_when_cheap():
    from tastewalk.planner import order_by_day

    cafe = _p("cafe", 45.520, -73.580)
    shop = _p("shop", 45.521, -73.580)
    bar = _p("bar", 45.522, -73.580)
    cafe.slot, shop.slot, bar.slot = "coffee", "shopping", "drinks"
    assert [p.qloo_id for p in order_by_day([bar, shop, cafe])] == ["cafe", "shop", "bar"]
