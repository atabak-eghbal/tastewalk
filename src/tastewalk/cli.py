"""Command-line entry point: run the full pipeline and print the itinerary.

Example:
  uv run python -m tastewalk.cli --fav "Radiohead:artist" --fav "Amelie:movie" --city Vancouver
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import time

from .config import load_settings
from .loop import make_clients, run
from .osm import OSMClient
from .schemas import Comparison, Favorite, FavoriteType, UserInput


def _parse_fav(s: str) -> Favorite:
    name, _, kind = s.rpartition(":")
    if not name or kind not in FavoriteType.__members__:
        raise argparse.ArgumentTypeError(
            f"use NAME:TYPE with TYPE in {', '.join(FavoriteType.__members__)}"
        )
    return Favorite(name=name, type=FavoriteType[kind])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--fav", type=_parse_fav, action="append", required=True)
    ap.add_argument("--city", default="Vancouver")
    ap.add_argument("--start", default="10:00")
    ap.add_argument("--stops", type=int, default=None)
    ap.add_argument("--no-baseline", action="store_true")
    ap.add_argument("--offline", action="store_true", help="use cached responses only")
    ap.add_argument("--json", action="store_true", help="print the final Comparison as JSON")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)

    settings = load_settings()
    h, m = map(int, args.start.split(":"))
    user = UserInput(
        city=args.city,
        favorites=args.fav,
        start_time=time(h, m),
        max_stops=args.stops or settings.max_stops,
    )
    qloo, llm = make_clients(settings, offline=args.offline)
    if not settings.has_llm:
        llm = None
        print("(no LLM configured: deterministic picks + template explanations)", file=sys.stderr)

    result: Comparison | None = None
    for ev in run(user, qloo, llm, with_baseline=not args.no_baseline, osm=OSMClient(qloo.cache)):
        print(f"[{ev.step}] {ev.message}", file=sys.stderr)
        if ev.step == "error":
            return 1
        if ev.step == "done":
            result = ev.data
    assert result is not None
    if args.json:
        print(result.model_dump_json(indent=2))
        return 0
    it = result.qloo_itinerary
    print(f"\nTasteWalk - {it.city}, {len(it.stops)} stops, {it.total_km} km on foot\n")
    for s in it.stops:
        walk = f" (walk {s.walk_minutes_from_prev} min)" if s.walk_minutes_from_prev else ""
        print(f"{s.arrive:%H:%M}-{s.leave:%H:%M}  {s.place.name} [{s.place.category}]{walk}")
        if s.why_it_fits:
            print(f"             {s.why_it_fits}")
    if it.check and it.check.issues:
        print("\nRoute check:", "; ".join(it.check.issues))
    if result.baseline_itinerary:
        print("\nLLM-only baseline:")
        for b in result.baseline_itinerary.stops:
            print(f"  {b.time or '--:--'}  {b.name} [{b.category}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
