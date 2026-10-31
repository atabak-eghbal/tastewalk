"""FastAPI app: serves the single-page UI and streams agent progress over Server-Sent Events.

Run locally:  uv run uvicorn app.main:app --reload
UI dev without a Qloo key:  TASTEWALK_FAKE_QLOO=1 uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool

from tastewalk.config import load_settings
from tastewalk.dev_fake import fake_client
from tastewalk.examples import EXAMPLES
from tastewalk.llm import LLMError
from tastewalk.loop import make_clients, run
from tastewalk.osm import OSMClient
from tastewalk.parse import parse_favorites
from tastewalk.schemas import FavoriteType, UserInput

STATIC = Path(__file__).parent / "static"
log = logging.getLogger("tastewalk.app")
# Any city works (geocoded); these are just suggestions in the city box.
CITY_SUGGESTIONS = [
    "Vancouver",
    "Seoul",
    "Tokyo",
    "New York",
    "London",
    "Paris",
    "Berlin",
    "Mexico City",
    "Toronto",
    "Montreal",
    "Barcelona",
    "Lisbon",
    "Sydney",
    "Melbourne",
    "Amsterdam",
    "Copenhagen",
    "Chicago",
    "San Francisco",
]
RATE_LIMIT = 20  # custom plans per IP per minute (examples are cached and don't count)
PREWARM_GAP_S = 60  # each example's planner + critic ~4-6k LLM tokens; Groq free: 8k/min


class ParseIn(BaseModel):
    text: str = Field(min_length=2, max_length=500)


def _jsonable(x: Any) -> Any:
    if isinstance(x, BaseModel):
        return x.model_dump(mode="json")
    if isinstance(x, list):
        return [_jsonable(i) for i in x]
    return x


def create_app(fake: bool | None = None) -> FastAPI:
    settings = load_settings()
    if fake is None:
        fake = os.getenv("TASTEWALK_FAKE_QLOO") == "1"
    qloo, llm = make_clients(settings)
    if fake:
        qloo = fake_client(settings.cache_dir / "fake")
    if not settings.has_llm:
        llm = None
    osm = None if fake else OSMClient(qloo.cache)
    hits: dict[str, deque[float]] = defaultdict(deque)

    def prewarm() -> None:
        """Run every example once at boot so judges get instant, cached results."""
        for ex_id, ex in EXAMPLES.items():
            last = None
            for last in run(ex["input"], qloo, llm, osm=osm):
                pass
            log.warning("prewarm %s: %s", ex_id, last.step if last else "no events")
            time.sleep(PREWARM_GAP_S)

    if not fake and settings.has_qloo and os.getenv("TASTEWALK_PREWARM", "1") == "1":
        threading.Thread(target=prewarm, daemon=True, name="prewarm").start()

    app = FastAPI(title="TasteWalk", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/api/meta")
    def meta() -> dict:
        return {
            "fake_data": fake,
            "has_qloo": fake or settings.has_qloo,
            "has_llm": llm is not None,
            "cities": CITY_SUGGESTIONS,
            "types": [{"value": t.value, "label": t.name.replace("_", " ")} for t in FavoriteType],
            "examples": [
                {"id": k, "label": v["label"], "input": v["input"].model_dump(mode="json")}
                for k, v in EXAMPLES.items()
            ],
        }

    def _rate_ok(ip: str) -> bool:
        now, q = time.monotonic(), hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if not q:
            hits.pop(ip, None)  # keep the table small
            q = hits[ip]
        if len(q) >= RATE_LIMIT:
            return False
        q.append(now)
        return True

    @app.post("/api/parse")
    def parse(body: ParseIn, request: Request) -> dict:
        """'I love Radiohead and Ghibli films' -> favorites for the form (typed or spoken)."""
        if llm is None:
            raise HTTPException(503, "Free-text input needs an LLM; add favorites below instead.")
        if not _rate_ok(request.client.host if request.client else "?"):
            raise HTTPException(429, "The demo is busy. Try again in a minute.")
        try:
            favs = parse_favorites(llm, body.text)
        except LLMError as e:
            raise HTTPException(503, "Couldn't read that right now; add favorites below.") from e
        return {"favorites": [f.model_dump(mode="json") for f in favs]}

    @app.get("/api/plan")
    async def plan(q: str, request: Request) -> EventSourceResponse:
        try:
            user = UserInput.model_validate_json(q)
        except ValidationError as e:
            raise HTTPException(422, e.errors(include_url=False)) from e
        is_example = any(ex["input"] == user for ex in EXAMPLES.values())
        allowed = is_example or _rate_ok(request.client.host if request.client else "?")

        async def events():
            if not allowed:  # an SSE error event: EventSource can't read HTTP status codes
                msg = "The demo is busy. Try again in a minute, or pick one of the examples."
                yield {"data": json.dumps({"step": "error", "message": msg, "data": None})}
                return
            async for ev in iterate_in_threadpool(run(user, qloo, llm, osm=osm)):
                payload = {"step": ev.step, "message": ev.message, "data": _jsonable(ev.data)}
                yield {"data": json.dumps(payload)}

        return EventSourceResponse(events())

    return app


app = create_app()
