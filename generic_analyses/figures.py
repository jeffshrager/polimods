"""The generic figures: what moved, over the elections of a sweep.

Every figure takes one condition -- one parameter setting, averaged over its
repetitions -- because a curve averaged across settings describes none of them.
Lines are means over runs; the shaded band is the electorate's own spread, not
uncertainty about the mean, and is labelled as such.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .dynamics import Condition, Experiment
from .theme import Theme

#: Small multiples stop being readable well before this; past it, ask for one
#: condition at a time.
MAX_FACETS = 12


# -- shared pieces ------------------------------------------------------------


def _subtitle(ax, text: str, theme: Theme) -> None:
    ax.set_title(text, color=theme.ink_secondary, fontsize=9, loc="left", pad=6)


def _end_labels(ax, entries, theme: Theme) -> None:
    """Label lines at their right end: a dot in the series colour, text in ink.

    Text carries no identity of its own -- the dot beside it does -- and labels
    are nudged apart when two lines finish at the same height, which is the usual
    outcome here: convergence is what the model is about.  The nudge is in points
    off the data point, so a label never drifts far enough to look like it
    belongs to a different line.
    """
    entries = [(x, y, label, color) for x, y, label, color in entries if np.isfinite(y)]
    if not entries:
        return

    low, high = ax.get_ylim()
    if high <= low:
        return
    # Convert once: the offsets below are in points, the data is not.
    points_per_unit = (ax.bbox.height / ax.figure.dpi * 72) / (high - low)
    minimum_gap = 11.0  # points; roughly one line of 8.5pt text

    entries.sort(key=lambda e: e[1])
    placed: list[float] = []
    for _x, y, _label, _color in entries:
        at = y * points_per_unit
        if placed and at - placed[-1] < minimum_gap:
            at = placed[-1] + minimum_gap
        placed.append(at)

    for (x, y, label, color), at in zip(entries, placed):
        ax.plot([x], [y], marker="o", markersize=4.5, color=color, zorder=5, clip_on=False)
        ax.annotate(
            label,
            xy=(x, y),
            xytext=(9, at - y * points_per_unit),
            textcoords="offset points",
            va="center",
            fontsize=8.5,
            color=theme.ink_secondary,
            annotation_clip=False,
        )


def _finish(
    fig,
    title: str,
    subtitle: str,
    theme: Theme,
    bottom: float = 0.0,
    header: float = 0.85,
) -> None:
    """Title block above the plots, in reserved space rather than on top of them.

    ``header`` is in inches, not figure fractions: the block is two lines of text
    whatever the figure's height, so reserving a fraction gives a squashed header
    on a short figure and a gap on a tall one.
    """
    inches = fig.get_figheight()
    top = 1 - header / inches
    engine = fig.get_layout_engine()
    if engine is not None:
        # rect is (left, bottom, width, height), so the height is what keeps the
        # plots clear of the header -- not the top edge.
        engine.set(rect=(0.01, bottom, 0.97, top - bottom))
    fig.suptitle(
        title, x=0.01, y=1 - 0.22 / inches, ha="left", va="top", fontsize=13,
        color=theme.ink, weight="medium",
    )
    if subtitle:
        fig.text(
            0.01, 1 - 0.52 / inches, subtitle, ha="left", va="top",
            fontsize=9, color=theme.ink_muted,
        )


def _header(experiment: Experiment, condition: Condition) -> str:
    runs = f"mean of {condition.runs} run{'s' if condition.runs != 1 else ''}"
    if condition.settings:
        return f"{experiment.name} — {condition.label} — {runs}"
    return f"{experiment.name} — {runs}"


# -- the figures --------------------------------------------------------------


def political_space(experiment: Experiment, condition: Condition, theme: Theme):
    """Where the parties are, over the electorate they are competing for.

    One axis, one unit: everything on it is a position on the same left-right
    scale, so vertical distance always means ideological distance.
    """
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    x = condition.elections

    if condition.has("ideology_p10", "ideology_p90"):
        ax.fill_between(
            x,
            condition["ideology_p10"],
            condition["ideology_p90"],
            color=theme.electorate,
            alpha=0.13,
            linewidth=0,
            label="Electorate, 10th–90th percentile",
        )
    if condition.has("ideology_p50"):
        ax.plot(
            x,
            condition["ideology_p50"],
            color=theme.electorate,
            linewidth=1.3,
            label="Median voter",
        )

    ax.plot(x, condition["blue_position"], color=theme.blue, label="Blue party")
    ax.plot(x, condition["red_position"], color=theme.red, label="Red party")

    for column, color, label in (
        ("blue_voter_ideology", theme.blue, "Blue voters"),
        ("red_voter_ideology", theme.red, "Red voters"),
    ):
        if condition.has(column):
            ax.plot(
                x,
                condition[column],
                color=color,
                linewidth=1.2,
                linestyle=(0, (4, 2)),
                alpha=0.85,
                label=f"{label} (coalition centre)",
            )

    ax.axhline(0, color=theme.axis, linewidth=0.8, zorder=0)
    ax.set_xlabel("election")
    ax.set_ylabel("ideology  (left −1 … +1 right)")
    ax.set_xlim(x.min(), x.max())
    ax.margins(y=0.14)

    ends = [
        (x[-1], condition["blue_position"][-1], "Blue party", theme.blue),
        (x[-1], condition["red_position"][-1], "Red party", theme.red),
    ]
    if condition.has("ideology_p50"):
        ends.append((x[-1], condition["ideology_p50"][-1], "Median voter", theme.electorate))
    _end_labels(ax, ends, theme)

    ax.legend(loc="upper left", ncol=3, columnspacing=1.6, handlelength=1.8)
    _finish(
        fig,
        "Where the parties are, and where the voters are",
        _header(experiment, condition),
        theme,
    )
    return fig


def competition(experiment: Experiment, condition: Condition, theme: Theme):
    """How the contest itself went: shares, margin, turnout, switching."""
    fig, axes = plt.subplots(2, 2, figsize=(9.5, 5.8), sharex=True)
    x = condition.elections

    # Only Blue's share is drawn: Red's is 100 minus it, and a second line that
    # carries no information is a second thing to read.
    ax = axes[0][0]
    ax.plot(x, condition["blue_share"], color=theme.blue, linewidth=1.4)
    # The 50% rule is the only reference the panel needs, and the subtitle says
    # what it means -- a label on it would sit on top of the data.
    ax.axhline(50, color=theme.ink_muted, linewidth=1.0, zorder=0)
    ax.set_ylabel("% of votes cast")
    _subtitle(ax, "Blue's share of the vote — above the 50% line is a Blue win", theme)

    for ax, column, title, ylabel in (
        (axes[0][1], "margin", "Winning margin — how one-sided each election was", "points"),
        (axes[1][0], "turnout_rate", "Turnout — the share who voted at all", "% of electorate"),
        (
            axes[1][1],
            "switch_rate",
            "Vote switching — repeat voters who changed side",
            "% of repeat voters",
        ),
    ):
        if not condition.has(column):
            ax.set_visible(False)
            continue
        ax.plot(x, condition[column], color=theme.electorate, linewidth=1.4)
        ax.set_ylabel(ylabel)
        _subtitle(ax, title, theme)

    for ax in axes[1]:
        ax.set_xlabel("election")
    for ax in fig.axes:
        ax.set_xlim(x.min(), x.max())
        ax.margins(y=0.16)

    _finish(fig, "How the competition went", _header(experiment, condition), theme)
    return fig


def convergence(experiment: Experiment, condition: Condition, theme: Theme):
    """The two distances that decide whether the model produces parity.

    Kept in two panels rather than one: they are the same unit but different
    objects, and a reader who sees them on one axis starts reading crossings as
    events.
    """
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.6), sharex=True)
    x = condition.elections

    axes[0].plot(x, condition["party_gap"], color=theme.electorate)
    axes[0].set_ylabel("distance between the parties")
    _subtitle(axes[0], "Party gap — 0 is two identical parties", theme)

    if condition.has("ideology_sd"):
        axes[1].plot(x, condition["ideology_sd"], color=theme.electorate)
        _subtitle(axes[1], "Electorate spread — 0 is everyone agreeing", theme)
    else:
        axes[1].set_visible(False)
    axes[1].set_ylabel("sd of voter ideology")

    for ax in axes:
        ax.set_xlabel("election")
        ax.set_xlim(x.min(), x.max())
        ax.set_ylim(bottom=0)
        ax.margins(y=0.12)

    _finish(fig, "Convergence", _header(experiment, condition), theme)
    return fig


def space_by_condition(experiment: Experiment, theme: Theme, columns: int = 3):
    """The headline figure once per condition, on shared axes so panels compare."""
    conditions = experiment.conditions[:MAX_FACETS]
    rows = int(np.ceil(len(conditions) / columns))
    fig, axes = plt.subplots(
        rows,
        columns,
        figsize=(3.4 * columns, 2.5 * rows + 0.6),
        sharex=True,
        sharey=True,
        squeeze=False,
    )
    flat = [ax for row in axes for ax in row]

    for ax, condition in zip(flat, conditions):
        x = condition.elections
        if condition.has("ideology_p10", "ideology_p90"):
            ax.fill_between(
                x,
                condition["ideology_p10"],
                condition["ideology_p90"],
                color=theme.electorate,
                alpha=0.13,
                linewidth=0,
            )
        if condition.has("ideology_p50"):
            ax.plot(x, condition["ideology_p50"], color=theme.electorate, linewidth=1.1)
        ax.plot(x, condition["blue_position"], color=theme.blue, linewidth=1.5)
        ax.plot(x, condition["red_position"], color=theme.red, linewidth=1.5)
        ax.axhline(0, color=theme.axis, linewidth=0.8, zorder=0)
        ax.set_xlim(x.min(), x.max())
        # One setting per line: panel titles sit side by side, and a single long
        # line runs into its neighbour.
        ax.set_title(
            "\n".join(part.strip() for part in condition.label.split(",")),
            color=theme.ink_secondary,
            fontsize=8.5,
            loc="left",
            pad=5,
        )

    for ax in flat[len(conditions) :]:
        ax.set_visible(False)
    for ax in axes[-1]:
        ax.set_xlabel("election")
    for row in axes:
        row[0].set_ylabel("ideology")

    handles = [
        plt.Line2D([], [], color=theme.blue, label="Blue party"),
        plt.Line2D([], [], color=theme.red, label="Red party"),
        plt.Line2D([], [], color=theme.electorate, linewidth=1.1, label="Median voter"),
        plt.Line2D(
            [], [], color=theme.electorate, alpha=0.3, linewidth=7,
            label="Electorate, 10th–90th percentile",
        ),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.005),
        ncol=4,
        handlelength=1.8,
    )

    dropped = len(experiment.conditions) - len(conditions)
    note = f"{experiment.name} — mean over repetitions"
    if dropped:
        note += f" — showing {len(conditions)} of {len(experiment.conditions)} conditions"
    _finish(fig, "Party positions across conditions", note, theme, bottom=0.06)
    return fig


# -- writing them out ---------------------------------------------------------

FIGURES = {
    "political_space": political_space,
    "competition": competition,
    "convergence": convergence,
}


def write_all(
    experiment: Experiment,
    condition: Condition,
    theme: Theme,
    out: Path,
    suffix: str = "",
) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, build in FIGURES.items():
        fig = build(experiment, condition, theme)
        path = out / f"{name}{suffix}.png"
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        written.append(path)
    return written
