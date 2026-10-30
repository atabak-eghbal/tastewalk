# Build Plan (deadline: confirm on Devpost, about 2 days out)

## Block 1 - Setup (1-2h)
- [ ] Get Qloo hackathon API key (check Devpost email)
- [x] GitHub repo `tastewalk` (private until finished), push scaffold, MIT shows in About
- [x] `uv sync` - [ ] fill `.env` (waiting on Qloo key + LLM choice)
- [ ] Run `scripts/smoke_test_qloo.py`; record endpoints/params in docs/research/01-qloo-api.md

## Block 2 - Core loop on CLI (5h)
- [x] Schemas
- [x] Qloo client with disk cache (endpoint shapes unverified)
- [x] Taste agent: resolve favorites -> insights for places in the city (Vancouver)
- [x] Planner: order stops, walking times (haversine x detour factor; OSRM optional)
- [x] Critic: why-it-fits text grounded in Qloo tags
- [x] Baseline LLM-only itinerary (untested against a real LLM)

## Block 3 - Product (5h)
- [x] FastAPI + SSE streaming of agent steps
- [x] UI: input form, map, timeline, why cards, side-by-side toggle
- [x] 4 curated example profiles (`src/tastewalk/examples.py`), all resolve in Qloo; prewarmed at app startup (no committed Qloo data)

## Block 4 - Deploy (2-3h)
- [x] Dockerfile + render.yaml + /healthz (image tested locally)
- [ ] Deploy publicly (Render / Fly.io / Railway free tier); verify works logged-out
- [ ] Put demo URL in README

## Block 5 - Polish + submit (3h)
- [ ] README final, screenshots/GIF, honest limitations
- [ ] Draft all submission fields in docs/devpost/
- [ ] Flip GitHub repo to public (kept private until finished)
- [ ] Submit with 3h buffer; recheck every required field

## Cut list (in order)
1. Opening-hours checks (only applied when Qloo returns hours anyway)
2. Multi-city support (demo is Vancouver only)
3. Map polish -> simple list + static map
