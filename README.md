# Limited Reviewer

Automatically generate a **PowerPoint review of an MTG set's Limited environment**.
Give it a set code; it pulls card data from [Scryfall](https://scryfall.com),
analyzes the draft/sealed environment, and writes a `.pptx` deck with the stats
that matter for Limited: color balance, mana curve, removal (and how good it is),
combat tricks, card advantage, ramp, archetypes, and more.

## Install

```sh
py -m pip install -r requirements.txt
```

(Requires Python 3.10+. Uses `requests`, `pandas`, `matplotlib`, `python-pptx`.)

## Usage

```sh
# from the project root
$env:PYTHONPATH = "src"           # PowerShell
py -m limited_reviewer FIN
```

```sh
export PYTHONPATH=src              # bash
py -m limited_reviewer MH3 -o my-review.pptx
```

Output goes to `output/<CODE>-limited-review.pptx` by default. Chart PNGs are
written to `output/charts/<code>/`.

Options:
- `-o, --output PATH` — choose the output file.
- `--format FMT` — 17Lands format for win rates (default `PremierDraft`).
- `--no-cache` — bypass the on-disk caches (`cache/`).

Set codes are Scryfall codes: `FIN`, `MH3`, `OTJ`, `BLB`, `DSK`, `LCI`, ...

The first run for a set downloads card images (a few MB), so it takes a little
longer; later runs are fast from cache.

## What's in the deck

The deck is organised into chapters. The **Contents** page has **clickable links**
to each chapter, and every slide has a **page number**.

- **Title + Contents**
- **Chapter 1 — The Set at a Glance:** overview, color balance, mana curve,
  play/draw win rate.
- **Chapter 2 — Archetypes:** 17Lands archetype win rates, gold-card density, one
  slide per color pair with key commons & uncommons **ranked by win rate within
  that archetype**, then **pivot cards** (commons/uncommons strong in 2+ archetypes).
- **Chapter 3 — Removal & Interaction:** removal galleries (one per color, ≤5 mana,
  by win rate), sweepers/wraths, combat tricks (one per color), other functions.
- **Chapter 4 — Draft Signals:** overrated *traps*, underrated *sleepers*.
- **Chapter 5 — Best Cards:** top 5 commons + top 5 uncommons, then Top 20 overall.
- **Methodology & caveats**

Every card caption shows **GIH win rate + pick position** (e.g. `64.5% · P1.4`);
on archetype slides the win rate is the card's rate **in that archetype**.

Removal over 5 mana is excluded (too slow to count as Limited interaction);
board wipes are split into their own category. The pool is draft-booster cards
only — Starter Deck, promo, and digital (Alchemy/rebalanced) cards are dropped.

## Debugging win-rate gaps

Every run also writes `output/<CODE>-debug.csv`, one row per card with its match
status so you can see *why* a card lacks a win rate:
`ok` · `low_sample` · `row_but_null_wr` (too few games) · `no_17lands_row`
(name not found in 17Lands draft data). For FIN this is 290/294 matched, with
the handful of misses being cards 17Lands genuinely has no draft data for.

## How classification & ranking work

Function buckets come from Scryfall's community **"Tagger" oracle tags**
(`otag:removal`, `otag:combat-trick`, …), queried per set and cross-referenced to
the set's draftable cards, plus transparent Limited-aware heuristics (e.g. removal
split by spell speed and a conditional/unconditional keyword check).

Card **quality / ranking** uses **17Lands** GIH win rate (games-in-hand win rate),
the standard public Limited-performance metric, with a 200-game minimum before a
win rate is treated as reliable. Removal and tricks are sorted by it.

Tags describe a card's *general* function, not its quality in one specific
Limited format — so the deck shows the actual **card image + win rate** in each
bucket so you can verify and adjust. Card advantage is intentionally excluded.
See `PLAN.md` for architecture and roadmap.

Data sources: [Scryfall](https://scryfall.com) (cards/images) and
[17Lands public datasets](https://www.17lands.com/public_datasets) (win rates).

## Project layout

```
src/limited_reviewer/
  scryfall.py        Scryfall API client (paging, rate-limit, cache, card images)
  seventeenlands.py  17Lands GIH win-rate fetch + cache
  categories.py      category definitions + Limited heuristics
  analyze.py         stats engine + win-rate join + color grouping/sorting
  charts.py          matplotlib charts -> PNG
  deck.py            python-pptx slide builder (+ image galleries)
  debug.py           per-card win-rate match diagnostics -> CSV
  cli.py             command-line entrypoint
cache/               cached Scryfall responses, card images, 17Lands data
output/              generated decks + charts
```
