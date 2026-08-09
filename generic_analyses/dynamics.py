"""Reading an experiment folder into per-election series, ready to plot.

The jig writes two tables.  ``runs.csv`` is one row per run: the condition it was
in and where it ended up.  ``steps.csv`` is one row per election of every run --
the dynamics -- and is written only when the spec sets
``run_metrics_every_step = true``.  These figures need the second one, so a
folder without it fails with that sentence rather than an empty plot.

Runs are grouped by condition and averaged election-by-election.  A condition is
the unit that means anything: averaging two different parameter settings together
produces a curve that describes neither.
"""

from __future__ import annotations

import csv
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

RUNS_CSV = "runs.csv"
STEPS_CSV = "steps.csv"
MANIFEST = "manifest.json"


class MissingSteps(FileNotFoundError):
    """Raised when an experiment folder has no per-election table."""


@dataclass
class Condition:
    """One parameter setting, averaged over its repetitions."""

    index: int
    settings: dict[str, Any]
    runs: int
    elections: np.ndarray
    #: column name -> mean over runs, one value per election
    mean: dict[str, np.ndarray] = field(default_factory=dict)

    @property
    def label(self) -> str:
        if not self.settings:
            return "all runs"
        return ", ".join(f"{k} = {_format(v)}" for k, v in self.settings.items())

    def __getitem__(self, column: str) -> np.ndarray:
        if column not in self.mean:
            raise KeyError(
                f"{column!r} is not in steps.csv "
                f"(have: {', '.join(sorted(self.mean))})"
            )
        return self.mean[column]

    def has(self, *columns: str) -> bool:
        return all(c in self.mean for c in columns)


@dataclass
class Experiment:
    directory: Path
    name: str
    description: str
    sweep_variables: tuple[str, ...]
    conditions: list[Condition]

    def condition(self, index: int) -> Condition:
        for condition in self.conditions:
            if condition.index == index:
                return condition
        available = ", ".join(str(c.index) for c in self.conditions)
        raise KeyError(f"no condition {index} in {self.name} (have: {available})")


def _format(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _as_float(text: str) -> float:
    """Blank cells and NetLogo-style booleans included, since both reach the CSV."""
    if text in ("", "nan", "NaN"):
        return float("nan")
    if text in ("True", "False"):
        return 1.0 if text == "True" else 0.0
    try:
        return float(text)
    except ValueError:
        return float("nan")


def load(directory: str | Path) -> Experiment:
    """Read an experiment folder into per-condition, per-election means."""
    directory = Path(directory)
    steps_path = directory / STEPS_CSV
    if not steps_path.exists():
        specs = sorted(directory.glob("*.toml"))
        spec = specs[0] if specs else directory / "<spec>.toml"
        raise MissingSteps(
            f"{steps_path} does not exist, so there are no dynamics to plot.\n"
            "Per-election output is written only when the spec sets "
            "run_metrics_every_step = true, and it is not committed either way.\n"
            f"Set it in {spec} and run the experiment again "
            "(the re-run gets its own stamped folder):\n"
            f"    python -m polimods.jig run {spec}"
        )

    manifest = _read_manifest(directory)
    sweeps = tuple(manifest.get("sweep_variables", ()))

    runs = _read_csv(directory / RUNS_CSV)
    condition_of: dict[int, int] = {}
    settings: dict[int, dict[str, Any]] = {}
    for row in runs:
        run_id = int(row["run_id"])
        index = int(row["condition_index"])
        condition_of[run_id] = index
        settings.setdefault(index, {k: _value(row[k]) for k in sweeps if k in row})

    steps = _read_csv(steps_path)
    if not steps:
        raise MissingSteps(f"{steps_path} is empty")

    columns = [c for c in steps[0] if c not in ("run_id", "winner")]
    conditions = [
        _collect(index, settings.get(index, {}), steps, condition_of, columns)
        for index in sorted(set(condition_of.values()))
    ]

    return Experiment(
        directory=directory,
        name=manifest.get("experiment", directory.name),
        description=manifest.get("description", ""),
        sweep_variables=sweeps,
        conditions=[c for c in conditions if c.runs],
    )


def _value(text: str) -> Any:
    if text in ("True", "False"):
        return text == "True"
    try:
        return int(text) if text.lstrip("-").isdigit() else float(text)
    except ValueError:
        return text


def _read_manifest(directory: Path) -> dict[str, Any]:
    import json

    path = directory / MANIFEST
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _collect(
    index: int,
    settings: dict[str, Any],
    steps: Iterable[dict[str, str]],
    condition_of: dict[int, int],
    columns: Sequence[str],
) -> Condition:
    """Average one condition's runs election by election."""
    by_run: dict[int, list[dict[str, str]]] = {}
    for row in steps:
        run_id = int(row["run_id"])
        if condition_of.get(run_id) == index:
            by_run.setdefault(run_id, []).append(row)

    if not by_run:
        return Condition(index, settings, 0, np.array([]), {})

    length = min(len(rows) for rows in by_run.values())
    elections = np.array([int(row["election"]) for row in next(iter(by_run.values()))[:length]])

    mean: dict[str, np.ndarray] = {}
    for column in columns:
        stacked = np.array(
            [[_as_float(row[column]) for row in rows[:length]] for rows in by_run.values()]
        )
        # nanmean: a party that drew no votes in some run contributes nothing to
        # its coalition centre that election rather than dragging it to zero.
        # An election where *no* run has a value stays NaN, and plots as a gap.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            mean[column] = np.nanmean(stacked, axis=0)

    return Condition(index, settings, len(by_run), elections, mean)
