"""OpenAI-compatible LLM client that returns validated Pydantic objects (JSON only, cached)."""

from __future__ import annotations

import json
import logging
from typing import TypeVar

from openai import OpenAI, OpenAIError, RateLimitError
from pydantic import BaseModel, ValidationError

from .cache import DiskCache, request_key

log = logging.getLogger(__name__)
TIMEOUT_S = 40  # a stalled call must not freeze the demo; callers fall back without the LLM
MAX_RETRIES = 3  # the SDK retries 429s after the provider's retry-after (Groq free: 8k tokens/min)
T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(
        self, api_key: str, base_url: str, model: str, cache: DiskCache, fallback_model: str = ""
    ):
        self.model = model
        self.fallback_model = fallback_model  # used when the main model's daily quota is spent
        self.cache = cache
        self._client = (
            OpenAI(api_key=api_key, base_url=base_url, timeout=TIMEOUT_S, max_retries=MAX_RETRIES)
            if api_key
            else None
        )

    def _create(self, model: str, messages: list[dict]):
        return self._client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,  # stable picks: the live demo must match the docs
        )

    def json(self, system: str, user: str, schema: type[T], retries: int = 1) -> T:
        """Ask for JSON matching `schema`; validate it; retry once with the error on failure."""
        schema_json = json.dumps(schema.model_json_schema())
        sys_prompt = (
            f"{system}\n\nReply with ONLY a JSON object matching this schema:\n{schema_json}"
        )
        messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}]
        key = request_key("llm", {"model": self.model, "messages": messages})
        cached = self.cache.get(key)
        if cached is not None:
            return schema.model_validate(cached)
        if self._client is None:
            raise LLMError("LLM not configured (set LLM_API_KEY and LLM_MODEL)")

        last_err: Exception | None = None
        for _ in range(retries + 1):
            try:
                resp = self._create(self.model, messages)
            except RateLimitError as e:
                # Groq free tier: a daily token cap per model. Another model has its own quota.
                if not self.fallback_model or "per day" not in str(e):
                    raise LLMError(f"LLM call failed: {type(e).__name__}: {e}") from e
                log.warning("%s daily quota spent, using %s", self.model, self.fallback_model)
                try:
                    resp = self._create(self.fallback_model, messages)
                except OpenAIError as e2:
                    raise LLMError(f"LLM call failed: {type(e2).__name__}: {e2}") from e2
            except OpenAIError as e:  # rate limit, timeout, outage: callers fall back
                raise LLMError(f"LLM call failed: {type(e).__name__}: {e}") from e
            text = resp.choices[0].message.content or ""
            try:
                obj = schema.model_validate_json(_strip_fences(text))
            except ValidationError as e:
                last_err = e
                messages = messages + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": f"Invalid JSON for the schema: {e}. Fix it."},
                ]
                continue
            self.cache.set(key, obj.model_dump(mode="json"))
            return obj
        raise LLMError(f"LLM output failed validation: {last_err}")


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()
