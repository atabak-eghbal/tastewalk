"""API tests: meta, validation and the SSE plan stream, using the fake Qloo server."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import create_app


def _client() -> TestClient:
    return TestClient(create_app(fake=True))


def test_meta_and_index():
    c = _client()
    meta = c.get("/api/meta").json()
    assert meta["fake_data"] is True and len(meta["examples"]) >= 3
    assert c.get("/").status_code == 200
    assert c.get("/healthz").json() == {"ok": True}


def test_plan_rejects_bad_input():
    assert _client().get("/api/plan", params={"q": '{"favorites": []}'}).status_code == 422


def test_plan_streams_events():
    q = json.dumps({"favorites": [{"name": "Radiohead", "type": "urn:entity:artist"}]})
    with _client().stream("GET", "/api/plan", params={"q": q}) as r:
        events = [json.loads(line[5:]) for line in r.iter_lines() if line.startswith("data:")]
    steps = [e["step"] for e in events]
    assert steps[0] == "taste" and steps[-1] == "done"
    stops = events[-1]["data"]["qloo_itinerary"]["stops"]
    assert stops and all(s["place"]["qloo_id"] for s in stops)


def test_parse_without_llm_is_a_clear_503(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")  # .env doesn't override a set variable
    r = _client().post("/api/parse", json={"text": "I love Radiohead"})
    assert r.status_code == 503


def test_parse_maps_llm_output_to_favorites():
    from tastewalk.parse import _Parsed, parse_favorites
    from tastewalk.schemas import FavoriteType

    class FakeLLM:
        def json(self, system, user, schema):
            assert schema is _Parsed
            return _Parsed.model_validate(
                {
                    "favorites": [
                        {"name": "Radiohead", "type": "artist"},
                        {"name": "radiohead ", "type": "artist"},
                        {"name": "Spirited Away", "type": "movie"},
                    ]
                }
            )

    favs = parse_favorites(FakeLLM(), "I love Radiohead and Spirited Away")
    assert [(f.name, f.type) for f in favs] == [
        ("Radiohead", FavoriteType.artist),
        ("Spirited Away", FavoriteType.movie),
    ]
