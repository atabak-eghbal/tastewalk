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
from pydantic import BaseModel, ValidationError
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool

from tastewalk.config import load_settings
from tastewalk.dev_fake import fake_client
from tastewalk.examples import EXAMPLES
from tastewalk.loop import make_clients, run
from tastewalk.schemas import FavoriteType, UserInput

STATIC = Path(__file__).parent / "static"
log = logging.getLogger("tastewalk.app")
RATE_LIMIT = 8  # plans per IP per minute (protects Qloo/LLM quotas on the public demo)
PREWARM_GAP_S = 30  # one plan is ~6k LLM tokens; Groq free allows 8k/min


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
    hits: dict[str, deque[float]] = defaultdict(deque)

    def prewarm() -> None:
        """Run every example once at boot so judges get instant, cached results."""
        for ex_id, ex in EXAMPLES.items():
            last = None
            for last in run(ex["input"], qloo, llm):
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
            "cities": ["Montreal"],
            "types": [{"value": t.value, "label": t.name.replace("_", " ")} for t in FavoriteType],
            "examples": [
                {"id": k, "label": v["label"], "input": v["input"].model_dump(mode="json")}
                for k, v in EXAMPLES.items()
            ],
        }

    def _check_rate(ip: str) -> None:
        now, q = time.monotonic(), hits[ip]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            raise HTTPException(429, "Too many requests, try again in a minute")
        q.append(now)

    @app.get("/api/plan")
    async def plan(q: str, request: Request) -> EventSourceResponse:
        try:
            user = UserInput.model_validate_json(q)
        except ValidationError as e:
            raise HTTPException(422, e.errors(include_url=False)) from e
        _check_rate(request.client.host if request.client else "?")

        async def events():
            async for ev in iterate_in_threadpool(run(user, qloo, llm)):
                payload = {"step": ev.step, "message": ev.message, "data": _jsonable(ev.data)}
                yield {"data": json.dumps(payload)}

        return EventSourceResponse(events())

    return app


app = create_app()
