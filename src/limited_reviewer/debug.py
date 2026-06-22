"""Diagnostic CSV export.

Writes one row per draftable card showing exactly how (and whether) it matched
17Lands win-rate data, so 'no data' cards can be triaged into:
  - no_17lands_row : name never matched any 17Lands row (likely a name mismatch)
  - row_but_null_wr: a row exists but its GIH win rate is null (too few games)
  - low_sample     : has a win rate but below the reliability threshold
  - ok             : reliable win rate
"""

from __future__ import annotations

import csv
from pathlib import Path

from .analyze import REMOVAL_MAX_CMC, Analysis, color_group, name_candidates
from .categories import card_colors, color_identity, type_line

FIELDNAMES = [
    "name", "rarity", "cmc", "colors", "color_identity", "group", "type",
    "in_removal", "removal_excluded_over_cmc", "is_sweeper", "status",
    "matched_17lands_name", "gih_wr", "games", "alsa", "ata", "names_tried",
]


def _status(a: Analysis, card: dict) -> tuple[str, str]:
    """Return (status, matched_17lands_name)."""
    matched = ""
    for n in name_candidates(card):
        if n in a.ratings:
            matched = n
            break
    if not matched:
        return "no_17lands_row", ""
    r = a.ratings[matched]
    if r.gih_wr is None:
        return "row_but_null_wr", matched
    if not r.reliable:
        return "low_sample", matched
    return "ok", matched


def write_debug_csv(a: Analysis, path: Path) -> dict[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    removal_names = {c["name"] for c in a.category("removal").cards}
    sweeper_names = {c["name"] for c in a.category("board_wipe").cards}
    summary: dict[str, int] = {}

    rows = []
    for c in a.cards:
        status, matched = _status(a, c)
        summary[status] = summary.get(status, 0) + 1
        r = a.ratings.get(matched) if matched else None
        cmc = c.get("cmc") or 0
        rows.append({
            "name": c["name"],
            "rarity": c.get("rarity", ""),
            "cmc": cmc,
            "colors": "".join(card_colors(c)),
            "color_identity": "".join(sorted(color_identity(c))),
            "group": color_group(c),
            "type": type_line(c),
            "in_removal": c["name"] in removal_names,
            "removal_excluded_over_cmc": (c["name"] not in removal_names and cmc > REMOVAL_MAX_CMC),
            "is_sweeper": c["name"] in sweeper_names,
            "status": status,
            "matched_17lands_name": matched,
            "gih_wr": f"{r.gih_wr:.4f}" if r and r.gih_wr is not None else "",
            "games": r.games if r else "",
            "alsa": f"{r.alsa:.2f}" if r and r.alsa is not None else "",
            "ata": f"{r.ata:.2f}" if r and r.ata is not None else "",
            "names_tried": " | ".join(name_candidates(c)),
        })

    rows.sort(key=lambda x: (x["status"] != "no_17lands_row",
                             x["status"] != "row_but_null_wr", x["name"]))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return summary
