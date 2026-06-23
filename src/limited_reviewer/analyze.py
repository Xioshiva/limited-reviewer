"""Turn raw Scryfall data into Limited-review statistics."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations

from .categories import (
    CATEGORIES,
    WUBRG,
    card_colors,
    color_identity,
    is_instant_speed,
    oracle_text,
    removal_is_unconditional,
    removal_speed,
    type_line,
)
from .scryfall import ScryfallClient
from .seventeenlands import ArchetypeRating, CardRating, PlayDrawStat

RARITY_ORDER = ["common", "uncommon", "rare", "mythic"]
NON_DRAFT_LAYOUTS = {"token", "double_faced_token", "emblem", "art_series", "scheme", "planar"}

# Removal costing more than this is too slow to count as Limited interaction.
REMOVAL_MAX_CMC = 5

# Combat-relevant keyword abilities (from each card's Scryfall `keywords` field).
EVASION_KEYWORDS = ["Flying", "Menace", "Trample", "Reach", "Deathtouch", "Vigilance"]

# Single-bucket color grouping (each card in exactly one group).
GROUP_ORDER = ["W", "U", "B", "R", "G", "M", "C"]
GROUP_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red",
               "G": "Green", "M": "Multicolor", "C": "Colorless"}


def color_group(card: dict) -> str:
    cols = card_colors(card)
    if cols == ["C"]:
        return "C"
    if len(cols) >= 2:
        return "M"
    return cols[0]


def name_candidates(card: dict) -> list[str]:
    """Names to try when matching a card to external (17Lands) data."""
    names = [card["name"]]
    if " // " in card["name"]:
        names.append(card["name"].split(" // ")[0])
    for face in card.get("card_faces", []):
        if face.get("name"):
            names.append(face["name"])
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def is_draftable(card: dict) -> bool:
    """Heuristic for 'card a drafter can actually open in this set'."""
    if card.get("digital"):
        return False  # Alchemy / Arena-rebalanced digital-only cards.
    if card.get("layout") in NON_DRAFT_LAYOUTS:
        return False
    if "starterdeck" in (card.get("promo_types") or []):
        return False  # Starter Deck exclusives aren't in draft boosters.
    tl = type_line(card).lower()
    if "basic land" in tl:
        return False
    return True


@dataclass
class CategoryStat:
    key: str
    label: str
    blurb: str
    cards: list[dict] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.cards)

    @property
    def by_color(self) -> dict[str, int]:
        counts = Counter()
        for c in self.cards:
            for col in card_colors(c):
                counts[col] += 1
        return {col: counts.get(col, 0) for col in WUBRG + ["C"]}

    def names(self) -> list[str]:
        return sorted(c["name"] for c in self.cards)


@dataclass
class Analysis:
    code: str
    set_name: str
    released_at: str
    icon_svg_uri: str
    cards: list[dict]
    categories: list[CategoryStat]
    color_counts: dict[str, int]
    multicolor_count: int
    rarity_counts: dict[str, int]
    type_counts: dict[str, int]
    curve: dict[int, int]
    creature_count: int
    archetypes: list[dict]
    removal_detail: dict
    ratings: dict[str, CardRating] = field(default_factory=dict)
    color_ratings: list[ArchetypeRating] = field(default_factory=list)
    play_draw: PlayDrawStat | None = None
    # pair code ("WU") -> {card name -> rating within that archetype}
    archetype_card_ratings: dict[str, dict[str, CardRating]] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.cards)

    def category(self, key: str) -> CategoryStat:
        return next(c for c in self.categories if c.key == key)

    def rating(self, card: dict) -> CardRating | None:
        for name in name_candidates(card):
            r = self.ratings.get(name)
            if r is not None:
                return r
        return None

    def winrate(self, card: dict) -> float | None:
        r = self.rating(card)
        return r.gih_wr if r else None

    def _wr_sort_key(self, card):
        """Sort key: reliable WR first (desc), then low-sample, then no data."""
        r = self.rating(card)
        if r and r.reliable:
            return (0, -r.gih_wr)
        if r and r.gih_wr is not None:
            return (1, -r.gih_wr)
        return (2, 0.0)

    def grouped_by_color(self, cards: list[dict]) -> list[tuple[str, list[dict]]]:
        """Group cards into color buckets, each sorted by win rate (desc)."""
        buckets: dict[str, list[dict]] = {g: [] for g in GROUP_ORDER}
        for c in cards:
            buckets[color_group(c)].append(c)
        result = []
        for g in GROUP_ORDER:
            if buckets[g]:
                result.append((g, sorted(buckets[g], key=self._wr_sort_key)))
        return result

    def sorted_by_winrate(self, cards: list[dict]) -> list[dict]:
        return sorted(cards, key=self._wr_sort_key)

    def arch_rating(self, pair: str, card: dict) -> CardRating | None:
        """A card's rating *within* a given color-pair archetype."""
        table = self.archetype_card_ratings.get(pair)
        if not table:
            return None
        for name in name_candidates(card):
            r = table.get(name)
            if r is not None:
                return r
        return None

    def arch_winrate(self, pair: str, card: dict) -> float | None:
        r = self.arch_rating(pair, card)
        return r.gih_wr if r else None

    def _arch_sort_key(self, pair: str, card):
        r = self.arch_rating(pair, card) or self.rating(card)  # fall back to overall
        if r and r.reliable:
            return (0, -r.gih_wr)
        if r and r.gih_wr is not None:
            return (1, -r.gih_wr)
        return (2, 0.0)

    def archetype_meta(self, pair: str) -> dict | None:
        return next((ar for ar in self.archetypes if ar["pair"] == pair), None)

    def archetype_cards(self, pair: str, rarity: str, n: int = 6) -> list[dict]:
        """Best commons/uncommons of a color pair, ranked by *in-archetype* WR.

        A card belongs to a pair if its color identity is a non-empty subset of
        the pair (mono-color of either color, or the two-color gold cards).
        """
        colors = set(pair)
        pool = [c for c in self.cards
                if c.get("rarity") == rarity
                and color_identity(c)
                and color_identity(c) <= colors]
        pool.sort(key=lambda c: self._arch_sort_key(pair, c))
        return pool[:n]

    def _archetype_good_names(self, k: int = 15) -> dict[str, set[str]]:
        """Per pair, the names of the top-k commons/uncommons by in-archetype WR
        (color identity a subset of the pair -- colorless cards qualify too)."""
        good: dict[str, set[str]] = {}
        for ar in self.archetypes:
            pair = ar["pair"]
            colors = set(pair)
            pool = [c for c in self.cards
                    if c.get("rarity") in ("common", "uncommon")
                    and color_identity(c) <= colors
                    and (r := self.arch_rating(pair, c)) and r.reliable]
            pool.sort(key=lambda c: self.arch_rating(pair, c).gih_wr, reverse=True)
            good[pair] = {c["name"] for c in pool[:k]}
        return good

    def pivot_cards(self, rarity: str, k: int = 15, min_archetypes: int = 2,
                    n: int = 12) -> list[tuple[dict, list[str]]]:
        """Cards of a rarity that rank among the best in >= min_archetypes pairs.

        Returns (card, pairs-it's-good-in) sorted by breadth then best WR.
        """
        good = self._archetype_good_names(k)
        member: dict[str, list[str]] = {}
        for pair, names in good.items():
            for nm in names:
                member.setdefault(nm, []).append(pair)

        def best_wr(card, pairs):
            ws = [r.gih_wr for p in pairs if (r := self.arch_rating(p, card))]
            return max(ws) if ws else 0.0

        out = []
        for c in self.cards:
            if c.get("rarity") != rarity:
                continue
            pairs = member.get(c["name"], [])
            if len(pairs) >= min_archetypes:
                pairs = sorted(pairs, key=lambda p: -(self.arch_winrate(p, c) or 0))
                out.append((c, pairs))
        out.sort(key=lambda t: (len(t[1]), best_wr(t[0], t[1])), reverse=True)
        return out[:n]

    def keyword_color_matrix(self, keywords: list[str]) -> dict[str, dict[str, int]]:
        """For each keyword, count creatures of each color that have it."""
        mat = {k: {col: 0 for col in WUBRG} for k in keywords}
        for c in self.cards:
            kws = c.get("keywords") or []
            for k in keywords:
                if k in kws:
                    for col in card_colors(c):
                        if col in mat[k]:
                            mat[k][col] += 1
        return mat

    def archetype_winrate(self, pair: str) -> ArchetypeRating | None:
        want = frozenset(pair)
        for ar in self.color_ratings:
            if not ar.is_summary and ar.colors == want:
                return ar
        return None

    def traps_and_sleepers(self, n: int = 8) -> tuple[list[dict], list[dict]]:
        """Cards whose pick order disagrees with performance.

        Ranks reliable cards by pick priority (ALSA: low = taken early) and by
        win rate, then surfaces the biggest mismatches:
          - traps    : taken much earlier than they perform (overrated)
          - sleepers : perform much better than they're picked (underrated)
        """
        pool = [c for c in self.cards
                if (r := self.rating(c)) and r.reliable and r.alsa is not None]
        if len(pool) < 4:
            return [], []
        by_alsa = sorted(pool, key=lambda c: self.rating(c).alsa)        # earliest first
        pick_rank = {c["name"]: i for i, c in enumerate(by_alsa)}
        by_wr = sorted(pool, key=lambda c: self.rating(c).gih_wr, reverse=True)
        perf_rank = {c["name"]: i for i, c in enumerate(by_wr)}
        # disagreement > 0 => picked higher than it performs (overrated)
        disagree = {c["name"]: perf_rank[c["name"]] - pick_rank[c["name"]] for c in pool}
        traps = sorted(pool, key=lambda c: disagree[c["name"]], reverse=True)[:n]
        sleepers = sorted(pool, key=lambda c: disagree[c["name"]])[:n]
        return traps, sleepers

    def top_by_rarity(self, rarity: str, n: int = 5) -> list[dict]:
        """Best cards of a single rarity by win rate."""
        pool = [c for c in self.cards
                if c.get("rarity") == rarity and (r := self.rating(c)) and r.reliable]
        pool.sort(key=lambda c: self.rating(c).gih_wr, reverse=True)
        return pool[:n]

    def top_by_winrate(self, n: int = 12, max_rarity: str | None = None) -> list[dict]:
        pool = self.cards
        if max_rarity:
            allowed = set(RARITY_ORDER[: RARITY_ORDER.index(max_rarity) + 1])
            pool = [c for c in pool if c.get("rarity") in allowed]
        rated = [c for c in pool if (r := self.rating(c)) and r.reliable]
        rated.sort(key=lambda c: self.rating(c).gih_wr, reverse=True)
        return rated[:n]


