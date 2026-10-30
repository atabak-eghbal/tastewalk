# Devpost project description (draft)

<!-- Numbers come from docs/results/fact_check_examples.json. Keep claims verifiable. -->

**Elevator pitch (≤200 chars):**
Turn what you love into a walkable Vancouver day from Qloo's taste graph, then fact-check an AI-only plan. One example: an 18 km "walk" with a closed stop vs our 3 km.

## Inspiration
Every "things to do in Vancouver" list is the same: Granville Island, the Art Gallery, the
same steam clock. Ask a general-purpose AI and you get that list back, reworded, and studies of AI
trip plans keep finding places that don't exist, stops scheduled while they're closed, and stops
far apart. The best days in a new city happen when a friend who *gets* your taste walks you
around. We wanted to build that friend, and to prove it beats the AI-only answer rather than claim it.

## What it does
TasteWalk turns the things you already love (artists, films, shows, books, brands) into a
walkable day in Vancouver:

- **Your taste in Qloo**: each favorite is matched to a Qloo entity, with the themes they share.
- **Places that fit**: Qloo recommends places in the city that people with your taste love, for
  each part of the day (coffee, culture, shopping, food, drinks).
- **A real walking route**: stops in one walkable area, in a sensible day order, with arrival
  times, walking minutes and opening hours checked, on a map and a timeline.
- **"Why it fits you" cards**: Qloo's explainability says which of *your* favorites drove each
  pick; the LLM only turns those facts into a sentence.
- **The proof**: the same request goes to an LLM with no Qloo. A fact-checker looks up every
  place it named in Qloo, then OpenStreetMap: can it be found, is it open at the planned time,
  how far apart are the stops. A scorecard puts both plans side by side.

Try it: open the live demo and click an example card, e.g. "Indie music & arthouse film".

## Results (4 example profiles in Vancouver, Oct 30; LLM-only plans recorded so the demo matches)
**Clearest case (indie music & arthouse film):** Qloo located all 6 places the LLM named, all
real. But the LLM's "walking day" is 18.4 km with 72-, 70- and 53-minute legs, and the Orpheum is
closed when you'd arrive. TasteWalk: 3.1 km, no leg over 15 minutes.

| Across the 4 examples | TasteWalk (Qloo) | LLM only |
|---|---|---|
| Can the place be found? | 24 of 24 Qloo places (by construction) | 11 in Qloo · 6 only on OpenStreetMap · 7 in neither |
| Walking | 2.9-4.5 km per day, longest leg 22 min | indie 18.4 km, longest leg 72 min |
| Same tourist spots? | 24 stops across 4 tastes | Granville Island Market and the Art Gallery in 3 of 4 plans |
| Why each stop | which of your favorites drove it (Qloo explainability) | the LLM's own words |

"Found in neither" doesn't prove a place is invented (both sources have gaps), and the app says
so. Every LLM-named place, its verdict and its walking legs are in the repo
(docs/results/fact_check_examples.json).

## How we built it
- **Taste agent**: Qloo `GET /search` resolves each favorite to an entity. Qloo `GET /v2/insights`
  (`filter.type=urn:entity:place`, `signal.interests.entities`, `filter.location` as a POINT with
  a radius, `filter.tags` per day slot, `feature.explainability=true`) returns candidate places
  with coordinates, hours, affinity and which favorites drove each one.
- **Planner agent**: code picks the most walkable cluster; an LLM picks a varied set *by Qloo ID
  only* (anything else is dropped); code enforces a day's rhythm (one coffee, one meal, drinks
  last, no chains), orders the walk, schedules times, and swaps out stops closed on arrival.
- **Critic agent**: explainability shares become "because you love X" chips; the LLM writes a
  short explanation from Qloo facts only; code checks leg length, total walking and hours.
