"""Render analysis stats to PNG charts with matplotlib (headless)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .analyze import Analysis  # noqa: E402

# MTG-flavored palette (readable on white slides).
COLOR_HEX = {
    "W": "#E9E2B8",
    "U": "#2A78C2",
    "B": "#5A5A5A",
    "R": "#D3202A",
    "G": "#1E8A4C",
    "C": "#A6A6A6",
}
GOLD = "#C9A227"
ACCENT = "#34557A"
EDGE = "#2B2B2B"
COLOR_LABELS = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green", "C": "Colorless"}

plt.rcParams.update({
    "font.size": 12,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titlesize": 15,
    "axes.titleweight": "bold",
    "figure.facecolor": "white",
})


def _save(fig, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def _bar_labels(ax, bars, values):
    for bar, val in zip(bars, values):
        if val:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    str(val), ha="center", va="bottom", fontsize=10)


def color_chart(a: Analysis, path: Path) -> Path:
    keys = ["W", "U", "B", "R", "G", "C"]
    vals = [a.color_counts[k] for k in keys]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    bars = ax.bar([COLOR_LABELS[k] for k in keys], vals,
                  color=[COLOR_HEX[k] for k in keys], edgecolor=EDGE, linewidth=0.8)
    _bar_labels(ax, bars, vals)
    ax.set_ylabel("Cards (a card counts in each of its colors)")
    ax.set_title("Color distribution")
    ax.margins(y=0.15)
    return _save(fig, path)


def rarity_chart(a: Analysis, path: Path) -> Path:
    order = ["common", "uncommon", "rare", "mythic"]
    vals = [a.rarity_counts.get(r, 0) for r in order]
    colors = ["#9aa0a6", "#b9c4c9", "#d8a657", "#e06c1f"]
    fig, ax = plt.subplots(figsize=(6.2, 4.2))
    bars = ax.bar([r.title() for r in order], vals, color=colors, edgecolor=EDGE, linewidth=0.8)
    _bar_labels(ax, bars, vals)
    ax.set_ylabel("Cards")
    ax.set_title("Rarity breakdown")
    ax.margins(y=0.15)
    return _save(fig, path)


def curve_chart(a: Analysis, path: Path) -> Path:
    keys = list(range(8))
    vals = [a.curve[k] for k in keys]
    labels = [str(k) for k in range(7)] + ["7+"]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    bars = ax.bar(labels, vals, color=ACCENT, edgecolor=EDGE, linewidth=0.8)
    _bar_labels(ax, bars, vals)
    ax.set_xlabel("Mana value")
    ax.set_ylabel("Nonland cards")
    ax.set_title("Mana curve")
    ax.margins(y=0.15)
    return _save(fig, path)


def category_overview_chart(a: Analysis, path: Path) -> Path:
    from .categories import THEME_KEYS
    skip = set(THEME_KEYS) | {"creature_removal"}
    stats = [cs for cs in a.categories if cs.key not in skip]
    stats = sorted(stats, key=lambda cs: cs.count, reverse=True)
    labels = [cs.label for cs in stats]
    vals = [cs.count for cs in stats]
    fig, ax = plt.subplots(figsize=(8.0, 5.0))
    bars = ax.barh(labels, vals, color=ACCENT, edgecolor=EDGE, linewidth=0.8)
    for bar, val in zip(bars, vals):
        ax.text(bar.get_width() + max(vals) * 0.01, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel("Cards in set")
    ax.set_title("Card functions across the set")
    ax.margins(x=0.08)
    return _save(fig, path)


def removal_by_color_chart(a: Analysis, path: Path) -> Path:
    keys = ["W", "U", "B", "R", "G", "C"]
    vals = [a.removal_detail["by_color"][k] for k in keys]
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    bars = ax.bar([COLOR_LABELS[k] for k in keys], vals,
                  color=[COLOR_HEX[k] for k in keys], edgecolor=EDGE, linewidth=0.8)
    _bar_labels(ax, bars, vals)
    ax.set_ylabel("Removal cards")
    ax.set_title("Removal by color")
    ax.margins(y=0.15)
    return _save(fig, path)


def removal_speed_chart(a: Analysis, path: Path) -> Path:
    speed = a.removal_detail["speed"]
    labels = ["Instant", "Sorcery", "Permanent"]
    vals = [speed["instant"], speed["sorcery"], speed["permanent"]]
    colors = ["#1E8A4C", "#D3202A", "#7a7a7a"]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.4, 4.0))
    bars = ax1.bar(labels, vals, color=colors, edgecolor=EDGE, linewidth=0.8)
    _bar_labels(ax1, bars, vals)
    ax1.set_title("Removal by speed")
    ax1.set_ylabel("Cards")
    ax1.margins(y=0.15)

    cond = [a.removal_detail["unconditional"], a.removal_detail["conditional"]]
    cond_total = sum(cond) or 1
    ax2.pie(cond, labels=["Unconditional", "Conditional"],
            autopct=lambda pct: str(int(round(pct / 100 * cond_total))),
            colors=["#1E8A4C", "#d8a657"], wedgeprops={"edgecolor": "white"})
    ax2.set_title("Removal reliability (card counts)")
    return _save(fig, path)


def archetype_chart(a: Analysis, path: Path) -> Path:
    pairs = [ar["pair"] for ar in a.archetypes]
    vals = [ar["count"] for ar in a.archetypes]
    fig, ax = plt.subplots(figsize=(8.0, 4.2))
    bars = ax.bar(pairs, vals, color=GOLD, edgecolor=EDGE, linewidth=0.8)
    _bar_labels(ax, bars, vals)
    ax.set_ylabel("Multicolor (gold) cards")
    ax.set_xlabel("Color pair")
    ax.set_title("Archetype signposts — gold cards per pair")
    ax.margins(y=0.15)
    return _save(fig, path)


def archetype_winrate_chart(a: Analysis, path: Path) -> Path | None:
    rated = [ar for ar in a.archetypes if ar.get("win_rate") is not None]
    if not rated:
        return None
    rated = sorted(rated, key=lambda x: x["win_rate"], reverse=True)
    pairs = [ar["pair"] for ar in rated]
    vals = [ar["win_rate"] * 100 for ar in rated]
    # Games-weighted average (matches 17Lands' "Two-color" figure); an unweighted
    # mean under-counts because rarely-drafted weak pairs drag it down.
    total_games = sum(ar["games"] for ar in rated) or 1
    avg = sum(ar["win_rate"] * 100 * ar["games"] for ar in rated) / total_games
    fig, ax = plt.subplots(figsize=(8.4, 4.4))
    bars = ax.bar(pairs, vals, color=GOLD, edgecolor=EDGE, linewidth=0.8)
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                f"{val:.1f}", ha="center", va="bottom", fontsize=10)
    ax.axhline(avg, color=ACCENT, ls="--", lw=1.2, label=f"two-color avg {avg:.1f}%")
    ax.set_ylim(min(vals) - 1.5, max(vals) + 1.2)
    ax.set_ylabel("Win rate %")
    ax.set_xlabel("Color pair")
    ax.set_title("Archetype win rates (17Lands)")
    ax.legend(loc="lower right", frameon=False)
    return _save(fig, path)


def evasion_blockers_chart(a: Analysis, path: Path, keywords: list[str]) -> Path:
    """Grouped bars: per keyword, a WUBRG-colored bar for each color's count."""
    keys = ["W", "U", "B", "R", "G"]
    mat = a.keyword_color_matrix(keywords)
    import numpy as np
    x = np.arange(len(keywords))
    width = 0.16
    fig, ax = plt.subplots(figsize=(9.2, 4.6))
    for i, col in enumerate(keys):
        vals = [mat[k][col] for k in keywords]
        ax.bar(x + (i - 2) * width, vals, width, color=COLOR_HEX[col],
               edgecolor=EDGE, linewidth=0.6, label=COLOR_LABELS[col])
    ax.set_xticks(x)
    ax.set_xticklabels(keywords)
    ax.set_ylabel("Creatures")
    ax.set_title("Evasion & blocking abilities by color")
    ax.legend(ncol=5, loc="upper right", frameon=False, fontsize=10)
    ax.margins(y=0.18)
    return _save(fig, path)


