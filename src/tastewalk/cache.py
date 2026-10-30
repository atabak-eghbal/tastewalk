"""Disk cache keyed by request hash, used for every Qloo and LLM call.

The cache lives on the server only. Qloo's terms forbid storing their response data in a
public repository, so it is never committed (`.cache/` is gitignored).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def request_key(namespace: str, payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{namespace}-{hashlib.sha256(raw.encode()).hexdigest()[:24]}"


class DiskCache:
    def __init__(self, cache_dir: Path, seed_dir: Path | None = None):
        self.cache_dir = cache_dir
        self.seed_dir = seed_dir

    def get(self, key: str) -> Any | None:
        for d in (self.seed_dir, self.cache_dir):
            if d is None:
                continue
            path = d / f"{key}.json"
            if path.exists():
                return json.loads(path.read_text())
        return None

    def set(self, key: str, value: Any) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_dir / f"{key}.json.tmp"
        tmp.write_text(json.dumps(value, ensure_ascii=False))
        tmp.replace(self.cache_dir / f"{key}.json")
