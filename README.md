# TasteWalk

> **Tell it what you love. Get a walkable day built around your taste, not the tourist list.**

<!-- TODO: hero GIF (assets/hero.gif) -->
**Built for:** Qloo Agentic Hackathon 2026 | **Live demo:** _TBD_ | **Try an example:** `/?example=indie`

## What it does
You enter a few favorites (artists, films, shows, books, brands). TasteWalk then:
1. **Profiles** your taste: each favorite is resolved to a Qloo entity.
2. **Finds** places in Montreal that people with that taste love, using Qloo's taste graph.
3. **Plans** a realistic walking route: one walkable neighbourhood, a varied mix of stops, real times.
4. **Explains** why each stop fits you, grounded in the Qloo tags it shares with your taste.
5. **Compares** the result side by side with an itinerary from an LLM alone, so you can see what Qloo adds.

## What makes it Qloo-powered
Every stop on the TasteWalk route comes from Qloo and carries a Qloo entity ID. The LLM is never
allowed to add a place: it can only choose among Qloo's candidates by ID, and anything else is dropped.

| Step | Qloo feature |
|---|---|
| Taste profile | Search / entity resolution for each favorite (artists, movies, books, brands...) |
| Candidate places | Insights: places recommended from your entities as signals, filtered to the city |
| Ranking & variety | Qloo affinity scores and category tags |
| "Why it fits" | Tags shared between your favorites and each place |

<!-- TODO after smoke test: exact endpoints and parameters used, see docs/research/01-qloo-api.md -->

Without Qloo the app has no places to offer. The LLM-only column shows what you get instead:
famous, generic spots, with no proof they exist, no coordinates and no walking times.

## Why it matters
- **Travelers** get a day that feels picked by a friend who shares their taste, instead of the
  same top-10 list everyone gets.
- **Locals** discover places in their own city that match what they already love.
- **Tourism boards and local businesses** get visitors spread beyond the usual hotspots, matched
  to independent places that suit them.

## How it works
Three agents run in sequence and stream their progress to the UI:

- **Taste agent** - Qloo search + insights -> taste profile and candidate places
- **Planner agent** - code picks the most walkable cluster; the LLM picks a varied set of stops by
  Qloo ID; code orders them (shortest walking path) and schedules arrival/leave times
- **Critic agent** - code finds shared taste tags; the LLM writes a short explanation from those facts;
  code checks the route (long legs, total walking, opening hours when known)

Distances, times and route checks are always computed in code, never by the LLM. LLM output is
JSON validated with Pydantic. See [docs/architecture.md](docs/architecture.md).

## Quickstart
```bash
git clone https://github.com/atabak-eghbal/tastewalk && cd tastewalk
cp .env.example .env        # add QLOO_API_KEY, and an OpenAI-compatible LLM key + model
uv sync
uv run python scripts/smoke_test_qloo.py          # check Qloo access
uv run uvicorn app.main:app --reload              # http://localhost:8000
```

Command line:
```bash
uv run python -m tastewalk.cli --fav "Arcade Fire:artist" --fav "Amélie:movie"
```

No keys yet? `TASTEWALK_FAKE_QLOO=1 uv run uvicorn app.main:app` runs the UI on fictional demo
places (a banner says so). Tests: `uv run pytest`.

## Deploy
The repo ships a `Dockerfile` (any container host) and a `render.yaml` blueprint.
1. Render -> New -> Blueprint -> pick this repo.
2. Enter `QLOO_API_KEY`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` in the dashboard.
3. Open `/healthz`, then `/?example=indie` in a private window.

On startup the app runs the curated examples once to fill its server-side cache, so they load
instantly for visitors. Qloo responses are cached on the server only and never committed, per
Qloo's hackathon terms.

## Honest limitations
- **Montreal only** for now; the city centre and search radius are configured in code.
- **Walking distance** is straight-line distance x 1.3, not real street routing.
- **Opening hours** are checked only when Qloo returns them; otherwise they are not verified.
- **Times at each stop** use simple per-category estimates.
<!-- TODO: add anything learned from the real Qloo responses (coverage, missing coordinates...) -->

## License
MIT - see [LICENSE](LICENSE).