def play_draw_chart(a: Analysis, path: Path) -> Path | None:
    pd = a.play_draw
    if not pd:
        return None
    labels = ["On the play", "On the draw"]
    vals = [pd.win_rate_on_play * 100, pd.win_rate_on_draw * 100]
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    bars = ax.bar(labels, vals, color=[ACCENT, "#A6A6A6"], edgecolor=EDGE, linewidth=0.8)
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.15,
                f"{val:.1f}%", ha="center", va="bottom", fontsize=12, fontweight="bold")
    ax.axhline(50, color="#888", ls="--", lw=1)
    ax.set_ylim(44, max(vals) + 2.5)
    ax.set_ylabel("Win rate %")
    ax.set_title("Play / draw win rate")
    return _save(fig, path)


def generate_charts(a: Analysis, outdir: Path) -> dict[str, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    charts = {
        "color": color_chart(a, outdir / "color.png"),
        "rarity": rarity_chart(a, outdir / "rarity.png"),
        "curve": curve_chart(a, outdir / "curve.png"),
        "categories": category_overview_chart(a, outdir / "categories.png"),
        "removal_color": removal_by_color_chart(a, outdir / "removal_color.png"),
        "removal_speed": removal_speed_chart(a, outdir / "removal_speed.png"),
        "archetypes": archetype_chart(a, outdir / "archetypes.png"),
    }
    wr = archetype_winrate_chart(a, outdir / "archetype_winrate.png")
    if wr:
        charts["archetype_winrate"] = wr
    pd = play_draw_chart(a, outdir / "play_draw.png")
    if pd:
        charts["play_draw"] = pd
    from .analyze import EVASION_KEYWORDS
    charts["evasion_blockers"] = evasion_blockers_chart(
        a, outdir / "evasion_blockers.png", EVASION_KEYWORDS)
    return charts