def _color_counts(cards: list[dict]) -> tuple[dict[str, int], int]:
    counts = {col: 0 for col in WUBRG + ["C"]}
    multicolor = 0
    for c in cards:
        cols = card_colors(c)
        if len(cols) >= 2:
            multicolor += 1
        for col in cols:
            counts[col] += 1
    return counts, multicolor


def _rarity_counts(cards: list[dict]) -> dict[str, int]:
    counts = Counter(c.get("rarity", "common") for c in cards)
    return {r: counts.get(r, 0) for r in RARITY_ORDER}


def _type_counts(cards: list[dict]) -> dict[str, int]:
    buckets = ["Creature", "Instant", "Sorcery", "Enchantment", "Artifact", "Planeswalker", "Land", "Battle"]
    counts = Counter()
    for c in cards:
        tl = type_line(c)
        matched = False
        for b in buckets:
            if b in tl:
                counts[b] += 1
                matched = True
                break
        if not matched:
            counts["Other"] += 1
    order = buckets + ["Other"]
    return {b: counts[b] for b in order if counts[b]}


def _curve(cards: list[dict]) -> dict[int, int]:
    """Mana-value distribution of nonland spells (7+ bucketed together)."""
    counts = Counter()
    for c in cards:
        if "Land" in type_line(c):
            continue
        cmc = int(c.get("cmc", 0) or 0)
        counts[min(cmc, 7)] += 1
    return {i: counts.get(i, 0) for i in range(0, 8)}


