# Qloo API notes
Verified against `https://hackathon.api.qloo.com` on 2026-10-30 with `scripts/smoke_test_qloo.py`
and the official hackathon developer guide.

## Basics (verified)
- Auth: header `X-Api-Key: <key>`. Hackathon keys only work on the hackathon base URL.
- All endpoints are GET with query parameters.
- Invalid parameters are **silently ignored** (200 with empty or unfiltered results), so check
  every parameter against the Entity Type Parameter Guide.
- Do not use `/recommendations` or `/recs` (legacy, unsupported).
- **Caching:** private server-side caching is allowed with no time limit. **Qloo response data must
  not be stored in a public repository.** So `.cache/` is gitignored and nothing from Qloo is committed.

## Search - `GET /search` (verified)
- Params: `query`, `types` (e.g. `urn:entity:artist`), `take`.
- Response: `{"results": [entity, ...]}`. Entity keys: `entity_id` (UUID), `name`, `types`,
  `tags` (each `{name, tag_id, type, value}`), `properties`, `popularity`, `disambiguation`.
- Search `types` that worked: `artist`, `movie`, `brand`, `place`, `book`, `tv_show`, `podcast`,
  `videogame` (note: Insights uses `video_game`).
- All 16 favorites in the 4 demo profiles resolve to the right entity as the first result.

## Insights - `GET /v2/insights` (verified)
- Required: `filter.type` (we use `urn:entity:place`).
- Signals: `signal.interests.entities=<id>,<id>,...`
- Location: `filter.location=POINT(<lon> <lat>)` + `filter.location.radius=<meters>` works and
  returns `query.distance`. `filter.location.query=Montreal` also works. With no location filter,
  results are worldwide (Barcelona, Lisbon...).
- Category filter: `filter.tags=urn:tag:category:place:cafe,...` works.
- `feature.explainability=true` adds `query.explainability["signal.interests.entities"]`: a list of
  `{entity_id, score}`, i.e. how much each input favorite drove that recommendation. **This is what
  the critic uses for "why it fits".**
- Response: `{"success": true, "results": {"entities": [...]}, "query": {...}}`.
- Place entity fields we use:
  - `location.lat`, `location.lon`
  - `query.affinity` (0-1)
  - `properties.hours`: `{"monday": [{"opens": "T11:00:00", "closes": "T18:00:00", "closed": false}]}`;
    closed days are `{"opens": null, "closed": true}`
  - `properties.short_description`, `neighborhood`, `address`, `is_closed`, `image.url`
  - `tags` (each `{id, name, type}`): types include `urn:tag:category:place`, `genre:place`,
    `ambience:qloo`, `interests:qloo`, `setting:qloo`, `decor:qloo`, `amenity:qloo`...
- Latency: about 250 ms per call.

## Tags - `GET /v2/tags` (verified)
- `filter.query=<text>` + `filter.tag.types=urn:tag:category:place` -> `{"results": {"tags": [{id, name, type}]}}`.
- Category IDs we use: `cafe`, `bakery`, `museum`, `art_gallery`, `book_store`, `record_store`,
  `clothing_store`, `restaurant`, `bar`, `cocktail_bar` (all `urn:tag:category:place:<x>`).

## Decisions
- **Coordinates and hours come from Qloo**, so no geocoding service is needed.
- **Tag overlap doesn't work for "why it fits".** Favorites carry genre/style/theme tags, places
  carry ambience/decor/category tags; their IDs barely overlap. We use explainability instead.
- **Taste agent makes 6 insights calls per request:** one per day slot (coffee, culture, shopping,
  food, drinks) with a category filter, plus one general call, all with a 4 km radius around the
  city centre.
- Some tastes are close in Qloo's graph (indie music/arthouse film vs jazz/literary fiction shared
  59 of 69 candidates), so the demo profiles were chosen to be clearly different.
