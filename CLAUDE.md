# TasteWalk - Project Brief & Working Rules
> Read this file at the start of every session. It is the source of truth for scope,
> rules, and priorities. If a request conflicts with it, flag the conflict before acting.

## 1. The project in one paragraph
**TasteWalk** turns a person's favorite things (artists, films, restaurants, brands) and a city
into a walkable, personalized day itinerary. A multi-agent workflow uses the **Qloo taste graph**
to build a taste profile and find matching places, plans a realistic walking route, and a critic
agent explains why each stop fits. The UI shows a side-by-side comparison against an LLM-only
itinerary so Qloo's value is visible. First city: Montreal.

- **Hackathon:** Qloo Agentic Hackathon (Devpost)
- **Deadline:** TBD - confirm exact date/time/timezone on Devpost (about 2 days from Oct 29, 2026). Internal target: submit with a 3h buffer.
- **Finalists** may appear on air Nov 5 (Jason Calacanis, Cedric the Entertainer, Alex Elias) - keep availability open.
- **Entrant:** solo. Check eligibility/location rules on Devpost (not yet verified).

## 2. Non-negotiables (from the hackathon requirements)
- [ ] Functional demo app, hosted externally and fully published (no local-only, no private access).
- [ ] Public code repo (GitHub) with all source, assets, and run instructions.
- [ ] Open-source license (MIT) file visible in the repo's About section.
- [ ] Text description: what it does, key features, what makes it Qloo-powered.
- [ ] Demo video is NOT required - the live app is what judges use.
- [ ] The app must NOT work the same without Qloo. Qloo is the differentiator.

## 3. Judging criteria (optimise all four)
1. **Technological Implementation** - deep, non-trivial Qloo use (search, entity resolution, insights/recommendations, tags, location filters, signals), working code.
2. **Design** - complete product: input, map, timeline, "why this stop" cards.
3. **Potential Impact** - specific audience (travelers, locals, tourism boards, local businesses) and real problem (generic tourist lists).
4. **Quality of Idea** - non-obvious Qloo use; the side-by-side LLM-vs-Qloo comparison is the proof.

## 4. Architecture (see docs/architecture.md)
| Step | Agent | Tools | Output |
|---|---|---|---|
| 1 | **Taste agent** | Qloo search (resolve entities), Qloo insights (recommend places by signals + location) | TasteProfile + candidate places |
| 2 | **Planner agent** | LLM + routing/distance | Ordered stops with times |
| 3 | **Critic agent** | LLM + Qloo tags/affinity | Per-stop "why it fits" + route sanity check |
| - | **Baseline** | LLM only, no Qloo | Itinerary shown side by side |

### Key design decisions (do not change without discussing)
- Qloo returns the candidates; the LLM never invents places. Every stop must carry a Qloo entity ID.
- LLM outputs validated JSON (Pydantic), never executed code.
- Route feasibility (distance, opening hours, total walking time) is computed in code, not trusted to the LLM.
- Cache every Qloo response on disk by request hash.
- Demo must have 3-4 curated example profiles that reliably work.

## 5. Verify before assuming
- Base URL `https://hackathon.api.qloo.com` and header `X-Api-Key` (seen in hackathon forum posts - confirm in docs).
- Entity type values use URNs, e.g. `urn:entity:movie`, `urn:entity:brand`, `urn:entity:place` - confirm the full list.
- Exact insights endpoint path/params (`/v2/insights`?), location filter format, tag filters, and whether results include coordinates/opening hours. Run `scripts/smoke_test_qloo.py` first and record findings in `docs/research/01-qloo-api.md`.
- If Qloo lacks coordinates/hours for places, geocode with a free service and say so honestly in the README.

## 6. Repo conventions
- Python 3.11, `uv`, `ruff`, `pytest`.
- Secrets only in `.env`; `.env.example` lists every variable.
- Small commits; `main` is always demo-able.
- Every module has a docstring explaining its role.
- `docs/devpost/` holds drafts of every submission field.

## 7. Working agreement with Claude
- Claude Code builds and runs code. Claude chat handles research and writing.
- Claude does not create accounts, type API keys into websites, or submit the form; Atabak does.
- Prefer end-to-end slices over perfect components. Demo-ability first.
- If something takes longer than planned, say so and propose a cut.