def _archetypes(cards: list[dict]) -> list[dict]:
    """For each of the 10 two-color pairs, count exact gold cards (signposts)."""
    result = []
    for a, b in combinations(WUBRG, 2):
        pair = {a, b}
        gold = [c for c in cards if set(card_colors(c)) == pair]
        result.append({
            "pair": a + b,
            "count": len(gold),
            "cards": sorted(c["name"] for c in gold),
        })
    return result


def _removal_detail(removal_cards: list[dict]) -> dict:
    speed = Counter(removal_speed(c) for c in removal_cards)
    by_color = Counter()
    for c in removal_cards:
        for col in card_colors(c):
            by_color[col] += 1
    unconditional = sum(1 for c in removal_cards if removal_is_unconditional(c))
    instant = sum(1 for c in removal_cards if is_instant_speed(c))
    return {
        "speed": {k: speed.get(k, 0) for k in ("instant", "sorcery", "permanent")},
        "by_color": {col: by_color.get(col, 0) for col in WUBRG + ["C"]},
        "unconditional": unconditional,
        "conditional": len(removal_cards) - unconditional,
        "instant_speed": instant,
    }


def _archetypes_from_meta(cards: list[dict], meta: list[ArchetypeRating],
                          color_ratings: list[ArchetypeRating]) -> list[dict]:
    """Build archetype dicts from a detected (play-rate-selected) archetype list."""
    total = sum(ar.games for ar in color_ratings
                if not ar.is_summary and len(ar.colors) >= 2) or 1
    out = []
    for ar in meta:
        cset = set(ar.colors)
        gold = [c for c in cards if set(card_colors(c)) == cset]  # exact-color signposts
        out.append({
            "pair": ar.short_name,
            "colors": ar.colors,
            "name": ar.color_name,
            "win_rate": ar.win_rate,
            "games": ar.games,
            "play_rate": ar.games / total,
            "count": len(gold),
            "cards": sorted(c["name"] for c in gold),
        })
    return out


