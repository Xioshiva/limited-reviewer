# Limited Reviewer

Turn a Magic: The Gathering set code into a polished **PowerPoint review of its
Limited environment**. Point it at a set, and it pulls card data from
[Scryfall](https://scryfall.com) and performance data from
[17Lands](https://www.17lands.com), then writes a chaptered `.pptx` deck covering
colors, the mana curve, removal, tricks, archetypes, draft signals, and the best
cards — every card shown with its win rate. No API keys required.

```powershell
py -m limited_reviewer FIN     # -> output/FIN-limited-review.pptx
```

## Highlights

- **Archetypes** — the format's main archetypes **detected by play rate** (any
  color count: 3-color archetypes appear, dead 2-color pairs are dropped), with
  17Lands win rates and each archetype's key commons & uncommons ranked by their
  win rate *in that archetype*.
- **Pivot cards** — commons/uncommons that are strong across 2+ archetypes.
- **Removal & tricks** — galleries grouped by color and sorted by win rate;
  board wipes split out; removal over 5 mana excluded.
- **Draft signals** — *traps* (taken early, underperform) and *sleepers* (wheel,
  overperform), from pick order vs win rate.
- **Best cards** — top commons, top uncommons, and the top 20 overall.
- Clickable contents, page numbers, and a per-card win-rate **debug CSV**.

## Requirements

- Python 3.10+
- Install dependencies (`requests`, `pandas`, `matplotlib`, `python-pptx`):

  ```powershell
  py -m pip install -r requirements.txt
  ```

## Usage

From the project root, put `src` on the import path and run with a set code:

```powershell
# PowerShell
$env:PYTHONPATH = "src"
py -m limited_reviewer FIN
```

```bash
# bash
PYTHONPATH=src py -m limited_reviewer FIN
```

The deck is written to `output/<CODE>-limited-review.pptx`. Set codes are
Scryfall codes — `FIN`, `MH3`, `BLB`, `DSK`, `OTJ`, `SOS`, ...

| Option | Description |
|--------|-------------|
| `-o, --output PATH` | Output file (default `output/<CODE>-limited-review.pptx`) |
| `--format FMT` | 17Lands format for win rates (default `PremierDraft`) |
| `--max-age-days N` | Refetch 17Lands data older than N days (default `1`) |
| `--no-cache` | Ignore all caches and refetch everything |

> The first run for a set downloads card images and 17Lands data (a few MB);
> later runs are fast from `cache/`. 17Lands win rates keep moving, so cached
> 17Lands responses older than a day are refetched automatically (tune with
> `--max-age-days`); Scryfall card data is cached without expiry.

## What's in the deck

The deck is organised into chapters. The **Contents** page links to each chapter,
and every slide is numbered.

| Chapter | Slides |
|---------|--------|
| **The Set at a Glance** | overview, color balance, mana curve, play/draw win rate |
| **Archetypes** | main archetypes by play rate (incl. 3-color), win rates, gold-card density, one slide per archetype (key commons & uncommons by in-archetype win rate), pivot cards |
| **Removal & Interaction** | removal by color (≤5 mana), sweepers, combat tricks by color, other functions |
| **Draft Signals** | overrated *traps*, underrated *sleepers* |
| **Best Cards** | top 5 commons, top 5 uncommons, top 20 overall |
| **Methodology** | how cards were classified, and caveats |

Every card caption shows **GIH win rate + pick position** (e.g. `64.5% · P1.4`).

## How it works

- **Card pool** — the set's draft-booster cards: `set:<code> is:booster`, falling
  back to all cards when a set has no booster flag. Basic lands, tokens, Starter
  Deck exclusives, and digital (Alchemy/rebalanced) cards are dropped.
- **Function buckets** (removal, tricks, ramp, …) come from Scryfall's community
  **Tagger** oracle tags, cross-referenced to the pool, with light Limited-aware
  heuristics (e.g. removal split by spell speed and conditionality).
- **Ranking** uses **17Lands GIH win rate** (games-in-hand), the standard public
  Limited metric, with a 200-game reliability floor. Archetype slides use the
  card's win rate *within that color pair* (17Lands `colors=` filter); the
  archetype average line is games-weighted.

Tags describe a card's *general* function, not its quality in one format — so the
deck always shows the card image + win rate next to each bucket, for you to
verify and adjust.

## Debugging win-rate gaps

Each run also writes `output/<CODE>-debug.csv` — one row per card with a `status`
column explaining any missing win rate:

| status | meaning |
|--------|---------|
| `ok` | reliable win rate |
| `low_sample` | has a win rate, below the 200-game floor |
| `row_but_null_wr` | 17Lands row exists but too few games for a rate |
| `no_17lands_row` | name not found in 17Lands draft data |

## Project layout

```
src/limited_reviewer/
  scryfall.py        Scryfall client (paging, rate-limit, cache, card images)
  seventeenlands.py  17Lands win rates: cards, archetypes, play/draw
  categories.py      function-tag definitions + Limited heuristics
  analyze.py         stats engine, win-rate joins, grouping/sorting
  charts.py          matplotlib charts -> PNG
  deck.py            python-pptx slide builder
  debug.py           per-card win-rate diagnostics -> CSV
  cli.py             command-line entrypoint
cache/               cached Scryfall + 17Lands responses and card images
output/              generated decks, charts, and debug CSVs
```

`cache/` and `output/` are regenerated on demand and are git-ignored.

## Data sources

- [Scryfall](https://scryfall.com) — card data, Oracle text, images, function tags
- [17Lands](https://www.17lands.com/public_datasets) — win rates and pick order

This is an unofficial fan project. Magic: The Gathering is © Wizards of the Coast.
