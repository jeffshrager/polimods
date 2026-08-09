"""Does homophily manufacture polarization, or only sharpen it?

Specific to experiments/202608091608_homophily_polarization/. generic_analyses/
plots one condition (or all of them) but never compares across electorate_shape,
which is the whole point of this sweep -- the shipped network_sweep only ever
runs two-camp, so it cannot tell "homophily deepens an existing split" apart
from "homophily creates a split that was not there."

ideology_sd alone cannot answer this: a unimodal electorate that stays unimodal
and a bimodal electorate whose two camps sit close together can land on the same
spread. What distinguishes them is coalition_gap -- the distance between
red_voter_ideology and blue_voter_ideology, i.e. where each party's actual
supporters sit -- at the final election of each run. If homophily manufactures
camps from single-peaked, coalition_gap should rise with homophily there too,
not just in two-camp.

Reads ../runs.csv (condition membership) and ../steps.csv (per-election record,
for the final election of each run). Writes into this folder:

    condition_summary.csv   ideology_sd and coalition_gap, mean +/- sd per condition
    coalition_gap.png       coalition_gap vs homophily, faceted by electorate_shape
    ideology_sd.png         ideology_sd vs homophily, same faceting, for contrast
    findings.md             the slopes this script computed, in words
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from generic_analyses.theme import apply, get_theme  # noqa: E402

EXPERIMENT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_final_states() -> list[dict]:
    runs = _read_csv(EXPERIMENT / "runs.csv")
    meta = {
        int(row["run_id"]): {
            "condition_index": int(row["condition_index"]),
            "electorate_shape": row["electorate_shape"],
            "homophily": float(row["homophily"]),
            "social_influence": float(row["social_influence"]),
        }
        for row in runs
    }

    last_row: dict[int, dict[str, str]] = {}
    with open(EXPERIMENT / "steps.csv", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            run_id = int(row["run_id"])
            election = int(row["election"])
            if run_id not in last_row or election > int(last_row[run_id]["election"]):
                last_row[run_id] = row

    records = []
    for run_id, info in meta.items():
        final = last_row[run_id]
        red = float(final["red_voter_ideology"])
        blue = float(final["blue_voter_ideology"])
        records.append(
            {
                **info,
                "ideology_sd": float(final["ideology_sd"]),
                "coalition_gap": red - blue,
            }
        )
    return records


def aggregate(records: list[dict]) -> list[dict]:
    keys = sorted(
        {(r["electorate_shape"], r["homophily"], r["social_influence"]) for r in records}
    )
    rows = []
    for shape, homophily, influence in keys:
        matches = [
            r
            for r in records
            if r["electorate_shape"] == shape
            and r["homophily"] == homophily
            and r["social_influence"] == influence
        ]
        sd_vals = np.array([r["ideology_sd"] for r in matches])
        gap_vals = np.array([r["coalition_gap"] for r in matches])
        rows.append(
            {
                "electorate_shape": shape,
                "homophily": homophily,
                "social_influence": influence,
                "n": len(matches),
                "ideology_sd_mean": sd_vals.mean(),
                "ideology_sd_sd": sd_vals.std(ddof=1),
                "coalition_gap_mean": gap_vals.mean(),
                "coalition_gap_sd": gap_vals.std(ddof=1),
            }
        )
    return rows


def write_summary(rows: list[dict]) -> Path:
    path = HERE / "condition_summary.csv"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def slope_by_shape(rows: list[dict], column: str) -> dict[str, float]:
    """Slope of `column` on homophily, pooled over social_influence, per shape."""
    slopes = {}
    for shape in sorted({r["electorate_shape"] for r in rows}):
        xs = np.array([r["homophily"] for r in rows if r["electorate_shape"] == shape])
        ys = np.array([r[column] for r in rows if r["electorate_shape"] == shape])
        slope, _ = np.polyfit(xs, ys, 1)
        slopes[shape] = float(slope)
    return slopes


def plot_by_shape(rows: list[dict], column: str, ylabel: str, out: Path) -> None:
    import matplotlib.pyplot as plt

    shapes = sorted({r["electorate_shape"] for r in rows})
    influences = sorted({r["social_influence"] for r in rows})
    fig, axes = plt.subplots(1, len(shapes), figsize=(4.5 * len(shapes), 3.6), sharey=True)

    for ax, shape in zip(axes, shapes):
        for influence in influences:
            matches = sorted(
                (r for r in rows if r["electorate_shape"] == shape and r["social_influence"] == influence),
                key=lambda r: r["homophily"],
            )
            xs = [r["homophily"] for r in matches]
            ys = [r[f"{column}_mean"] for r in matches]
            ax.plot(xs, ys, marker="o", markersize=3.5, label=f"influence = {influence:g}")
        ax.set_title(shape)
        ax.set_xlabel("homophily")
        ax.set_ylim(bottom=0)
    axes[0].set_ylabel(ylabel)
    axes[-1].legend(loc="upper left", bbox_to_anchor=(1.02, 1.0))
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def write_findings(sd_slopes: dict[str, float], gap_slopes: dict[str, float]) -> None:
    lines = [
        "# Findings: does homophily manufacture polarization, or only sharpen it?",
        "",
        "Slopes are `numpy.polyfit(homophily, value, 1)`, pooled over all five",
        "`social_influence` levels, on the final-election value of each run.",
        "",
        "| electorate_shape | d(ideology_sd)/d(homophily) | d(coalition_gap)/d(homophily) |",
        "|---|---:|---:|",
    ]
    for shape in sorted(sd_slopes):
        lines.append(f"| {shape} | {sd_slopes[shape]:+.4f} | {gap_slopes[shape]:+.4f} |")
    lines += [
        "",
        "`coalition_gap` is `red_voter_ideology - blue_voter_ideology` at the final",
        "election: how far apart each party's actual supporters sit, as opposed to",
        "`ideology_sd`, which is the spread of the whole electorate and cannot tell a",
        "unimodal electorate from two camps sitting close together.",
        "",
        "A positive `coalition_gap` slope in `single-peaked` is the manufacture",
        "signature: homophily is pulling the two parties' voters apart even though",
        "they started drawn from one hump. A positive slope in `two-camp` is the",
        "sharpen signature: the camps were already separate and homophily widens the",
        "gap further, or at least resists the collapse `network_sweep` documented.",
    ]
    (HERE / "findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    records = load_final_states()
    rows = aggregate(records)
    write_summary(rows)

    apply(get_theme("light"))
    plot_by_shape(rows, "ideology_sd", "final ideology_sd", HERE / "ideology_sd.png")
    plot_by_shape(rows, "coalition_gap", "final coalition_gap (red - blue)", HERE / "coalition_gap.png")

    sd_slopes = slope_by_shape(rows, "ideology_sd_mean")
    gap_slopes = slope_by_shape(rows, "coalition_gap_mean")
    write_findings(sd_slopes, gap_slopes)

    print(f"{len(records)} runs summarized into {len(rows)} conditions")
    for shape in sorted(sd_slopes):
        print(
            f"  {shape:>13}  d(ideology_sd)/d(homophily) = {sd_slopes[shape]:+.4f}   "
            f"d(coalition_gap)/d(homophily) = {gap_slopes[shape]:+.4f}"
        )


if __name__ == "__main__":
    main()
