"""The per-experiment ``manifest.json``.

Every experiment folder carries one.  It records *all* model variables -- not only
the swept ones -- with the role each played, so the manifest alone determines what
was run.  A CSV without this is unfalsifiable six months later: you cannot tell
whether a surprising number came from the mechanism you were studying or from a
parameter you forgot you had pinned.

The manifest is written before the first run and updated when the sweep finishes,
so an interrupted experiment still leaves a record of what it was trying to do.
"""

from __future__ import annotations

import dataclasses
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ..params import BOUNDS, NETLOGO_DEFAULTS, Params
from .spec import ExperimentSpec

MANIFEST_NAME = "manifest.json"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _git_state(repo: Path) -> dict[str, Any]:
    def run(*args: str) -> str | None:
        try:
            result = subprocess.run(
                args, cwd=repo, capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    commit = run("git", "rev-parse", "--short", "HEAD")
    # Untracked files are excluded: the question this answers is "was the code
    # that produced these results modified relative to the commit", and the
    # results being written right now are themselves untracked.
    status = run("git", "status", "--porcelain", "--untracked-files=no")
    return {
        "git_commit": commit,
        "git_dirty": bool(status) if status is not None else None,
    }


def _param_type(name: str) -> str:
    for field in dataclasses.fields(Params):
        if field.name == name:
            return field.type if isinstance(field.type, str) else field.type.__name__
    return "unknown"


def variable_entries(spec: ExperimentSpec) -> dict[str, dict[str, Any]]:
    """Describe every model variable: swept, pinned by the spec, or left at default."""
    swept = {sweep.name: sweep for sweep in spec.sweeps}
    entries: dict[str, dict[str, Any]] = {}

    for name in Params.field_names():
        entry: dict[str, Any] = {"type": _param_type(name)}

        if name in swept:
            sweep = swept[name]
            entry["role"] = "swept"
            entry["sweep"] = sweep.definition
            entry["values"] = list(sweep.values)
            entry["n"] = sweep.n
        elif name in spec.constants:
            entry["role"] = "constant"
            entry["value"] = spec.constants[name]
        else:
            entry["role"] = "default"
            entry["value"] = NETLOGO_DEFAULTS[name]

        if name in BOUNDS:
            low, high, step = BOUNDS[name]
            entry["bounds"] = [low, high]
            entry["slider_step"] = step
        entry["netlogo_default"] = NETLOGO_DEFAULTS[name]

        # Put 'role' first so the file reads well.
        entries[name] = {"role": entry.pop("role"), **entry}

    return entries


def build_manifest(
    spec: ExperimentSpec,
    *,
    output_dir: Path,
    jobs: int,
    repo: Path | None = None,
    renamed_from: str | None = None,
    spec_file: Path | None = None,
) -> dict[str, Any]:
    repo = repo or Path(__file__).resolve().parents[2]
    # The spec recorded is the copy inside the output folder when there is one:
    # that is the file this run actually used and the one that will still be
    # there later.
    recorded_spec = spec_file if spec_file is not None else spec.source
    return {
        "experiment": spec.expname,
        "description": spec.expdescr,
        "spec_file": _relative_to(recorded_spec, repo),
        "created": _timestamp(),
        "completed": None,
        "status": "running",
        **_git_state(repo),
        "base_seed": spec.base_seed,
        "repetitions": spec.repetitions,
        "steps": spec.steps,
        "run_metrics_every_step": spec.run_metrics_every_step,
        "conditions": spec.condition_count,
        "total_runs": spec.total_runs,
        "runs_completed": 0,
        "wall_seconds": None,
        "metrics": list(spec.metrics),
        "sweep_variables": list(spec.sweep_names),
        "variables": variable_entries(spec),
        "output_dir": _relative_to(output_dir, repo),
        "renamed_from": renamed_from,
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "platform": sys.platform,
            "machine": platform.machine(),
            "jobs": jobs,
        },
    }


def _relative_to(path: str | Path | None, repo: Path) -> str | None:
    """Repo-relative when the path is inside the repo, absolute otherwise.

    Manifests get committed and read on other machines, where an absolute path
    to someone else's home directory says nothing.
    """
    if path is None:
        return None
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(repo.resolve()))
    except ValueError:
        return str(resolved)


def write_manifest(directory: Path, manifest: dict[str, Any]) -> Path:
    path = Path(directory) / MANIFEST_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, default=_jsonable)
        handle.write("\n")
    return path


def read_manifest(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if path.is_dir():
        path = path / MANIFEST_NAME
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def finalize_manifest(
    directory: Path,
    *,
    runs_completed: int,
    wall_seconds: float,
    status: str = "complete",
    error: str | None = None,
) -> dict[str, Any]:
    manifest = read_manifest(directory)
    manifest["status"] = status
    manifest["runs_completed"] = runs_completed
    manifest["wall_seconds"] = round(wall_seconds, 2)
    manifest["completed"] = _timestamp()
    if error:
        manifest["error"] = error
    write_manifest(directory, manifest)
    return manifest


def _jsonable(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")
