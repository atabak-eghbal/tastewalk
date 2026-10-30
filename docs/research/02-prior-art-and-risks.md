# Prior art and failure risks
Researched 2026-10-30, 1:30 PM ET. Devpost pages return 403 to automated fetches, so project
details come from search summaries and are unverified.

## Is Qloo an LLM? (verified)
No. Qloo is a taste graph (search, insights, tags). Its own chat agent in the hackathon kit
(`qloo explore`) needs a separate model provider (`qloo setup --model`). We keep our own LLM.

## Prior art: earlier Qloo hackathon (2025, LLM + Qloo, $10k grand prize)
"Qloo + LLM travel itinerary" is a crowded idea. Projects found:
- **TasteTrip**: free text -> Qloo -> destination + places -> second model writes a day-by-day plan;
  adds weather, photos, QR codes, PDF.
- **Globetrotter AI**: Qloo place matching, Gemini itinerary with cost breakdown.
- **VibeVoyage**: LLM extracts interests, then queries Qloo.
- **FlavorJourney**: food-only, Qloo + DeepSeek.
- **Prism AI**: LLM agent calls several Qloo endpoints to build an evening plan.
- Also TasteJourney, TasteTrails, Cultural Compass, Navay (not inspected).

Typical pattern: Qloo returns places, then the LLM writes the itinerary. Nothing found checks that the plan is
walkable or open, or proves what Qloo added. **Our differentiators, to make visible in UI and copy:**
1. Side-by-side LLM-only vs Qloo, with "unverified" labels: proof of Qloo's value.
2. "Why it fits" from Qloo explainability (which favorite drove each pick), not LLM vibes.
3. Walking route, times and opening hours computed in code; the LLM never adds a place.

## Known failure modes of LLM itineraries (literature)
- Non-existent places; 90% of ChatGPT city itineraries had at least one error, 52% visited places
  outside opening hours (SEO Travel study, trade press; methodology unclear).
- LLM plans average >17 km straight-line between stops vs 7.3 km in real plans (TripTailor).
- Category confusion (restaurant listed as attraction), fabricated details (TripTailor).
- Infeasible timing (Iti-Validator).
These are exactly what our baseline column should show and our pipeline prevents.

## Risks for our demo, ranked
| # | Risk | Status / mitigation |
|---|---|---|
| 1 | **Gemini free tier = 20 requests/day for gemini-2.5-flash** (verified from the 429 body, resets midnight PT). Each plan uses 3 calls, prewarm uses 12. | Exhausted today. Needs a paid key or another provider. Code falls back to Qloo-only (tested). |
| 2 | Render free restarts wipe `/tmp` cache; every restart re-runs prewarm (12 LLM calls, 24 Qloo calls). | Keep-awake ping every 10 min. Retry/backoff on 429. |
| 3 | Per-IP rate limit may see Render's proxy IP, so all judges share 8 plans/min. | Handled: Dockerfile runs uvicorn with `--proxy-headers --forwarded-allow-ips='*'`. |
| 4 | Cold custom plans take 50-85 s (sequential LLM calls). | Streamed progress; run baseline in parallel; consider turning Gemini thinking off. |
| 5 | Favorites that resolve to the wrong entity (homonyms). | Show the matched entity in the taste profile so users can see it. |
| 6 | Qloo quota/outage during judging (limits unknown). | Examples prewarmed and cached on disk. |
| 7 | Critic LLM over-claims facts not in Qloo data. | Prompt gives only Qloo facts; template fallback. |
| 8 | Free-tier hosting cold start (~1 min) if the ping fails. | GitHub Actions ping; check it runs. |

## Probe: can Qloo audit the LLM-only plan? (verified 2026-10-30)
- `GET /search?types=urn:entity:place` finds most LLM-named places with address + coordinates
  (Wilensky's, Drawn & Quarterly, L'Express, Notre-Dame Basilica). Fuzzy matches can be wrong
  ("Phonopolis" -> "La Grande Roue", "Le Saint-Edouard" -> a hotel), so a name check is required.
- `GET /v2/insights` with `filter.results.entities=<ids>` (also `filter.entities`) scores exactly
  those places against the user's favorites. Affinity is absolute: our route scored the same
  (0.80-0.82) in slot calls and in this scoring call.
- Indie example: Qloo route 0.80-0.82, LLM picks 0.76-0.81. The taste gap is small and honest;
  the bigger gaps are existence, hours and walking distance, which Qloo coordinates let us compute.

**Decision:** keep TasteWalk, add "Qloo fact-checks the LLM plan" (existence, open at the planned
time, walking km, taste match), the step no prior Qloo itinerary project shows.

## Sources
- https://github.com/qloo/qloo-hackathon-kit (starter/agent-chat/README.md)
- https://devpost.com/software/tastetrip, /globetrotter-ai-2-o, /vibevoyage, /flavorjourney,
  /prism-ai-your-personal-experience-curator, /tastetrails
- https://arxiv.org/pdf/2508.01432 (TripTailor), https://arxiv.org/pdf/2510.24719 (Iti-Validator)
- https://www.travelnews.co.za/article/ai-generated-itineraries-lead-travellers-astray
- Gemini 429 response body, 2026-10-30
