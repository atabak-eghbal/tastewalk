"""Rebuild docs/results/fact_check_examples.json from the live demo, so docs match what judges see.

Runs the 4 example profiles against the deployed app (GET, cached examples, no quota spent) and
keeps only aggregates and LLM-named place names (LLM output): no Qloo response data (Qloo terms).

    uv run python scripts/results_from_live.py [https://tastewalk-fy6u.onrender.com]
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import httpx

from tastewalk.examples import EXAMPLES

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://tastewalk-fy6u.onrender.com"
OUT = Path(__file__).resolve().parents[1] / "docs/results/fact_check_examples.json"


def done_event(ex_id: str) -> dict:
    q = EXAMPLES[ex_id]["input"].model_dump_json()
    with httpx.stream("GET", f"{BASE}/api/plan", params={"q": q}, timeout=300) as r:
        for line in r.iter_lines():
            if line.startswith("data:"):
                ev = json.loads(line[5:])
                if ev["step"] == "error":
                    raise SystemExit(f"{ex_id}: {ev['message']}")
                if ev["step"] == "done":
                    return ev["data"]
    raise SystemExit(f"{ex_id}: stream ended without a result")


def verdict(c: dict) -> str:
    if c["ambiguous"]:
        return "chain_branch_unclear"
    if c["found"]:
        return "located_in_qloo"
    return {True: "openstreetmap_only", False: "found_in_neither"}.get(c["in_osm"], "not_checked")


rows, tot = (
    [],
    dict.fromkeys(
        [
            "llm_stops",
            "located_in_qloo",
            "openstreetmap_only",
            "found_in_neither",
            "closed_at_planned_time",
            "tastewalk_stops",
            "tastewalk_with_hours",
            "template_explanations",
        ],
        0,
    ),
)
for ex_id in EXAMPLES:
    d = done_event(ex_id)
    it, a = d["qloo_itinerary"], d["baseline_audit"]
    stops = it["stops"]
    templ = sum(s["why_it_fits"].startswith("Picked for you because") for s in stops)
    rows.append(
        {
            "example": ex_id,
            "tastewalk_stops": len(stops),
            "tastewalk_km_estimated": it["total_km"],
            "tastewalk_longest_leg_min": max((s["walk_minutes_from_prev"] or 0) for s in stops),
            "tastewalk_stops_with_hours": sum(1 for s in stops if s["place"]["hours"]),
            "llm_km_between_located": a["walk_km"],
            "llm_longest_leg_min": a["longest_leg_min"],
            "llm_stops": [
                {
                    "name": c["name"],
                    "verdict": verdict(c),
                    "open_at_planned_time": c["open"],
                    "walk_min_from_previous": c["walk_minutes_from_prev"],
                }
                for c in a["stops"]
            ],
        }
    )
    tot["llm_stops"] += a["total"]
    tot["located_in_qloo"] += a["found"]
    tot["openstreetmap_only"] += a["in_osm"]
    tot["found_in_neither"] += a["nowhere"]
    tot["closed_at_planned_time"] += a["closed"]
    tot["tastewalk_stops"] += len(stops)
    tot["tastewalk_with_hours"] += rows[-1]["tastewalk_stops_with_hours"]
    tot["template_explanations"] += templ
    print(
        ex_id,
        it["total_km"],
        "km, longest leg",
        rows[-1]["tastewalk_longest_leg_min"],
        "| LLM:",
        a["found"],
        "in Qloo,",
        a["in_osm"],
        "OSM only,",
        a["nowhere"],
        "neither,",
        a["closed"],
        "closed,",
        a["walk_km"],
        "km, longest",
        a["longest_leg_min"],
        "| template why:",
        templ,
        "|",
        " / ".join(s["place"]["name"] for s in stops),
    )

commit = subprocess.run(
    ["git", "rev-parse", "--short", "HEAD"], check=True, capture_output=True, text=True
).stdout.strip()
OUT.write_text(
    json.dumps(
        {
            "date": "2026-10-30",
            "city": "Vancouver",
            "source": BASE,
            "commit": commit,
            "llm_model": "openai/gpt-oss-120b (Groq), temperature 0",
            "note": "Fetched from the live demo. LLM-only plans are frozen in src/tastewalk/example_baselines.json. "
            "Place names in llm_stops are LLM output; no Qloo response data is stored here (Qloo terms). "
            "Walking is estimated (straight line x 1.3).",
            "totals": tot,
            "rows": rows,
        },
        indent=1,
        ensure_ascii=False,
    )
)
print(tot)
