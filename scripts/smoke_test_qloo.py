"""Smoke test: confirm Qloo auth and print a sample search result.

Run: uv run python scripts/smoke_test_qloo.py
Verify endpoint paths/params against the official docs and record them in docs/research/01-qloo-api.md.
"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv()
base = os.getenv("QLOO_BASE_URL", "https://hackathon.api.qloo.com")
headers = {"X-Api-Key": os.environ["QLOO_API_KEY"]}

for query, etype in [("Radiohead", "urn:entity:artist"), ("Amelie", "urn:entity:movie")]:
    r = httpx.get(f"{base}/search", params={"query": query, "type": etype}, headers=headers, timeout=20)
    print(query, etype, r.status_code)
    print(r.text[:600], "\n")
