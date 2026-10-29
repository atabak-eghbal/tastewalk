# Build Plan (deadline: confirm on Devpost, about 2 days out)

## Block 1 - Setup (1-2h)
- [ ] Get Qloo hackathon API key (check Devpost email)
- [ ] Public GitHub repo `tastewalk`, push scaffold, MIT shows in About
- [ ] `uv sync`, fill `.env`
- [ ] Run `scripts/smoke_test_qloo.py`; record endpoints/params in docs/research/01-qloo-api.md

## Block 2 - Core loop on CLI (5h)
- [ ] Schemas
- [ ] Qloo client with disk cache
- [ ] Taste agent: resolve favorites -> insights for places in Montreal
- [ ] Planner: order stops, walking times (OSRM or haversine)
- [ ] Critic: why-it-fits text grounded in Qloo tags
- [ ] Baseline LLM-only itinerary

## Block 3 - Product (5h)
- [ ] FastAPI + SSE streaming of agent steps
- [ ] UI: input form, map, timeline, why cards, side-by-side toggle
- [ ] 3-4 curated example profiles

## Block 4 - Deploy (2-3h)
- [ ] Deploy publicly (Render / Fly.io / Railway free tier); verify works logged-out
- [ ] Put demo URL in README

## Block 5 - Polish + submit (3h)
- [ ] README final, screenshots/GIF, honest limitations
- [ ] Draft all submission fields in docs/devpost/
- [ ] Submit with 3h buffer; recheck every required field

## Cut list (in order)
1. Opening-hours checks
2. Multi-city support (keep Montreal only)
3. Map polish -> simple list + static map
