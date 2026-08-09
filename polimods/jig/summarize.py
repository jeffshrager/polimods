"""Aggregate a finished sweep into per-condition statistics.

Reads ``manifest.json`` to learn which columns are the sweep axes, so the usual
call needs no arguments beyond the experiment folder.  Because every condition is
repeated, a single run is never the unit of interpretation -- mean and interval
across repetitions are.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .manifest import read_manifest
from .runner import RUNS_CSV


@dataclass
class Cell:
    """One condition's worth of repeated runs, for one metric."""

    n: int
    mean: float
    sd: float
    ci95: float
    minimum: float
    maximum: float


@dataclass
class Summary:
    experiment: str
    directory: Path
    by: tuple[str, ...]
    metrics: tuple[str, ...]
    conditions: list[tuple[Any, ...]]
    cells: dict[tuple[Any, ...], dict[str, Cell]]
    total_runs: int

    def value(self, condition: tuple[Any, ...], metric: str) -> Cell:
        return self.cells[condition][metric]


def _coerce(text: str) -> Any:
    if text in ("True", "true"):
        return True
    if text in ("False", "false"):
        return False
    try:
        value = float(text)
    except (TypeError, ValueError):
        return text
    return int(value) if value.is_integer() and "." not in text else value


def load_runs(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if path.is_dir():
        path = path / RUNS_CSV
    with open(path, newline="", encoding="utf-8") as handle:
        return [{k: _coerce(v) for k, v in row.items()} for row in csv.DictReader(handle)]


def summarize(
    target: str | Path,
    by: Sequence[str] | None = None,
    metrics: Sequence[str] | None = None,
) -> Summary:
    """Group a sweep's runs by its swept variables and reduce each group."""
    path = Path(target)
    directory = path.parent if path.is_file() else path

    manifest = read_manifest(directory)
    rows = load_runs(directory)
    if not rows:
        raise ValueError(f"no runs found in {directory / RUNS_CSV}")

    by = tuple(by) if by else tuple(manifest.get("sweep_variables", ()))
    missing = [name for name in by if name not in rows[0]]
    if missing:
        raise ValueError(
            f"column(s) not in {RUNS_CSV}: {', '.join(missing)}. "
            f"Available: {', '.join(rows[0])}"
        )

    metrics = tuple(metrics) if metrics else tuple(manifest.get("metrics", ()))
    metrics = tuple(m for m in metrics if m in rows[0])

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(tuple(row[name] for name in by), []).append(row)

    cells: dict[tuple[Any, ...], dict[str, Cell]] = {}
    for condition, group in grouped.items():
        per_metric = {}
        for metric in metrics:
            values = np.array(
                [float(r[metric]) for r in group if r[metric] != ""], dtype=float
            )
            n = len(values)
            sd = float(values.std(ddof=1)) if n > 1 else 0.0
            per_metric[metric] = Cell(
                n=n,
                mean=float(values.mean()) if n else math.nan,
                sd=sd,
                ci95=1.96 * sd / math.sqrt(n) if n > 1 else 0.0,
                minimum=float(values.min()) if n else math.nan,
                maximum=float(values.max()) if n else math.nan,
            )
        cells[condition] = per_metric

    return Summary(
        experiment=manifest.get("experiment", directory.name),
        directory=directory,
        by=by,
        metrics=metrics,
        conditions=sorted(grouped, key=_sort_key),
        cells=cells,
        total_runs=len(rows),
    )


def _sort_key(condition: tuple[Any, ...]) -> tuple:
    return tuple((0, v) if isinstance(v, (int, float)) else (1, str(v)) for v in condition)


def format_table(summary: Summary, show: str = "mean") -> str:
    """A fixed-width table: one row per condition, one column per metric."""
    headers = list(summary.by) + ["n"] + list(summary.metrics)
    rows: list[list[str]] = []

    for condition in summary.conditions:
        cells = summary.cells[condition]
        first = next(iter(cells.values()), None)
        row = [_fmt(v) for v in condition] + [str(first.n if first else 0)]
        for metric in summary.metrics:
            cell = cells[metric]
            if show == "ci":
                row.append(f"{cell.mean:.3f} +/-{cell.ci95:.3f}")
            elif show == "sd":
                row.append(f"{cell.mean:.3f} ({cell.sd:.3f})")
            else:
                row.append(f"{cell.mean:.3f}")
        rows.append(row)

    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows)) if rows else len(headers[i])
        for i in range(len(headers))
    ]
    lines = [
        "  ".join(h.rjust(w) for h, w in zip(headers, widths)),
        "  ".join("-" * w for w in widths),
    ]
    lines += ["  ".join(c.rjust(w) for c, w in zip(row, widths)) for row in rows]

    title = f"{summary.experiment}: {summary.total_runs} runs, {len(summary.conditions)} conditions"
    return "\n".join([title, ""] + lines)


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def plot(summary: Summary, metric: str, path: str | Path) -> Path:
    """A heatmap for two swept variables, a line chart for one.

    matplotlib is imported here rather than at module scope so the jig itself has
    no plotting dependency.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = Path(path)
    fig, ax = plt.subplots(figsize=(7, 5), constrained_layout=True)

    if len(summary.by) == 2:
        x_values = sorted({c[0] for c in summary.conditions}, key=_scalar_key)
        y_values = sorted({c[1] for c in summary.conditions}, key=_scalar_key)
        grid = np.full((len(y_values), len(x_values)), np.nan)
        for (x, y), cells in summary.cells.items():
            grid[y_values.index(y), x_values.index(x)] = cells[metric].mean

        image = ax.imshow(grid, origin="lower", aspect="auto", cmap="viridis")
        ax.set_xticks(range(len(x_values)), [_fmt(v) for v in x_values])
        ax.set_yticks(range(len(y_values)), [_fmt(v) for v in y_values])
        ax.set_xlabel(summary.by[0])
        ax.set_ylabel(summary.by[1])
        fig.colorbar(image, ax=ax, label=metric)
    else:
        x_values = [c[0] for c in summary.conditions]
        means = np.array([summary.cells[c][metric].mean for c in summary.conditions])
        errors = np.array([summary.cells[c][metric].ci95 for c in summary.conditions])
        positions = np.arange(len(x_values))
        ax.errorbar(positions, means, yerr=errors, marker="o", capsize=3)
        ax.set_xticks(positions, [_fmt(v) for v in x_values], rotation=45, ha="right")
        ax.set_xlabel(", ".join(summary.by))
        ax.set_ylabel(metric)

    ax.set_title(f"{summary.experiment}: {metric}")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _scalar_key(value: Any) -> tuple:
    return (0, value) if isinstance(value, (int, float)) else (1, str(value))
