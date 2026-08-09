"""Experiment specifications: the jig's equivalent of a BehaviorSpace experiment.

A spec is a TOML file naming the experiment, saying what it is for, and listing
the parameters to hold constant, the parameters to sweep, how many repetitions to
run per condition, and which metrics to record.  Reading it expands to a fully
enumerated list of runs, each with a deterministic seed, *before* anything
executes -- so a bad value fails the whole experiment immediately rather than 200
runs in.

    expname = "parity_sweep"        # short label; also names the output folder
    expdescr = '''                  # what the experiment is for, at any length
    Does losing-party adaptation generate parity?
    ...
    '''
    repetitions = 10
    steps = 100
    metrics = ["mean_margin", "control_change_rate"]

    [constants]
    social_network = false

    [sweep]
    base_pressure = [0.0, 0.25, 0.5, 0.75, 1.0]          # enumeratedValueSet
    party_adaptation = { first = 0.0, step = 0.1, last = 0.5 }   # steppedValueSet
"""

from __future__ import annotations

import itertools
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ..model import Model
from ..params import Params

#: Keys allowed at the top level of a spec file.
TOP_LEVEL_KEYS = {
    "expname",
    "expdescr",
    "repetitions",
    "steps",
    "metrics",
    "run_metrics_every_step",
    "base_seed",
    "constants",
    "sweep",
}

#: Earlier spelling, still read so an old spec file does not become unrunnable.
ALIASES = {"name": "expname", "description": "expdescr"}

DEFAULT_BASE_SEED = 20260807

#: What an expname may contain, since it becomes a directory name.
_NAME = re.compile(r"[A-Za-z0-9_-]+")


class SpecError(ValueError):
    """Raised for a malformed or invalid experiment specification."""


