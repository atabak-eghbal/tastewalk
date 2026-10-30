# Handoff: state of TasteWalk (Oct 30, 2026, ~5:35 PM ET)

Read CLAUDE.md first, then this file. Everything below was true at commit time; verify before acting.

## Deadline
Devpost closes **Oct 30, 11:45 PM ET** (Atabak confirmed). Aim to submit by **10:45 PM ET**.
Atabak does the submitting, account actions and making the repo public; Claude prepares everything.

## What is live
- Demo: https://tastewalk-fy6u.onrender.com (Render free plan, Docker, auto-deploys on push to `main`).
- Render env vars (set in the Render dashboard, not from `.env`): `QLOO_API_KEY`, `LLM_API_KEY` (Groq,
  starts `gsk_`), `LLM_BASE_URL=https://api.groq.com/openai/v1`, `LLM_MODEL=openai/gpt-oss-120b`.
- City: **Vancouver** (changed from Montreal on Oct 30 per Atabak). Montreal is still configured in code.
- 4 examples: `indie`, `design`, `anime`, `streetwear` (`/?example=indie` etc.). All verified live:
  each finishes in ~2 s once the startup prewarm has run (~2 min after a deploy/restart).

## Architecture in one breath
Taste agent (Qloo search + insights per day slot, explainability) -> Planner (LLM picks by Qloo ID;
code: compact area, one coffee/meal/drinks, no chains, day order, swaps closed stops) -> Critic
(explainability -> "because you love X", LLM sentence) -> Baseline (LLM only) -> Fact-checker
(code, no LLM: Qloo search to locate each LLM place, strict name match, chains = ambiguous,
OpenStreetMap/Nominatim as second source, hours + walking via our routing code). See
docs/architecture.md and README.md.

## Key decisions (don't undo without asking Atabak)
- Qloo data is never committed (Qloo terms). Server-side cache only (`.cache/`, gitignored).
- The examples' **LLM-only plans are frozen** in `src/tastewalk/example_baselines.json` (LLM output,
  plus OpenStreetMap verdicts), so the live demo, README and video show the same numbers. Custom
  favorites get a live LLM plan. **If you change an example's input, regenerate that file** (see
  git history of commit dfc91e8 for the script pattern) and `docs/results/fact_check_examples.json`.
- Fact-check wording: "not found in Qloo or OpenStreetMap", never "fake/made up". Matching is
  strict on purpose (simulated judges caught false matches earlier).
- Proof headline leads with what the fact-check finds: long walk / closed stops / not found.
- Numbers in README/Devpost come from `docs/results/fact_check_examples.json` only.

## Headline numbers (Vancouver, from the results file)
- Indie: Qloo located all 6 LLM places, but the LLM's walking day is 18.4 km with a 72-min leg and
  the Orpheum is closed on arrival. TasteWalk: 3.1 km, no leg over 15 min.
- 4 examples, 24 LLM-only stops: 11 located in Qloo, 6 only on OpenStreetMap, 7 in neither.
  Granville Island Public Market and the Vancouver Art Gallery appear in 3 of 4 LLM-only plans.
- TasteWalk: 24 Qloo places, 2.9-4.5 km per day, longest leg 22 min, hours checked for 18/24.

## Remaining work, in order
1. **Video v3** (Vancouver, static shots + hard cuts, NO zoom/pan/animated scroll; Atabak dislikes
   camera motion). A background agent in the old session was making it; check
   `~/Desktop/tastewalk_video/` for `tastewalk_demo_v3.mp4`. If it isn't there, rebuild from the
   pipeline in `~/Projects/tastewalk-video-tools/` (`v3/` = latest scripts: shots.py, cards.py,
   narrate.py; Kokoro TTS voice af_heart; Playwright via `uv run --no-project --with playwright`).
   Verify: duration ≤ 1:45, picture = audio length, a contact sheet you LOOK at, and consecutive
   frames inside a shot identical except real UI changes (no motion). Never show keys.
2. **Atabak:** make the GitHub repo public; About: website = demo URL, topics, MIT license visible.
   Then check the public repo page renders (README images, links) in a logged-out browser.
3. **Atabak:** keep-awake ping on cron-job.org every 5 min to `/healthz` (GitHub cron is throttled).
4. Tag a release `v1.0.0` with short notes (Claude can do it via `gh` once the repo is public).
5. Give Atabak the final Devpost text in chat, ready to paste, from `docs/devpost/description.md`
   (elevator pitch is 167 chars, limit 200). Fill any [brackets]. He submits.
6. Optional, if time: the judges said "agentic" is thin. Idea: critic rejects a stop with a weak
   explainability link and the planner replaces it, shown live in the agent steps (~30 min).
   Re-run tests, re-verify the 4 examples live, and keep numbers in docs consistent if routes change.

## How to work on it
- `uv sync`; tests `uv run pytest -q` (34 pass, no network); lint `uv run ruff check . && uv run ruff format .`
- Local server: `TASTEWALK_PREWARM=0 uv run uvicorn app.main:app --port 8011`
- Screenshot: `uv run --no-project --with playwright python ~/Projects/tastewalk-video-tools/screenshot.py "http://localhost:8011/?example=indie" out.png 1280 [dark]`
- Live check of an example (SSE): see `curl -N "https://tastewalk-fy6u.onrender.com/api/plan?q=<UserInput JSON, url-encoded>"`.
- Never print `.env`. Commit messages end with the Co-Authored-By line used in git log.
- Groq free tier: 1000 requests/day, 8k tokens/min (a plan ~6k tokens). Qloo returns 429 on bursts;
  the client retries. Nominatim: 1 request/s, identified User-Agent, cached.

## Simulated judge feedback (5 personas, before the fixes)
Scores were ~6-8/10. Fixed since: false fact-check matches, circular headline, stale numbers,
rate-limit dead ends, double lunches, chains, theme-tag noise, proof below the fold, mobile
scorecard, garbage-input resolution. Not fixed: "agentic" depth (item 6), named-buyer depth
beyond the Devpost "Who it's for" section.
