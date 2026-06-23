"""Command-line entrypoint: review a set's Limited environment."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analyze import analyze_set
from .debug import write_debug_csv
from .deck import build_deck
from .scryfall import ScryfallClient, ScryfallError
from .seventeenlands import SeventeenLandsClient, select_archetypes

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="limited_reviewer",
        description="Generate a Limited review presentation for an MTG set.",
    )
    parser.add_argument("set_code", help="Scryfall set code, e.g. FIN, MH3, OTJ")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="Output .pptx path (default: output/<CODE>-limited-review.pptx)")
    parser.add_argument("--format", default="PremierDraft",
                        help="17Lands format for win rates (default: PremierDraft)")
    parser.add_argument("--max-age-days", type=float, default=1.0,
                        help="Refetch 17Lands data older than this many days (default: 1)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Bypass the on-disk caches")
    args = parser.parse_args(argv)

    code = args.set_code.lower()
    out = args.output or (ROOT / "output" / f"{code.upper()}-limited-review.pptx")
    chart_dir = ROOT / "output" / "charts" / code

    client = ScryfallClient(use_cache=not args.no_cache)
    seventeen = SeventeenLandsClient(client.cache_dir, use_cache=not args.no_cache,
                                     ttl_seconds=args.max_age_days * 86400)
    try:
        print(f"Fetching '{code}' from Scryfall ...")
        print(f"Fetching {args.format} win rates from 17Lands ...")
        ratings = seventeen.ratings(code, args.format)
        color_ratings = seventeen.color_ratings(code, args.format)
        play_draw = seventeen.play_draw(code, args.format)
        archetypes = select_archetypes(color_ratings)
        if archetypes:
            print("Main archetypes: "
                  + ", ".join(f"{a.short_name}({a.games * 100 // sum(x.games for x in archetypes)}%)"
                              for a in archetypes))
        print("Fetching per-archetype win rates from 17Lands ...")
        arch_ratings = {a.short_name: seventeen.ratings(code, args.format, colors=a.short_name)
                        for a in archetypes}
        analysis = analyze_set(client, code, ratings, color_ratings, play_draw,
                               arch_ratings, archetypes)
    except ScryfallError as e:
        print(f"Scryfall error: {e}", file=sys.stderr)
        return 1

    with_wr = sum(1 for c in analysis.cards if analysis.winrate(c) is not None)
    print(f"  {analysis.set_name}: {analysis.total} draftable cards "
          f"({with_wr} with a 17Lands win rate)")

    if analysis.total == 0:
        print(f"\nNo draftable booster cards found for '{code}'. It's probably not a "
              f"Limited/draft set (e.g. a Secret Lair, Commander, or other supplemental "
              f"product). Try a draftable set code such as FIN, MH3, BLB, DSK, or OTJ.",
              file=sys.stderr)
        return 2
    print(f"  removal(<=5cmc)={analysis.category('removal').count}, "
          f"sweepers={analysis.category('board_wipe').count}, "
          f"tricks={analysis.category('combat_trick').count}")

    debug_path = out.with_name(f"{code.upper()}-debug.csv")
    summary = write_debug_csv(analysis, debug_path)
    print(f"  debug CSV -> {debug_path}  ({summary})")

    print("Downloading card images + building presentation ...")
    path = build_deck(analysis, out, chart_dir, client)
    print(f"Done -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
