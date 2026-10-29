"""DEVELOPMENT ONLY: a fake Qloo server for tests and for building the UI without an API key.

Enabled in the web app only with TASTEWALK_FAKE_QLOO=1, and the UI shows a "demo data" banner.
The places are fictional ("Test ..."), placed around the Plateau / Mile End so the map looks
right. Response shapes follow what qloo.py assumes; update both once the real API is confirmed.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from .cache import DiskCache
from .qloo import QlooClient

FAKE_KEY = "fake-key"
_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# id, name, category, lat, lon, affinity
FAKE_PLACES = [
    ("P1", "Test Cafe A", "Coffee Shop", 45.5230, -73.5810, 0.95),
    ("P2", "Test Records", "Record Store", 45.5245, -73.5835, 0.91),
    ("P3", "Test Gallery", "Art Gallery", 45.5190, -73.5760, 0.88),
    ("P4", "Test Bistro", "Restaurant", 45.5215, -73.5790, 0.86),
    ("P5", "Test Cafe B", "Coffee Shop", 45.5250, -73.5800, 0.84),
    ("P6", "Test Cafe C", "Coffee Shop", 45.5260, -73.5820, 0.83),
    ("P7", "Test Bar", "Bar", 45.5200, -73.5820, 0.80),
    ("P8", "Test Bookshop", "Book Store", 45.5272, -73.5890, 0.79),
    ("P9", "Test Park", "Park", 45.5155, -73.5800, 0.77),
    ("P10", "Test Market", "Market", 45.5320, -73.6145, 0.75),
    ("FAR", "Far Away Place", "Bar", 45.70, -73.90, 0.99),  # outside the city radius
]


def place_json(pid: str, name: str, cat: str, lat: float, lon: float, aff: float) -> dict:
    return {
        "entity_id": pid,
        "name": name,
        "location": {"lat": lat, "lon": lon},
        "properties": {
            "address": "1 Test St",
            "hours": {d: [{"opens": "T08:00", "closes": "T23:00"}] for d in _DAYS},
        },
        "tags": [
            {"id": f"urn:tag:category:{cat}", "name": cat, "type": "urn:tag:category:place"},
            {"id": "urn:tag:genre:indie", "name": "Indie", "type": "urn:tag:genre"},
        ],
        "query": {"affinity": aff},
    }


def handler(request: httpx.Request) -> httpx.Response:
    if request.headers.get("X-Api-Key") != FAKE_KEY:
        return httpx.Response(401, json={"error": "bad key"})
    if request.url.path == "/search":
        q = request.url.params["query"]
        if q == "Nobody":
            return httpx.Response(200, json={"results": []})
        tag = {"id": "urn:tag:genre:indie", "name": "Indie", "type": "urn:tag:genre"}
        return httpx.Response(
            200, json={"results": [{"entity_id": f"E-{q}", "name": q, "tags": [tag]}]}
        )
    if request.url.path == "/v2/insights":
        if request.url.params.get("filter.type") != "urn:entity:place":
            return httpx.Response(400)
        ents = [place_json(*p) for p in FAKE_PLACES]
        return httpx.Response(200, json={"results": {"entities": ents}})
    return httpx.Response(404)


def fake_client(cache_dir: Path) -> QlooClient:
    return QlooClient(
        FAKE_KEY, "https://fake.qloo", DiskCache(cache_dir), transport=httpx.MockTransport(handler)
    )
