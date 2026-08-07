"""The experimental jig: scriptable parameter sweeps of the two-party model.

A replacement for NetLogo's BehaviorSpace that runs from a TOML spec, parallelizes
across processes, seeds every run deterministically, and writes a self-describing
results folder.

    from polimods.jig import ExperimentSpec, run_experiment

    spec = ExperimentSpec.from_file("experiments/parity_sweep.toml")
    manifest = run_experiment(spec, jobs=8)
"""

from .manifest import build_manifest, finalize_manifest, read_manifest, write_manifest
from .runner import (
    DEFAULT_JOBS,
    RUNS_CSV,
    STEPS_CSV,
    execute_run,
    resolve_output_dir,
    run_experiment,
)
from .spec import ExperimentSpec, Run, SpecError, Sweep, derive_seed
from .summarize import Summary, format_table, load_runs, plot, summarize

__all__ = [
    "DEFAULT_JOBS",
    "ExperimentSpec",
    "RUNS_CSV",
    "Run",
    "STEPS_CSV",
    "SpecError",
    "Summary",
    "Sweep",
    "build_manifest",
    "derive_seed",
    "execute_run",
    "finalize_manifest",
    "format_table",
    "load_runs",
    "plot",
    "read_manifest",
    "resolve_output_dir",
    "run_experiment",
    "summarize",
    "write_manifest",
]
