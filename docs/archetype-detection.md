# Spec: dynamic archetype detection (by play rate)

Status: **implemented** (`seventeenlands.select_archetypes`, wired through
`analyze`/`cli`/`charts`/`deck`). On SOS it now surfaces Temur/Sultai/Jeskai and
drops the dead 2-color pairs, as predicted below. Kept as the design record.

## Problem

Archetypes are currently **hardcoded to the 10 two-color pairs** (see
`analyze._archetypes`, which iterates `combinations("WUBRG", 2)`), and the deck
shows all 10 equally. Real formats don't work that way:

- The main archetype is sometimes **3-color (or more)**.
- Some 2-color pairs are essentially **unplayed** and shouldn't get a slide.

### Evidence (SOS, Premier Draft, all-time)

Play rate = share of 2-colour-plus games. Total ≈ 1,146,789 games.

| Archetype | Colors | Play rate | Win rate |
|-----------|--------|-----------|----------|
| Boros (RW)   | 2 | 20.2% | 56.9% |
| Izzet (UR)   | 2 | 18.7% | 54.0% |
| Orzhov (WB)  | 2 | 17.4% | 57.3% |
| Golgari (BG) | 2 | 12.7% | 54.1% |
| Simic (UG)   | 2 |  9.5% | 54.5% |
| **Temur (URG)**  | **3** | **8.2%** | 52.8% |
| **Sultai (UBG)** | **3** | **3.9%** | 52.5% |
| **Jeskai (WUR)** | **3** | **3.4%** | 53.9% |
| Mardu (WBR)  | 3 | 1.7% | 50.1% |
| … | | | |
| Gruul (RG)   | 2 | 0.1% | 53.2% |
| Dimir (UB)   | 2 | 0.1% | 48.9% |
| Bant (WUG)   | 3 | 0.1% | 50.6% |

So the *real* SOS archetypes are 5 two-color pairs **+ Temur/Sultai/Jeskai**,
while RG/UB/etc. are dead. Today we show RG and UB but **omit Temur entirely**.

## Goal

Detect the format's main archetypes **dynamically from play rate**, regardless of
color count (2c/3c/4c/5c): include high-playrate combos, drop very-low-playrate
ones. Everything downstream (per-archetype slides, in-archetype win rates, pivot
cards) should follow the detected set.

## Data we already have

- `seventeenlands.color_ratings()` already returns **non-summary rows for every
  color combo** (mono → 5c) with `short_name`, `color_name`, `wins`, `games`. We
  currently keep only the 2-color rows.
- Per-card win rates work for **3-color** filters: `card_ratings?...&colors=URG`
  returns GIH WR per card (verified — 183 SOS cards with a rate).

## Algorithm

1. Fetch all non-summary `color_ratings` rows.
2. `total = sum(games)`; `play_rate[combo] = games / total`.
3. `main = [row for row if play_rate >= MIN_PLAYRATE]`, sorted by play rate desc,
   capped at `MAX_ARCHETYPES`. (Optionally exclude mono unless its play rate is
   high.) Guarantee a sensible floor (e.g. keep at least the top 5) so a weird
   set never yields zero archetypes.
4. Use `main` everywhere the 10 hardcoded pairs are used now.

### Suggested thresholds (tune later, expose as CLI flags)

- `MIN_ARCHETYPE_PLAYRATE = 0.03`  (3%)
- `MAX_ARCHETYPES = 10`
- SOS @3% → Boros, Izzet, Orzhov, Golgari, Simic, **Temur, Sultai, Jeskai** (8).
  Dead 2c pairs dropped; the real 3c archetypes included. ✅

## Code touchpoints

- **`seventeenlands.py`** — add `main_archetypes(set, fmt)` (or compute in
  analyze) returning the selected combos with games/win_rate/play_rate. Keep
  using each row's own **`short_name`** as the `colors=` value when fetching
  per-archetype card ratings (it's 17Lands' own code — avoids color-order
  guessing; the 2c reversed-order fallback can be dropped/generalized).
- **`analyze.py`**
  - Replace `_archetypes(cards)` with one driven by the detected combos. Each
    archetype dict: `{ "pair": short_name, "colors": frozenset, "name":
    color_name, "win_rate", "games", "play_rate", "count": signpost_count }`.
  - Decide **signpost ("gold") count** for 3c+: e.g. cards whose
    `color_identity == combo` (exactly those colors), or `⊆ combo and >= 2
    colors`. Pick one and label it.
  - `arch_rating`, `archetype_cards`, `pivot_cards` already key by the pair
    string / `color_identity ⊆ colors`, so they generalize to any color count —
    just make sure the `pair` keys match the detected `short_name`s.
- **`cli.py`** — fetch `color_ratings` first, **detect** the archetype list, then
  fetch per-archetype `ratings(colors=short_name)` only for the detected set
  (instead of the fixed `combinations("WUBRG", 2)`).
- **`charts.py`** — `archetype_winrate_chart`: x labels become variable-length
  codes (e.g. `RW`, `URG`); games-weighted average over the detected set.
- **`deck.py`** — archetype slides already use `color_name` for titles and
  `archetype_cards` for the card rows, so they work; just confirm the
  gold-density slide label/semantics still make sense with mixed color counts.

## Open questions / decisions

- Mono-color archetypes: include only if play rate is high (rare). Default: skip.
- Signpost definition for 3c+ (see above) — affects the gold-density chart.
- Color-order normalization: prefer 17Lands `short_name` verbatim for the
  `colors=` param; only normalize (sorted WUBRG) for display/dedupe keys.
- Sanity-check a clean 2-color set (e.g. FIN) still surfaces its real pairs and
  isn't accidentally trimmed.

## Test plan

- **SOS**: expect ~8 archetypes including Temur/Sultai/Jeskai; RG/UB/Bant dropped.
- **FIN**: expect the balanced two-color pairs retained (regression guard).
- Confirm every detected archetype's `colors=` fetch populates (per-card WR > 0).
