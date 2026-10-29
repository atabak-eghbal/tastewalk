# TasteWalk

> **Tell it what you love. Get a walkable day built around your taste, not the tourist list.**

<!-- TODO: hero GIF (assets/hero.gif) -->
**Built for:** Qloo Agentic Hackathon 2026 | **Live demo:** _TBD_ | **Repo:** this one

## What it does
You enter a few favorites (artists, films, restaurants, brands) and a city. TasteWalk then:
1. **Profiles** your taste using the Qloo taste graph.
2. **Finds** places that match that taste in the city.
3. **Plans** a realistic walking route with times.
4. **Explains** why each stop fits you.
5. **Compares** the result against an LLM-only itinerary, side by side.

## What makes it Qloo-powered
<!-- TODO: list exact Qloo endpoints used: search, insights, tags, location filter -->

## Why it matters
<!-- TODO: specific audience + problem -->

## Architecture
See [docs/architecture.md](docs/architecture.md).

## Quickstart
```bash
git clone https://github.com/<you>/tastewalk && cd tastewalk
cp .env.example .env        # add your keys
uv sync
uv run python scripts/smoke_test_qloo.py
uv run uvicorn app.main:app --reload   # http://localhost:8000
```

## Honest limitations
<!-- TODO -->

## License
MIT - see [LICENSE](LICENSE).
