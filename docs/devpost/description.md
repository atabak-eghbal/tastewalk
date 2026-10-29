# Devpost project description (draft)

<!-- Fill the TODOs after the Qloo smoke test and the first real runs. Keep claims verifiable. -->

## Inspiration
Every "things to do in Montreal" list is the same: the same basilica, the same bagel shops, the
same market. Ask a general-purpose AI and you get that same list back, just reworded. But the
best days in a new city happen when a friend who *gets* your taste walks you around. We wanted to
build that friend, and Qloo's taste graph is what makes it possible.

## What it does
TasteWalk turns the things you already love (artists, films, shows, books, brands) into a
walkable day in the city:

- **Your taste profile**: each favorite is matched to a Qloo entity, and shared themes are shown.
- **Places that fit**: Qloo recommends places in the city that people with your taste love.
- **A real walking route**: stops in one walkable neighbourhood, in the shortest order, with
  arrival times and walking minutes between stops, shown on a map and a timeline.
- **"Why it fits you" cards**: each stop explains its link to your taste, using the Qloo tags it
  shares with your favorites.
- **Side by side with an LLM-only plan**: the same request without Qloo, so you can see the
  difference for yourself.

Try it: open the live demo and click an example, e.g. "Indie music & arthouse film".

## How we built it
- **Taste agent** - Qloo search resolves each favorite to an entity; Qloo insights returns
  places for those entities as signals, filtered to the city. <!-- TODO: exact endpoints/params -->
- **Planner agent** - code finds the walkable cluster with the highest taste affinity; an LLM picks a
  varied set of stops *by Qloo ID only*; code orders them along the shortest walking path and
  computes times.
- **Critic agent** - code computes which Qloo tags each stop shares with the user's taste; the
  LLM turns those facts into a short explanation; code checks leg length, total walking and
  opening hours where available.
- **Baseline** - the same request sent to the LLM with no Qloo data.
- Python, FastAPI with Server-Sent Events (you watch each agent work), Pydantic-validated LLM
  output, a disk cache for every API call, Leaflet + OpenStreetMap, Docker. <!-- TODO: host -->

## What makes it Qloo-powered
The LLM never invents a place. Every stop on the TasteWalk route comes from Qloo and carries a
Qloo entity ID; the planner can only choose among Qloo candidates, and any other ID is dropped.
Remove Qloo and TasteWalk has nothing to recommend. The LLM-only column shows the alternative:
famous, generic places with no IDs, no coordinates and no walking times.

Qloo features used: <!-- TODO confirm --> entity search across types, insights with entity
signals and a location filter, affinity scores, and tags.

## Challenges we ran into
<!-- TODO: real ones from the build, e.g. Qloo response shape, places without coordinates, ... -->
- Keeping the LLM honest: structured output validated against the candidate list, so it can't
  "helpfully" add a famous place that Qloo didn't recommend.
- Making the route walkable: a taste match on the other side of the city is no use, so candidates
  are clustered by walking distance before stops are chosen.

## Accomplishments we're proud of
- The side-by-side comparison makes Qloo's value visible in seconds.
- Every recommendation can be traced: Qloo ID, affinity score and shared tags on every card.

## What we learned
<!-- TODO -->

## What's next
- More cities (only the city centre and radius are city-specific).
- Real street routing and opening hours for every stop.
- A version for tourism boards and local businesses: "which visitors would love this place?"

## Built with
python, fastapi, pydantic, qloo-api, openai-compatible-llm, leaflet, openstreetmap, docker
<!-- TODO: host -->
