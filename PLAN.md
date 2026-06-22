# Limited Reviewer — Project Plan

Automatic **MTG set review for Limited**. You give it a set code (e.g. `FIN`),
it pulls data from Scryfall and generates a **PowerPoint presentation** with the
key stats for evaluating that set's draft/sealed environment.

## Goal / output
A `.pptx` deck answering:
- How many cards per **color**? How much **multicolor**?
- Breakdown by **rarity** and **card type**, plus the **mana curve**.
- How much **removal**, and how good is it (speed: instant vs sorcery,
  conditional vs unconditional, by color)?
- How many **combat tricks**, **card advantage**, **ramp/fixing**, **burn**,
  **bounce**, **counterspells**, **lifegain**, **evasion**, **tutors**?
- **Archetype** snapshot: the 10 two-color pairs and their signpost/gold-card
  density.

## Data + classification
- **Card data:** Scryfall API (free, no key). Requires `User-Agent` + `Accept`
  headers; throttled ~120ms/request; responses + card images cached in `cache/`.
- **Win rates:** 17Lands public card-ratings data — GIH WR (games-in-hand win
  rate, `ever_drawn_win_rate`) with sample size, cached per set/format.
- **Classification:** Scryfall community "Tagger" oracle tags (`otag:removal`,
  `otag:combat-trick`, …) as the base signal, **plus** our own transparent
  Limited-aware heuristics (e.g. removal split by spell speed / conditionality).
  Verified populated tags for a set: removal, creature-removal, combat-trick,
  ramp, burn, bounce, counterspell, lifegain, evasion, tutor.
- The deck shows the actual **card images + win rate** in each bucket so
  classifications can be eyeballed and corrected (tags aren't perfect for Limited).
- Card advantage intentionally **excluded** (per request).

## Tech
- Python 3.12 (`py` launcher). Deps: `requests`, `pandas`, `matplotlib`,
  `python-pptx` (installed).
- Run: `py -m limited_reviewer FIN` → `output/FIN-limited-review.pptx`

## Architecture (`src/limited_reviewer/`)
| File | Role | Status |
|------|------|--------|
| `scryfall.py`        | API client: headers, paging, rate-limit, cache, card images | ✅ done |
| `seventeenlands.py`  | 17Lands GIH win-rate fetch + cache                  | ✅ done |
| `categories.py`      | Category defs (tags) + Limited heuristics           | ✅ done |
| `analyze.py`         | Stats + win-rate join + color grouping/sorting      | ✅ done |
| `charts.py`          | matplotlib charts → PNGs (WUBRG colored)            | ✅ done |
| `deck.py`            | python-pptx slide builder (+ image galleries)       | ✅ done |
| `cli.py`             | `py -m limited_reviewer CODE` entrypoint            | ✅ done |

## Deck outline (chapters; ~44 slides for FIN)
- **Title** + **Contents** — agenda with **clickable links** to each chapter.
  Every slide (except the title) has a **page number**.
- **Chapter 1 — The Set at a Glance:** overview, color balance, mana curve,
  play/draw win rate.
- **Chapter 2 — Archetypes:** archetype win rates (17Lands), gold-card density,
  one slide per color pair with key commons & uncommons **ranked by the card's
  win rate *within that archetype*** (17Lands `colors=` filter), then **pivot
  cards** — commons/uncommons strong in 2+ archetypes.
- **Chapter 3 — Removal & Interaction:** removal galleries (one per color, ≤5
  mana, by win rate), sweepers/wraths, combat tricks (one per color), other
  functions (burn/bounce/counters/lifegain/evasion/tutors/ramp).
- **Chapter 4 — Draft Signals:** overrated traps, underrated sleepers.
- **Chapter 5 — Best Cards:** top 5 commons + top 5 uncommons, then Top 20 overall.
- **Methodology** — how cards were classified (and caveats).

Every card caption shows **GIH win rate + pick position** (e.g. `64.5% · P1.4`);
on archetype slides the win rate is the card's rate **in that archetype**.

## Card pool & data notes
- Pool = `set:CODE is:booster`, minus digital (Alchemy/rebalanced) cards, basics,
  and token layouts → the cards a drafter actually opens (matches 17Lands draft data).
- 17Lands needs an explicit wide **date range** or it returns mostly-null win rates.
- 17Lands color_ratings returns base + "+ Splash" rows per pair; we use
  `combine_splash=true` so each pair appears once.
- A diagnostic `output/<CODE>-debug.csv` lists every card's match status
  (ok / low_sample / row_but_null_wr / no_17lands_row) for triaging gaps.

## Status
- [x] Full pipeline verified end-to-end on FIN (37-slide deck)
- [x] 17Lands card + archetype + play/draw + pick (ALSA/ATA) data joined
- [x] Archetypes lead the deck; tricks split by color like removal
- [x] Play/draw slide; traps & sleepers (pick order vs win rate); Top 20 finale
- [x] Separate sweepers category; removal (≤5 mana); debug CSV with ALSA/ATA
- [x] Booster-only pool; digital cards excluded

## Possible next steps (tag ideas)
- **Keyword-ability slide** (free, from card data): Flying/Deathtouch/Lifelink/…
  + set mechanics (Job select, Flashback, Surveil, Crew, Cycling).
- **Theme tags** with data in FIN: self-mill (21), mill (27), landfall (15),
  sacrifice-outlet (14), cantrip (5) — reveal the set's deck themes.
- Name archetype themes (WU Tempo, BR Sacrifice…) alongside color pairs.
- CSV/JSON export of the full raw stats.

## Notes / open questions
- "Draftable" filter currently drops basic lands + token/emblem layouts. May
  refine to booster-only if special-slot cards skew counts.
- Archetype names are editorial; we report by color pair (WU, UB, …) + gold-card
  counts rather than inventing theme names. Can add known names later.
