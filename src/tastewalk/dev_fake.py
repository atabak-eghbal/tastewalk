"""DEVELOPMENT ONLY: a fake Qloo server for tests and for building the UI without an API key.

Enabled in the web app only with TASTEWALK_FAKE_QLOO=1, and the UI shows a "demo data" banner.
The places are fictional ("Test ..."), placed around downtown Vancouver so the map looks
right. Response shapes follow what qloo.py assumes; update both once the real API is confirmed.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from .cache import DiskCache
from .qloo import QlooClient

FAKE_KEY = "fake-key"
_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# id, name, category, lat, lon, affinity
FAKE_PLACES = [
    ("P1", "Test Cafe A", "Cafe", 49.3002, -123.1218, 0.95),
    ("P2", "Test Records", "Record store", 49.3017, -123.1243, 0.91),
    ("P3", "Test Gallery", "Art gallery", 49.2962, -123.1168, 0.88),
    ("P4", "Test Bistro", "Restaurant", 49.2987, -123.1198, 0.86),
    ("P5", "Test Cafe B", "Cafe", 49.3022, -123.1208, 0.84),
    ("P6", "Test Cafe C", "Cafe", 49.3032, -123.1228, 0.83),
    ("P7", "Test Bar", "Bar", 49.2972, -123.1228, 0.80),
    ("P8", "Test Bookshop", "Book store", 49.3044, -123.1298, 0.79),
    ("P9", "Test Park", "Park", 49.2927, -123.1208, 0.77),
    ("P10", "Test Market", "Market", 49.3092, -123.1553, 0.75),
    ("FAR", "Far Away Place", "Bar", 49.4772, -123.4408, 0.99),  # outside the city radius
]


def _cat_id(cat: str) -> str:
    return "urn:tag:category:place:" + cat.lower().replace(" ", "_")


def place_json(
    pid: str, name: str, cat: str, lat: float, lon: float, aff: float, signals: list[str] = ()
) -> dict:
    """One place in the verified /v2/insights shape (see docs/research/01-qloo-api.md)."""
    n = len(signals)
    explain = [
        {"entity_id": e, "score": (n - i) / (n * (n + 1) / 2)} for i, e in enumerate(signals)
    ]
    return {
        "entity_id": pid,
        "name": name,
        "subtype": "urn:entity:place",
        "location": {"lat": lat, "lon": lon},
        "properties": {
            "address": "1 Test St",
            "neighborhood": "Test Gastown",
            "short_description": f"A fictional {cat.lower()} used for testing.",
            "is_closed": False,
            "hours": {
                d: [{"opens": "T08:00:00", "closes": "T23:00:00", "closed": False}] for d in _DAYS
            },
        },
        "tags": [
            {"id": _cat_id(cat), "name": cat, "type": "urn:tag:category:place"},
            {"id": "urn:tag:ambience:qloo:cozy", "name": "Cozy", "type": "urn:tag:ambience:qloo"},
        ],
        "query": {
            "affinity": aff,
            "explainability": {"signal.interests.entities": explain},
        },
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
        signals = request.url.params["signal.interests.entities"].split(",")
        wanted = set(filter(None, request.url.params.get("filter.tags", "").split(",")))
        rows = [p for p in FAKE_PLACES if not wanted or _cat_id(p[2]) in wanted]
        ents = [place_json(*p, signals=signals) for p in rows]
        return httpx.Response(200, json={"results": {"entities": ents}})
    return httpx.Response(404)


def fake_client(cache_dir: Path) -> QlooClient:
    return QlooClient(
        FAKE_KEY, "https://fake.qloo", DiskCache(cache_dir), transport=httpx.MockTransport(handler)
    )