def _normalize_aliases(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept the old ``name``/``description`` spelling, but never both at once."""
    raw = dict(raw)
    for old, new in ALIASES.items():
        if old not in raw:
            continue
        if new in raw:
            raise SpecError(
                f"spec sets both {old!r} and {new!r}; {old!r} is the old spelling "
                f"of {new!r}, so keep one"
            )
        raw[new] = raw.pop(old)
    return raw


@dataclass(frozen=True)
class Sweep:
    """One swept variable: the values it takes and how they were specified."""

    name: str
    values: tuple[Any, ...]
    definition: dict[str, Any]

    @property
    def n(self) -> int:
        return len(self.values)


@dataclass(frozen=True)
class Run:
    """A single model run: one condition, one repetition, one seed."""

    run_id: int
    condition_index: int
    repetition: int
    seed: int
    params: Params
    condition: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExperimentSpec:
    #: Short label: the experiment's name everywhere, and the name of the folder
    #: it writes into.  Kept to characters a directory name can hold.
    expname: str
    #: What the experiment is for, at whatever length that takes -- the question
    #: it is asking, why these variables, what would count as an answer.  A
    #: sweep whose point is not written down is a table nobody can interpret
    #: later, and the manifest is where it survives.
    expdescr: str
    repetitions: int
    steps: int
    metrics: tuple[str, ...]
    run_metrics_every_step: bool
    base_seed: int
    constants: dict[str, Any]
    sweeps: tuple[Sweep, ...]
    source: Path | None = None

    # -- construction ---------------------------------------------------------

    @classmethod
    def from_file(cls, path: str | Path) -> "ExperimentSpec":
        path = Path(path)
        try:
            with open(path, "rb") as handle:
                raw = tomllib.load(handle)
        except FileNotFoundError:
            raise SpecError(f"no such experiment spec: {path}") from None
        except tomllib.TOMLDecodeError as error:
            raise SpecError(f"{path}: invalid TOML: {error}") from None
        return cls.from_dict(raw, source=path)

    @classmethod
    def from_dict(cls, raw: dict[str, Any], source: Path | None = None) -> "ExperimentSpec":
        raw = _normalize_aliases(raw)
        unknown = set(raw) - TOP_LEVEL_KEYS
        if unknown:
            raise SpecError(
                f"unknown top-level key(s): {', '.join(sorted(unknown))}. "
                f"Expected one of {', '.join(sorted(TOP_LEVEL_KEYS))}"
            )

        expname = raw.get("expname") or (source.stem if source else None)
        if not expname:
            raise SpecError("spec needs an 'expname'")
        if not _NAME.fullmatch(str(expname)):
            # The expname becomes a directory name, so it has to be one.
            raise SpecError(
                f"expname {expname!r} is not usable as a folder name: use letters, "
                "digits, '-' and '_' only"
            )

        valid_params = set(Params.field_names())

        constants = dict(raw.get("constants", {}))
        bad = set(constants) - valid_params
        if bad:
            raise SpecError(
                f"unknown parameter(s) in [constants]: {', '.join(sorted(bad))}"
            )

        sweeps = []
        for key, definition in raw.get("sweep", {}).items():
            if key not in valid_params:
                raise SpecError(f"unknown parameter in [sweep]: {key}")
            if key in constants:
                raise SpecError(f"{key} appears in both [constants] and [sweep]")
            sweeps.append(Sweep(key, _expand(key, definition), _describe(definition)))

        if not sweeps:
            raise SpecError(
                "spec has no [sweep] variables; use [constants] plus a single "
                "repetition if that is really what you want"
            )

        metrics = tuple(raw.get("metrics", Model.METRICS))
        unknown_metrics = [m for m in metrics if m not in Model.METRICS]
        if unknown_metrics:
            raise SpecError(
                f"unknown metric(s): {', '.join(unknown_metrics)}. "
                f"Available: {', '.join(Model.METRICS)}"
            )

        repetitions = int(raw.get("repetitions", 1))
        steps = int(raw.get("steps", 100))
        if repetitions < 1:
            raise SpecError("repetitions must be at least 1")
        if steps < 1:
            raise SpecError("steps must be at least 1")

        spec = cls(
            expname=str(expname),
            expdescr=str(raw.get("expdescr", "")).strip(),
            repetitions=repetitions,
            steps=steps,
            metrics=metrics,
            run_metrics_every_step=bool(raw.get("run_metrics_every_step", False)),
            base_seed=int(raw.get("base_seed", DEFAULT_BASE_SEED)),
            constants=constants,
            sweeps=tuple(sweeps),
            source=source,
        )
        spec.validate()
        return spec

    # -- expansion ------------------------------------------------------------

    @property
    def summary(self) -> str:
        """The first line of ``expdescr``, for places that have one row to spare."""
        return self.expdescr.strip().splitlines()[0] if self.expdescr.strip() else ""

    @property
    def sweep_names(self) -> tuple[str, ...]:
        return tuple(s.name for s in self.sweeps)

    @property
    def condition_count(self) -> int:
        count = 1
        for sweep in self.sweeps:
            count *= sweep.n
        return count

    @property
    def total_runs(self) -> int:
        return self.condition_count * self.repetitions

    def conditions(self) -> list[dict[str, Any]]:
        """The Cartesian product of the swept variables, in declaration order."""
        return [
            dict(zip(self.sweep_names, combination))
            for combination in itertools.product(*(s.values for s in self.sweeps))
        ]

    def params_for(self, condition: dict[str, Any]) -> Params:
        return Params(**{**self.constants, **condition})

    def runs(self) -> list[Run]:
        runs = []
        run_id = 0
        for condition_index, condition in enumerate(self.conditions()):
            params = self.params_for(condition)
            for repetition in range(self.repetitions):
                runs.append(
                    Run(
                        run_id=run_id,
                        condition_index=condition_index,
                        repetition=repetition,
                        seed=derive_seed(self.base_seed, condition_index, repetition),
                        params=params,
                        condition=condition,
                    )
                )
                run_id += 1
        return runs

    def validate(self) -> "ExperimentSpec":
        """Check every condition the experiment will actually run.

        Cheap relative to the sweep itself, and it turns a typo like
        ``identity_strength = 20`` into an error before the first process starts.
        """
        for condition in self.conditions():
            try:
                self.params_for(condition).validate()
            except (ValueError, TypeError) as error:
                raise SpecError(f"condition {condition}: {error}") from None
        return self


def derive_seed(base_seed: int, condition_index: int, repetition: int) -> int:
    """A stable seed for one run.

    Derived from the triple rather than from a position in the run list, so a
    single run can be reproduced on its own and adding conditions to a spec does
    not reshuffle the seeds of the conditions already there.
    """
    sequence = np.random.SeedSequence([base_seed, condition_index, repetition])
    return int(sequence.generate_state(1, dtype=np.uint64)[0])


def _expand(name: str, definition: Any) -> tuple[Any, ...]:
    """Turn a sweep definition into the explicit list of values it stands for."""
    if isinstance(definition, (list, tuple)):
        if not definition:
            raise SpecError(f"sweep '{name}' has no values")
        return tuple(definition)

    if isinstance(definition, dict):
        missing = {"first", "step", "last"} - set(definition)
        extra = set(definition) - {"first", "step", "last"}
        if missing or extra:
            raise SpecError(
                f"sweep '{name}' must be a list of values or a table with "
                f"first/step/last, got keys {sorted(definition)}"
            )
        first = float(definition["first"])
        step = float(definition["step"])
        last = float(definition["last"])
        if step <= 0:
            raise SpecError(f"sweep '{name}': step must be positive")
        if last < first:
            raise SpecError(f"sweep '{name}': last must not be below first")
        # NetLogo's steppedValueSet includes 'last' when it lands on the grid.
        count = int((last - first) / step + 1e-9) + 1
        values = [round(first + i * step, 10) for i in range(count)]
        return tuple(values)

    # A bare scalar in [sweep] is a one-value sweep, which is legal and useful
    # when a variable is swept in a sibling spec.
    return (definition,)


def _describe(definition: Any) -> dict[str, Any]:
    if isinstance(definition, dict):
        return {"first": definition["first"], "step": definition["step"], "last": definition["last"]}
    if isinstance(definition, (list, tuple)):
        return {"enumerated": list(definition)}
    return {"enumerated": [definition]}
