"""17Lands card-performance data.

Uses the public aggregated card-ratings endpoint (the same data that backs the
public datasets at https://www.17lands.com/public_datasets). The metric we care
about for Limited card quality is GIH WR -- "games in hand win rate"
(``ever_drawn_win_rate``) -- weighted by its sample size (``ever_drawn_game_count``).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests

RATINGS_URL = "https://www.17lands.com/card_ratings/data"
COLOR_RATINGS_URL = "https://www.17lands.com/color_ratings/data"
PLAY_DRAW_URL = "https://www.17lands.com/data/play_draw"
HEADERS = {"User-Agent": "limited-reviewer/0.1", "Accept": "application/json"}

# 17Lands data starts in 2019; a wide window pulls a set's full history. Without
# an explicit range the endpoint uses a narrow recent window and most cards come
# back with a null win rate.
DEFAULT_START = "2019-01-01"

# 17Lands win rates keep moving (especially for new sets), so cached responses
# are refetched once they're older than this. Card data from Scryfall is static
# and cached without expiry.
DEFAULT_TTL_SECONDS = 24 * 3600

# Archetype detection: keep color combos drafted at least this often, regardless
# of color count, capped at MAX (with a MIN floor so we never show too few).
ARCHETYPE_MIN_PLAYRATE = 0.03
ARCHETYPE_MAX = 10
ARCHETYPE_MIN = 5

# Below this many GIH games the win rate is too noisy to rank on.
MIN_RELIABLE_GAMES = 200


@dataclass(frozen=True)
class CardRating:
    name: str
    gih_wr: float | None          # ever_drawn_win_rate (0-1)
    games: int                    # ever_drawn_game_count
    alsa: float | None            # avg last seen at (how late it wheels)
    ata: float | None             # avg taken at (how early it's picked)
    iwd: float | None             # improvement when drawn

    @property
    def reliable(self) -> bool:
        return self.gih_wr is not None and self.games >= MIN_RELIABLE_GAMES


@dataclass(frozen=True)
class PlayDrawStat:
    win_rate_on_play: float       # fraction of games won by the player on the play
    average_game_length: float    # avg turns
    sample_size: int

    @property
    def win_rate_on_draw(self) -> float:
        return 1.0 - self.win_rate_on_play


@dataclass(frozen=True)
class ArchetypeRating:
    color_name: str        # e.g. "Azorius (WU)"
    short_name: str        # e.g. "WU"
    colors: frozenset      # frozenset({"W", "U"})
    wins: int
    games: int
    is_summary: bool

    @property
    def win_rate(self) -> float | None:
        return self.wins / self.games if self.games else None


def _to_float(v) -> float | None:
    try:
        if v in (None, ""):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


class SeventeenLandsClient:
    def __init__(self, cache_dir: Path, use_cache: bool = True,
                 ttl_seconds: float = DEFAULT_TTL_SECONDS):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_cache = use_cache
        self.ttl_seconds = ttl_seconds

    def _fresh(self, path: Path) -> bool:
        """A cache file counts as usable only if present and younger than the TTL."""
        if not self.use_cache or not path.exists():
            return False
        return (time.time() - path.stat().st_mtime) < self.ttl_seconds

    def ratings(self, set_code: str, fmt: str = "PremierDraft",
                start_date: str | None = None, end_date: str | None = None,
                colors: str | None = None) -> dict[str, CardRating]:
        """Return a name -> CardRating map for a set/format.

        With ``colors`` (e.g. "WU") the win rates are computed only within decks
        of those colors -- i.e. the card's performance *in that archetype*.
        Returns an empty dict if 17Lands has no data, so the deck still builds.
        """
        extra = {"format": fmt}
        if colors:
            extra["colors"] = colors
        rows = self._fetch(RATINGS_URL, set_code, start_date, end_date, "cards", extra)
        out: dict[str, CardRating] = {}
        for r in rows:
            name = r.get("name")
            if not name:
                continue
            out[name] = CardRating(
                name=name,
                gih_wr=_to_float(r.get("ever_drawn_win_rate")),
                games=int(r.get("ever_drawn_game_count") or 0),
                alsa=_to_float(r.get("avg_seen")),
                ata=_to_float(r.get("avg_pick")),
                iwd=_to_float(r.get("drawn_improvement_win_rate")),
            )
        return out

    def play_draw(self, set_code: str, fmt: str = "PremierDraft") -> PlayDrawStat | None:
        """On-the-play win rate and game length for a set/format."""
        rows = self._fetch_raw(PLAY_DRAW_URL, f"playdraw_{set_code.upper()}_{fmt}")
        data = rows.get("data", []) if isinstance(rows, dict) else []
        for r in data:
            if r.get("expansion") == set_code.upper() and r.get("event_type") == fmt:
                wr = _to_float(r.get("win_rate_on_play"))
                if wr is None:
                    return None
                return PlayDrawStat(
                    win_rate_on_play=wr,
                    average_game_length=_to_float(r.get("average_game_length")) or 0.0,
                    sample_size=int(r.get("sample_size") or 0),
                )
        return None

    def _fetch_raw(self, url: str, cache_name: str):
        """Cached GET returning the raw decoded JSON (dict or list)."""
        cache_path = self.cache_dir / f"17lands_{cache_name}.json"
        if self._fresh(cache_path):
            return json.loads(cache_path.read_text(encoding="utf-8"))
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError):
            data = {}
        if self.use_cache:
            cache_path.write_text(json.dumps(data), encoding="utf-8")
        return data

    def color_ratings(self, set_code: str, fmt: str = "PremierDraft",
                      start_date: str | None = None, end_date: str | None = None
                      ) -> list[ArchetypeRating]:
        """Per-archetype (color / color-pair) win rates for a set/format.

        ``combine_splash=true`` collapses the base and '+ Splash' rows so each
        color pair appears exactly once.
        """
        rows = self._fetch(COLOR_RATINGS_URL, set_code, start_date, end_date, "colors",
                           {"event_type": fmt, "combine_splash": "true"})
        out: list[ArchetypeRating] = []
        for r in rows:
            short = str(r.get("short_name") or "").strip()
            out.append(ArchetypeRating(
                color_name=r.get("color_name", short),
                short_name=short,
                colors=frozenset(ch for ch in short if ch in "WUBRG"),
                wins=int(r.get("wins") or 0),
                games=int(r.get("games") or 0),
                is_summary=bool(r.get("is_summary")),
            ))
        return out

    def _fetch(self, url: str, set_code: str,
               start_date: str | None, end_date: str | None,
               kind: str, extra: dict[str, str]) -> list[dict]:
        start = start_date or DEFAULT_START
        end = end_date or date.today().isoformat()
        tag = "_".join(f"{k}-{v}" for k, v in sorted(extra.items()))
        # 'end' is always "now", so it's not part of the key; the TTL governs
        # freshness instead (and avoids accumulating one stale file per day).
        cache_path = self.cache_dir / f"17lands_{kind}_{set_code.upper()}_{tag}_{start}.json"
        if self._fresh(cache_path):
            return json.loads(cache_path.read_text(encoding="utf-8"))
        params = {"expansion": set_code.upper(), "start_date": start, "end_date": end, **extra}
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            rows = resp.json()
            if not isinstance(rows, list):
                rows = []
        except (requests.RequestException, ValueError):
            rows = []
        if self.use_cache:
            cache_path.write_text(json.dumps(rows), encoding="utf-8")
        return rows


def select_archetypes(color_ratings: list[ArchetypeRating],
                      min_playrate: float = ARCHETYPE_MIN_PLAYRATE,
                      max_archetypes: int = ARCHETYPE_MAX,
                      min_archetypes: int = ARCHETYPE_MIN,
                      include_mono: bool = False) -> list[ArchetypeRating]:
    """Pick a set's main archetypes by play rate, regardless of color count.

    Includes high-playrate 3-/5-color archetypes and drops barely-played 2-color
    ones. Falls back to the most-played few if nothing clears the threshold.
    """
    rows = [ar for ar in color_ratings if not ar.is_summary and ar.games > 0 and ar.colors]
    if not include_mono:
        rows = [ar for ar in rows if len(ar.colors) >= 2]
    if not rows:
        return []
    total = sum(ar.games for ar in rows)
    rows.sort(key=lambda ar: ar.games, reverse=True)
    selected = [ar for ar in rows if ar.games / total >= min_playrate]
    if len(selected) < min_archetypes:
        selected = rows[:min_archetypes]
    return selected[:max_archetypes]