def analyze_set(client: ScryfallClient, code: str,
                ratings: dict[str, CardRating] | None = None,
                color_ratings: list[ArchetypeRating] | None = None,
                play_draw: PlayDrawStat | None = None,
                archetype_card_ratings: dict[str, dict[str, CardRating]] | None = None,
                archetypes_meta: list[ArchetypeRating] | None = None
                ) -> Analysis:
    set_meta = client.get_set(code)
    raw = client.cards_in_set(code)
    cards = [c for c in raw if is_draftable(c)]
    by_name = {c["name"]: c for c in cards}

    cat_stats: list[CategoryStat] = []
    for cat in CATEGORIES:
        names = client.names_matching(code, cat.otag)
        members = [by_name[n] for n in names if n in by_name]
        if cat.key == "removal":
            # Spells/abilities over 5 mana are too slow to count as removal.
            members = [c for c in members if (c.get("cmc") or 0) <= REMOVAL_MAX_CMC]
        cat_stats.append(CategoryStat(cat.key, cat.label, cat.blurb, members))

    color_counts, multicolor = _color_counts(cards)
    removal_cards = next(cs for cs in cat_stats if cs.key == "removal").cards

    if archetypes_meta:
        # Dynamic: archetypes detected by play rate (any color count).
        archetypes = _archetypes_from_meta(cards, archetypes_meta, color_ratings or [])
    else:
        # Fallback (no 17Lands data): the fixed 10 two-color pairs.
        archetypes = _archetypes(cards)
        arch_by_colors = {ar.colors: ar for ar in (color_ratings or []) if not ar.is_summary}
        for arch in archetypes:
            ar = arch_by_colors.get(frozenset(arch["pair"]))
            arch["win_rate"] = ar.win_rate if ar else None
            arch["games"] = ar.games if ar else 0
            arch["name"] = ar.color_name if ar else arch["pair"]
            arch["play_rate"] = None

    return Analysis(
        code=code.upper(),
        set_name=set_meta.get("name", code.upper()),
        released_at=set_meta.get("released_at", ""),
        icon_svg_uri=set_meta.get("icon_svg_uri", ""),
        cards=cards,
        categories=cat_stats,
        color_counts=color_counts,
        multicolor_count=multicolor,
        rarity_counts=_rarity_counts(cards),
        type_counts=_type_counts(cards),
        curve=_curve(cards),
        creature_count=sum(1 for c in cards if "Creature" in type_line(c)),
        archetypes=archetypes,
        removal_detail=_removal_detail(removal_cards),
        ratings=ratings or {},
        color_ratings=color_ratings or [],
        play_draw=play_draw,
        archetype_card_ratings=archetype_card_ratings or {},
    )
