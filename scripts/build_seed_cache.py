"""Run every curated example against the real APIs and save the responses as the seed cache.

Run: uv run python scripts/build_seed_cache.py
Writes to data/seed_cache/ (committed), so the examples work on the deployed app even if the
host wipes its disk or Qloo/the LLM is slow or down during judging. Re-run after changing
prompts, examples or Qloo parameters, since those change the cache keys.
"""

import sys

from tastewalk.cache import DiskCache
from tastewalk.config import load_settings
from tastewalk.examples import EXAMPLES
from tastewalk.llm import LLM
from tastewalk.loop import run
from tastewalk.qloo import QlooClient

settings = load_settings()
if not settings.has_qloo:
    sys.exit("QLOO_API_KEY is empty in .env")
# Write straight into the seed dir; ignore the runtime cache so every response is captured.
cache = DiskCache(settings.seed_cache_dir)
qloo = QlooClient(settings.qloo_api_key, settings.qloo_base_url, cache)
llm = LLM(settings.llm_api_key, settings.llm_base_url, settings.llm_model, cache)
if not settings.has_llm:
    print("warning: no LLM configured; seeding Qloo responses only", file=sys.stderr)
    llm = None

failed = []
for ex_id, ex in EXAMPLES.items():
    print(f"\n== {ex_id}: {ex['label']}")
    last = None
    for ev in run(ex["input"], qloo, llm):
        print(f"  [{ev.step}] {ev.message}")
        last = ev
    if last is None or last.step != "done":
        failed.append(ex_id)

n = len(list(settings.seed_cache_dir.glob("*.json")))
print(f"\nSeed cache: {n} files in {settings.seed_cache_dir}")
if failed:
    sys.exit(f"Examples that did not finish: {', '.join(failed)}")
