"""Smoke test: probe the Qloo hackathon API and report what actually works.

Run: uv run python scripts/smoke_test_qloo.py
Tries several guesses for paths, params and location filters (from forum posts), prints a
short report, and saves every raw response to .cache/smoke/ for inspection. Record the
findings in docs/research/01-qloo-api.md and fix the QLOO_* constants in src/tastewalk/qloo.py.
"""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
KEY = os.getenv("QLOO_API_KEY")
if not KEY:
    sys.exit("QLOO_API_KEY is empty in .env")
BASE = os.getenv("QLOO_BASE_URL", "https://hackathon.api.qloo.com").rstrip("/")
OUT = ROOT / ".cache" / "smoke"
OUT.mkdir(parents=True, exist_ok=True)
http = httpx.Client(base_url=BASE, headers={"X-Api-Key": KEY}, timeout=30)
MONTREAL = (45.5048, -73.5772)


def call(label: str, path: str, params: dict) -> dict | None:
    try:
        r = http.get(path, params=params)
    except httpx.HTTPError as e:
        print(f"  {label:<38} ERROR {e}")
        return None
    fname = OUT / f"{label.replace(' ', '_').replace('/', '_')}.json"
    fname.write_text(r.text)
    try:
        data = r.json()
    except ValueError:
        data = None
    n = _count(data)
    print(f"  {label:<38} {r.status_code}  results={n}  -> {fname.relative_to(ROOT)}")
    if r.status_code >= 400:
        print(f"      {r.text[:200]}")
    return data if r.status_code < 400 else None


def _results(data):
    if not isinstance(data, dict):
        return []
    res = data.get("results", [])
    if isinstance(res, dict):
        res = res.get("entities", [])
    return res if isinstance(res, list) else []


def _count(data):
    return len(_results(data)) if data is not None else "-"


def describe_entity(e: dict) -> None:
    print(f"      keys: {sorted(e.keys())}")
    print(
        f"      name={e.get('name')!r} id={e.get('entity_id')!r} types={e.get('types') or e.get('type')}"
        f" subtype={e.get('subtype')}"
    )
    for k in ("location", "geocode", "query"):
        if k in e:
            print(f"      {k}: {json.dumps(e[k])[:200]}")
    props = e.get("properties") or {}
    print(f"      properties keys: {sorted(props.keys())}")
    if "hours" in props:
        print(f"      hours sample: {json.dumps(props['hours'])[:200]}")
    tags = e.get("tags") or []
    print(f"      tags ({len(tags)}): {json.dumps(tags[:3])[:300]}")


print(f"Base URL: {BASE}\n\n1) Search - which param name and entity types work?")
first_id = None
for param in ("types", "type"):
    data = call(
        f"search {param}=artist", "/search", {"query": "Radiohead", param: "urn:entity:artist"}
    )
    if _results(data) and first_id is None:
        first_id = _results(data)[0].get("entity_id")
        describe_entity(_results(data)[0])
for etype, q in [
    ("movie", "Amelie"),
    ("brand", "Patagonia"),
    ("place", "Olimpico"),
    ("book", "Dune"),
    ("tv_show", "Fleabag"),
    ("podcast", "Radiolab"),
    ("videogame", "Celeste"),
]:
    call(f"search types={etype}", "/search", {"query": q, "types": f"urn:entity:{etype}"})

if not first_id:
    sys.exit("\nNo entity resolved; fix search before probing insights.")

print(f"\n2) Insights for places, signal = {first_id}")
lat, lon = MONTREAL
base_params = {"filter.type": "urn:entity:place", "signal.interests.entities": first_id, "take": 10}
variants = {
    "insights point+radius": {
        "filter.location": f"POINT({lon} {lat})",
        "filter.location.radius": 5000,
    },
    "insights location.query": {"filter.location.query": "Montreal"},
    "insights no location": {},
}
working = None
for label, extra in variants.items():
    data = call(label, "/v2/insights", base_params | extra)
    if _results(data) and working is None and extra:
        working = label
        describe_entity(_results(data)[0])

print("\n3) Tags endpoint (for critic / tag filters)")
call("tags search", "/v2/tags", {"filter.query": "jazz", "take": 5})

print(f"\nWorking location filter: {working or 'NONE FOUND'}")
print("Raw responses saved in .cache/smoke/. Next: update docs/research/01-qloo-api.md")