- **Baseline + fact-checker** (code, no LLM): the LLM answers alone; then Qloo `GET /search`
  locates each named place (strict matching: "Atwater Market" is not "Atwater Cocktail Club",
  chains with several branches are marked unclear), OpenStreetMap is the second source for
  places Qloo doesn't know, Qloo insights with `filter.results.entities` scores the located ones,
  and the same routing code checks hours and walking.
- Python, FastAPI with Server-Sent Events (you watch each agent work), Pydantic-validated JSON
  from the LLM (Groq, `openai/gpt-oss-120b`, through an OpenAI-compatible client), a server-side
  cache for every API call, Leaflet + OpenStreetMap, Docker on Render.

## What makes it Qloo-powered
The LLM never invents a place on our route. Every stop comes from Qloo and carries a Qloo entity
ID. Remove Qloo and TasteWalk has nothing to recommend, nothing to explain, and nothing to check
the AI-only answer against. Qloo features used: entity search across types, insights with entity
signals, location and category-tag filters, explainability, affinity scores, tags (vibe chips,
categories, hours), and insights restricted to specific entities to audit another plan.

## Challenges we ran into
- **Walkable, not just relevant**: the first real routes were 7.6 km with 40-minute legs and a bar
  scheduled at 11 AM. We added a compact-area pool, day-order rules (coffee first, drinks last)
  that are only used when they don't add much walking, and swaps for places closed on arrival.
- **Explaining "why" honestly**: favorites and places share almost no tag IDs in Qloo (genres vs
  ambience tags), so tag overlap was useless. Qloo's explainability feature turned out to be the
  answer: it reports how much each favorite drove each recommendation.
- **Fair fact-checking**: Qloo's search is fuzzy ("Phonopolis" returned a Ferris wheel), and our
  own simulated judges caught our first matcher (while we prototyped in Montreal) calling
  "Atwater Market" closed because it
  matched a cocktail bar. We now match names strictly, mark chains as unclear, and check
  OpenStreetMap before saying a place can't be found. "Not in Qloo" is never "made up".
- **Days that make sense**: Qloo categories are fine-grained ("Italian restaurant", "Steak
  house"), so per-category caps let through two lunches. We group stops into coffee, meal,
  drinks and other, with quotas and a day order.
- **Free-tier limits**: one LLM provider's free tier allowed 20 requests a day, which we used up
  in testing. We switched to Groq, retry on rate limits, and fall back to Qloo-only text if the
  LLM is unavailable, so the route always works.
- **Qloo's data terms**: Qloo responses can't be stored in a public repo, so the server caches
  them privately and warms the example profiles at startup.

## Who it's for
- **Visitors and locals**: a day that feels picked by a friend who shares your taste.
- **Destination marketers (e.g. Destination Vancouver), hotels and concierge apps**: embed it as a
  "local friend" itinerary that routes visitors past the top-10 list to independent places,
  each recommendation explainable. The same Qloo insights run in reverse answer "which visitors
  would love this neighbourhood or business?".

## Accomplishments we're proud of
- The scorecard turns "Qloo makes it better" into checks a judge can see in the app.
- Every recommendation is traceable: Qloo ID, affinity and the favorites that drove it.
- Each plan streams live: you watch three agents, the baseline and the fact-checker work.

## What we learned
- A taste graph's real superpower for agents is grounding: the LLM is much more useful choosing
  and explaining among real, scored options than generating them.
- Explainability matters more than more data: "because you love Amélie" is more convincing
  than any generated paragraph.
- Measure the comparison, and audit your own auditor. The taste-match gap between plans was
  too small to claim anything, so we dropped it; the real gaps were whether places can be found,
  their hours and the walk.

## What's next
- More cities (only the city centre and radius are city-specific).
- Real street routing instead of straight-line distance x 1.3.
- For tourism boards and local businesses: "which visitors would love this place?", using the
  same insights in reverse.

## Built with
python, fastapi, pydantic, qloo, groq, gpt-oss, openstreetmap, nominatim, server-sent-events, leaflet, docker, render
