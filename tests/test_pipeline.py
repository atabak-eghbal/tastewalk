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
from tastewalk.loop import run
from tastewalk.qloo import QlooClient, parse_place
from tastewalk.routing import order_stops, schedule, walk_minutes
from tastewalk.schemas import Favorite, FavoriteType, Place, UserInput

# Fictional test places around the Plateau (not real venues).
FAKE_PLACES = [
    ("P1", "Test Cafe A", "Coffee Shop", 45.5230, -73.5810, 0.95),
    ("P2", "Test Records", "Record Store", 45.5245, -73.5835, 0.91),
    ("P3", "Test Gallery", "Art Gallery", 45.5190, -73.5760, 0.88),
    ("P4", "Test Bistro", "Restaurant", 45.5215, -73.5790, 0.86),
    ("P5", "Test Cafe B", "Coffee Shop", 45.5250, -73.5800, 0.84),
    ("P6", "Test Cafe C", "Coffee Shop", 45.5260, -73.5820, 0.83),
    ("P7", "Test Bar", "Bar", 45.5200, -73.5820, 0.80),
    ("FAR", "Far Away Place", "Bar", 45.70, -73.90, 0.99),  # outside city radius
]


def _place_json(pid, name, cat, lat, lon, aff):
    return {
        "entity_id": pid,
        "name": name,
        "location": {"lat": lat, "lon": lon},
        "properties": {
            "address": "1 Test St",
            "hours": {"Monday": [{"opens": "T08:00", "closes": "T23:00"}]},
        },
        "tags": [
            {"id": f"urn:tag:category:{cat}", "name": cat, "type": "urn:tag:category:place"},
            {"id": "urn:tag:genre:indie", "name": "Indie", "type": "urn:tag:genre"},
        ],
        "query": {"affinity": aff},
    }


def fake_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["X-Api-Key"] == "test-key"
    if request.url.path == "/search":
        q = request.url.params["query"]
        if q == "Nobody":
            return httpx.Response(200, json={"results": []})
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "entity_id": f"E-{q}",
                        "name": q,
                        "tags": [
                            {"id": "urn:tag:genre:indie", "name": "Indie", "type": "urn:tag:genre"}
                        ],
                    }
                ]
            },
        )
    if request.url.path == "/v2/insights":
        assert request.url.params["filter.type"] == "urn:entity:place"
        return httpx.Response(
            200, json={"results": {"entities": [_place_json(*p) for p in FAKE_PLACES]}}
        )
    return httpx.Response(404)


@pytest.fixture
def qloo(tmp_path):
    return QlooClient(
        "test-key",
        "https://fake.qloo",
        DiskCache(tmp_path),
        transport=httpx.MockTransport(fake_handler),
    )


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
    assert cats.count("Coffee Shop") <= 2  # variety cap
    assert all("Indie" in s.matched_tags and s.why_it_fits for s in stops)


def test_no_matches_is_an_error(qloo):
    events = list(run(user("Nobody"), qloo, llm=None))
    assert events[-1].step == "error"


def test_qloo_responses_are_cached(tmp_path):
    calls = []

    def counting(req):
        calls.append(req.url.path)
        return fake_handler(req)

    cache = DiskCache(tmp_path)
    c1 = QlooClient("test-key", "https://fake.qloo", cache, transport=httpx.MockTransport(counting))
    c1.search("Radiohead", "urn:entity:artist")
    c1.search("Radiohead", "urn:entity:artist")
    assert calls == ["/search"]
    offline = QlooClient("test-key", "https://fake.qloo", cache, offline=True)
    assert offline.search("Radiohead", "urn:entity:artist")[0]["entity_id"] == "E-Radiohead"


def test_parse_place_requires_id_and_coords():
    assert parse_place({"entity_id": "x", "name": "no coords"}) is None
    p = parse_place(_place_json(*FAKE_PLACES[0]))
    assert p.category == "Coffee Shop" and p.affinity == 0.95
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
    assert "Indie" in itin.stops[0].why_it_fits
