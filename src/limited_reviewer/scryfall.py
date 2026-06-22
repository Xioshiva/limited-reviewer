"""Scryfall API client.

Scryfall requires both a ``User-Agent`` and an ``Accept`` header on every
request, and asks callers to throttle to ~10 requests/sec. Responses are
cached on disk so repeated runs for the same set don't re-hit the API.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import requests

API = "https://api.scryfall.com"
HEADERS = {
    "User-Agent": "limited-reviewer/0.1 (https://github.com/local/limited-reviewer)",
    "Accept": "application/json",
}
# Scryfall asks for 50-100ms between requests; 120ms is comfortably polite.
RATE_LIMIT_SECONDS = 0.12

CACHE_DIR = Path(__file__).resolve().parents[2] / "cache"


class ScryfallError(RuntimeError):
    pass


class ScryfallClient:
    def __init__(self, cache_dir: Path | None = None, use_cache: bool = True):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.use_cache = use_cache
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_request = 0.0

    # -- low level ---------------------------------------------------------
    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < RATE_LIMIT_SECONDS:
            time.sleep(RATE_LIMIT_SECONDS - elapsed)
        self._last_request = time.monotonic()

    def _cache_path(self, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{digest}.json"

    def _get(self, url: str, params: dict | None = None) -> dict:
        cache_key = url + "?" + json.dumps(params or {}, sort_keys=True)
        cache_path = self._cache_path(cache_key)
        if self.use_cache and cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        self._throttle()
        resp = self.session.get(url, params=params, timeout=30)
        if resp.status_code == 404:
            # Scryfall returns 404 for a search that matched nothing.
            data = {"object": "list", "total_cards": 0, "data": [], "has_more": False}
        elif not resp.ok:
            raise ScryfallError(f"{resp.status_code} for {resp.url}: {resp.text[:200]}")
        else:
            data = resp.json()

        if self.use_cache:
            cache_path.write_text(json.dumps(data), encoding="utf-8")
        return data

    # -- public ------------------------------------------------------------
    def get_set(self, code: str) -> dict:
        """Return set metadata (name, released_at, card_count, icon, ...)."""
        return self._get(f"{API}/sets/{code.lower()}")

    def search_all(self, query: str, unique: str = "cards") -> list[dict]:
        """Return every card matching a Scryfall search query (handles paging)."""
        cards: list[dict] = []
        params = {"q": query, "unique": unique, "order": "set"}
        url = f"{API}/cards/search"
        page = self._get(url, params)
        cards.extend(page.get("data", []))
        while page.get("has_more"):
            # next_page already carries the encoded query params.
            page = self._get(page["next_page"])
            cards.extend(page.get("data", []))
        return cards

    def cards_in_set(self, code: str) -> list[dict]:
        """Unique cards in a set's draft boosters (the Limited-relevant pool).

        ``is:booster`` excludes Starter Deck / promo / digital-only cards that a
        drafter can't actually open, which is also what 17Lands draft data covers.
        Some sets don't have the booster flag populated on Scryfall, though, so we
        fall back to all cards in the set when the booster query comes back empty.
        """
        code = code.lower()
        cards = self.search_all(f"set:{code} is:booster")
        if len(cards) < 50:
            cards = self.search_all(f"set:{code}")
        return cards

    def names_matching(self, code: str, otag: str) -> set[str]:
        """Set of card names in ``code`` carrying a given Scryfall oracle tag."""
        cards = self.search_all(f"set:{code.lower()} otag:{otag}")
        return {c["name"] for c in cards}

    # -- card images -------------------------------------------------------
    def download_image(self, url: str) -> Path | None:
        """Download a card image (front face) to the cache, return local path."""
        if not url:
            return None
        img_dir = self.cache_dir / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        ext = ".png" if ".png" in url.split("?")[0] else ".jpg"
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        path = img_dir / f"{digest}{ext}"
        if path.exists() and path.stat().st_size > 0:
            return path
        self._throttle()
        try:
            resp = self.session.get(url, timeout=30, headers={"Accept": "image/*"})
            resp.raise_for_status()
            path.write_bytes(resp.content)
            return path
        except requests.RequestException:
            return None


def front_image_url(card: dict, size: str = "normal") -> str | None:
    """Best image URL for a card's front (handles double-faced layouts)."""
    iu = card.get("image_uris")
    if not iu and card.get("card_faces"):
        iu = card["card_faces"][0].get("image_uris")
    return iu.get(size) if iu else None
