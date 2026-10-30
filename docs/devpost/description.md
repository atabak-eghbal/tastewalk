# Devpost project description (draft)

<!-- Numbers come from docs/results/fact_check_examples.json. Keep claims verifiable. -->

**Elevator pitch (≤200 chars):**
Tell it what you love; get a walkable day in Montreal built from Qloo's taste graph, then watch Qloo fact-check an AI-only plan: 24/24 of our stops verified vs 4/24 of the AI's.

## Inspiration
Every "things to do in Montreal" list is the same: the same basilica, the same bagel shops, the
same market. Ask a general-purpose AI and you get that list back, reworded, and studies of AI
trip plans keep finding places that don't exist, stops scheduled while they're closed, and stops
far apart. The best days in a new city happen when a friend who *gets* your taste walks you
around. We wanted to build that friend, and to prove it beats the AI-only answer rather than claim it.

## What it does
TasteWalk turns the things you already love (artists, films, shows, books, brands) into a
walkable day in the city:

- **Your taste in Qloo**: each favorite is matched to a Qloo entity, with the themes they share.
- **Places that fit**: Qloo recommends places in the city that people with your taste love, for
  each part of the day (coffee, culture, shopping, food, drinks).
- **A real walking route**: stops in one walkable area, in a sensible day order, with arrival
  times, walking minutes and opening hours checked, on a map and a timeline.
- **"Why it fits you" cards**: Qloo's explainability says which of *your* favorites drove each
  pick; the LLM only turns those facts into a sentence.
- **The proof**: the same request goes to an LLM with no Qloo. Then a fact-checker looks up every
  place the LLM named in Qloo: can it be located, is it open at the planned time, how far apart
  are the stops, how well does it match your taste. A scorecard puts both plans side by side.

Try it: open the live demo and click an example card, e.g. "Indie music & arthouse film".

## Results (4 example profiles, one run each, Oct 30)
| | With Qloo | LLM only |
|---|---|---|
| Stops Qloo can verify (place, coordinates, Qloo ID) | **24 of 24** | **4 of 24** |
| Opening hours checked at the planned time | 24 of 24 | only for the 4 located |
| Walking distance | measured: 2.8-4.8 km per day | can't be measured for most stops |
| Taste match (Qloo affinity, where comparable) | higher in 3 of 3 (0.79/0.81/0.76) | 0.78/0.73/0.62 |

"Not in Qloo" doesn't prove a place is invented: Qloo's coverage isn't complete, and we say so in
the app. It means nobody can confirm the place, its hours or the walk before you go.

## How we built it
- **Taste agent**: Qloo `GET /search` resolves each favorite to an entity. Qloo `GET /v2/insights`
  (`filter.type=urn:entity:place`, `signal.interests.entities`, `filter.location` as a POINT with
  a radius, `filter.tags` per day slot, `feature.explainability=true`) returns candidate places
  with coordinates, hours, affinity and which favorites drove each one.
- **Planner agent**: code picks the most walkable cluster; an LLM picks a varied set *by Qloo ID
  only* (anything else is dropped); code orders the day, schedules times, and swaps out stops
  that would be closed on arrival.
- **Critic agent**: explainability shares become "because you love X" chips; the LLM writes a
  short explanation from Qloo facts only; code checks leg length, total walking and hours.
- **Baseline + fact-checker**: the LLM answers alone; then Qloo `GET /search` locates each named
  place (strict name matching, so a liquor store inside a market doesn't count as the market),
  Qloo insights with `filter.results.entities` scores those exact places against the user's
  favorites, and the same routing code measures the walk.
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
- **Fair fact-checking**: Qloo's search is fuzzy ("Phonopolis" returned a Ferris wheel), so a
  naive match would accuse the LLM of things it didn't do. We match names strictly and say
  "not in Qloo", never "doesn't exist".
- **Free-tier limits**: one LLM provider's free tier allowed 20 requests a day, which we used up
  in testing. We switched to Groq, retry on rate limits, and fall back to Qloo-only text if the
  LLM is unavailable, so the route always works.
- **Qloo's data terms**: Qloo responses can't be stored in a public repo, so the server caches
  them privately and warms the example profiles at startup.

## Accomplishments we're proud of
- The scorecard turns "Qloo makes it better" into numbers a judge can check in the app.
- Every recommendation is traceable: Qloo ID, affinity and the favorites that drove it.
- Each plan streams live: you watch five agents work in sequence.

## What we learned
- A taste graph's real superpower for agents is grounding: the LLM is much more useful choosing
  and explaining among real, scored options than generating them.
- Explainability matters more than more data: "because you love Amélie" is more convincing
  than any generated paragraph.
- Measure the comparison. The taste-match gap between plans was smaller than we expected; the
  big gaps were verifiability, hours and walking, so that's what we lead with.

## What's next
- More cities (only the city centre and radius are city-specific).
- Real street routing instead of straight-line distance x 1.3.
- For tourism boards and local businesses: "which visitors would love this place?", using the
  same insights in reverse.

## Built with
python, fastapi, pydantic, qloo, groq, gpt-oss, server-sent-events, leaflet, openstreetmap, docker, render
