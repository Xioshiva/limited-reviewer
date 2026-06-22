"""Card-function categories for Limited analysis.

The base signal is Scryfall's community "Tagger" oracle tags (``otag:``), which
are queried per set. On top of that we layer transparent, Limited-aware
heuristics -- e.g. removal is only as good as it is fast and unconditional, so
we split it by spell speed. These heuristics are intentionally simple and
auditable; the generated deck lists the actual cards in each bucket so a human
can sanity-check them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

WUBRG = ["W", "U", "B", "R", "G"]
COLOR_NAMES = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green", "C": "Colorless"}


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    otag: str
    blurb: str
    theme: bool = False  # archetype-glue theme (vs. core interaction)


# Only tags verified to exist & be populated on Scryfall are used here.
CATEGORIES: list[Category] = [
    Category("removal", "Removal", "removal",
             "Spells/abilities that kill, exile, or neutralize a permanent."),
    Category("board_wipe", "Sweepers / Wraths", "board-wipe",
             "Mass removal — 'wrath of God' effects that hit many permanents."),
    Category("creature_removal", "Creature removal", "creature-removal",
             "Removal that specifically answers creatures."),
    Category("combat_trick", "Combat tricks", "combat-trick",
             "Instant-speed effects used to win combat or dodge removal."),
    Category("ramp", "Ramp / acceleration", "ramp",
             "Mana acceleration and fixing effects."),
    Category("burn", "Burn / direct damage", "burn",
             "Direct damage to creatures or players."),
    Category("bounce", "Bounce", "bounce",
             "Return permanents to hand (tempo)."),
    Category("counterspell", "Counterspells", "counterspell",
             "Counter target spell effects."),
    Category("lifegain", "Lifegain", "lifegain",
             "Incidental and dedicated life gain."),
    Category("evasion", "Evasion", "evasion",
             "Flying, menace, trample and other ways through."),
    Category("tutor", "Tutors", "tutor",
             "Search effects that find specific cards."),
]

CATEGORIES_BY_KEY = {c.key: c for c in CATEGORIES}
THEME_KEYS = [c.key for c in CATEGORIES if c.theme]


# -- Limited-aware heuristics ---------------------------------------------

def card_colors(card: dict) -> list[str]:
    """WUBRG colors of a card; ['C'] if colorless. Uses faces when needed."""
    colors = card.get("colors")
    if colors is None and "card_faces" in card:
        colors = []
        for face in card["card_faces"]:
            colors.extend(face.get("colors", []))
    colors = sorted(set(colors or []), key=WUBRG.index) if colors else []
    return colors or ["C"]


def color_identity(card: dict) -> set[str]:
    return set(card.get("color_identity") or [])


def oracle_text(card: dict) -> str:
    if card.get("oracle_text"):
        return card["oracle_text"]
    if "card_faces" in card:
        return "\n".join(f.get("oracle_text", "") for f in card["card_faces"])
    return ""


def type_line(card: dict) -> str:
    return card.get("type_line") or " // ".join(
        f.get("type_line", "") for f in card.get("card_faces", [])
    )


def is_instant_speed(card: dict) -> bool:
    """True if the card can be cast at instant speed (instant or has flash)."""
    tl = type_line(card).lower()
    if "instant" in tl:
        return True
    return bool(re.search(r"\bflash\b", oracle_text(card).lower()))


def removal_speed(card: dict) -> str:
    """Classify a removal card as 'instant', 'sorcery', or 'permanent'."""
    tl = type_line(card).lower()
    if "instant" in tl or re.search(r"\bflash\b", oracle_text(card).lower()):
        return "instant"
    if "sorcery" in tl:
        return "sorcery"
    # Creatures/enchantments/artifacts that remove via an ability.
    return "permanent"


# Phrases that usually signal *unconditional* removal in Limited.
_UNCONDITIONAL = re.compile(
    r"(destroy target|exile target|deals? \d+ damage to (any target|target creature)"
    r"|return target .*to (its owner'?s )?hand|fight)",
    re.IGNORECASE,
)
# Phrases that usually make removal conditional / narrow.
_CONDITIONAL = re.compile(
    r"(can't block|tapped creature|attacking or blocking|with (flying|power)"
    r"|nonland permanent an opponent controls.*mana value \d"
    r"|creature with (mana value|power) \d|if its power)",
    re.IGNORECASE,
)


def removal_is_unconditional(card: dict) -> bool:
    text = oracle_text(card)
    if _CONDITIONAL.search(text):
        return False
    return bool(_UNCONDITIONAL.search(text))
