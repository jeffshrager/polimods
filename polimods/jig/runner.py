"""Parallel execution of an experiment spec.

The jig's BehaviorSpace equivalent: expand a spec into runs, execute them across
processes, and stream results to CSV as they land.  Output goes to
``experiments/<YYYYMMDDHHMM>_<experiment>/``, which holds the spec that produced
it, the manifest describing it, and every file it wrote -- one stamped folder is
the whole experiment.
"""

from __future__ import annotations

import csv
import os
import re
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from ..history import ElectionRecord
from ..model import Model
from .manifest import (
    MANIFEST_NAME,
    build_manifest,
    finalize_manifest,
    read_manifest,
    write_manifest,
)
from .spec import ExperimentSpec, Run

RUNS_CSV = "runs.csv"
STEPS_CSV = "steps.csv"

#: Two cores are left for the operating system and for whatever else the user is
#: doing; a sweep should not make the machine unusable.
DEFAULT_JOBS = max(1, (os.cpu_count() or 4) - 2)


#: A folder is an experiment folder when it is named ``YYYYMMDDHHMM_<something>``.
DATED_FOLDER = re.compile(r"^\d{12}_")

#: Stamps carry the minute, not just the day: several experiments a day is the
#: normal case here, and a date alone would collide by lunchtime.  Local time,
#: because it is read against the user's memory of when they ran things; the
#: manifest's ``created`` field is the UTC record.
STAMP_FORMAT = "%Y%m%d%H%M"


def default_experiments_root() -> Path:
    return Path(__file__).resolve().parents[2] / "experiments"


def dated_name(name: str, on: datetime | None = None) -> str:
    """``202608071014_parity_sweep``: the name of one experiment's folder."""
    return f"{(on or datetime.now()).strftime(STAMP_FORMAT)}_{name}"


# -- execution ---------------------------------------------------------------


def execute_run(
    run: Run,
    steps: int,
    metrics: Sequence[str],
    record_steps: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run one model to completion and return its result row (plus per-election rows)."""
    model = Model(run.params, seed=run.seed, validate=False)
    model.run(steps)

    row: dict[str, Any] = {
        "run_id": run.run_id,
        "condition_index": run.condition_index,
        "repetition": run.repetition,
        "seed": run.seed,
    }
    row.update(run.condition)
    row.update(model.metrics(tuple(metrics)))

    step_rows: list[dict[str, Any]] = []
    if record_steps:
        for record in model.history:
            step_rows.append({"run_id": run.run_id, **record.as_dict()})

    return row, step_rows


def _worker(job: tuple[Run, int, Sequence[str], bool]):
    return execute_run(*job)


# -- output location ---------------------------------------------------------


def _has_results(directory: Path) -> bool:
    """True once a run has written here.  An empty folder holding only the spec
    is not a previous experiment, so writing into it clobbers nothing."""
    return (directory / MANIFEST_NAME).exists() or (directory / RUNS_CSV).exists()


def _latest_dated(root: Path, name: str) -> Path | None:
    """The most recent existing ``<stamp>_<name>`` folder under ``root``."""
    if not root.exists():
        return None
    pattern = re.compile(rf"\d{{12}}_{re.escape(name)}(_\d+)?$")
    matches = [p for p in root.iterdir() if p.is_dir() and pattern.match(p.name)]
    return max(matches, key=lambda p: p.name) if matches else None


def resolve_output_dir(
    spec: ExperimentSpec,
    *,
    root: Path | None = None,
    out: Path | None = None,
    resume: bool = False,
    now: datetime | None = None,
) -> tuple[Path, str | None]:
    """Pick the folder for this experiment, without ever clobbering an old one.

    An experiment lives in one stamped folder, ``<root>/<YYYYMMDDHHMM>_<name>/``,
    which holds its spec and everything the run writes.  A spec that already sits
    in such a folder is run in place; a loose spec gets a folder stamped with the
    current minute, and the spec is copied into it by :func:`run_experiment`.

    Returns ``(directory, renamed_from)``.  ``renamed_from`` is set when the
    natural folder was already occupied by a finished run and a suffix was added,
    so the new manifest can say what it collided with.
    """
    if out is not None:
        return Path(out), None

    source = Path(spec.source).resolve() if spec.source else None
    if root is not None:
        root = Path(root)
        directory = root / dated_name(spec.expname, now)
    elif source is not None and DATED_FOLDER.match(source.parent.name):
        # The spec already lives in its own experiment folder: that is the folder.
        directory = source.parent
        root = directory.parent
    else:
        root = source.parent if source is not None else default_experiments_root()
        directory = root / dated_name(spec.expname, now)

    if resume:
        # A resumed sweep is always older than the current stamp.
        if not _has_results(directory):
            existing = _latest_dated(root, spec.expname)
            if existing is not None:
                return existing, None
        return directory, None

    if not _has_results(directory):
        return directory, None

    # The folder is taken by a finished run.  A re-run is a new experiment, so it
    # gets its own stamp -- and a suffix if the same minute is taken too.
    collided_with = str(directory)
    stem = dated_name(spec.expname, now)
    candidate = root / stem
    suffix = 2
    while candidate.exists():
        candidate = root / f"{stem}_{suffix}"
        suffix += 1
    return candidate, collided_with


def _place_spec(spec: ExperimentSpec, directory: Path) -> Path | None:
    """Ensure the spec sits in the folder it produced, and return where it landed.

    A folder that carries its own spec can be re-run, diffed against a later
    sweep, or read six months later without hunting for the file that made it.
    An existing copy is left alone rather than overwritten: on ``--resume`` the
    copy is what earlier runs actually used.
    """
    if spec.source is None:
        return None
    source = Path(spec.source).resolve()
    if source.parent == directory.resolve():
        return source
    copy = directory / source.name
    if not copy.exists():
        shutil.copy2(source, copy)
    return copy


def _completed_run_ids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as handle:
        return {int(row["run_id"]) for row in csv.DictReader(handle) if row.get("run_id")}


# -- the sweep ---------------------------------------------------------------


def run_experiment(
    spec: ExperimentSpec,
    *,
    jobs: int | None = None,
    root: Path | None = None,
    out: Path | None = None,
    resume: bool = False,
    progress: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    jobs = jobs or DEFAULT_JOBS
    directory, renamed_from = resolve_output_dir(
        spec, root=root, out=out, resume=resume, now=now
    )
    directory.mkdir(parents=True, exist_ok=True)
    spec_file = _place_spec(spec, directory)

    runs_path = directory / RUNS_CSV
    steps_path = directory / STEPS_CSV

    all_runs = spec.runs()
    already_done: set[int] = set()
    if resume:
        already_done = _completed_run_ids(runs_path)
    pending = [r for r in all_runs if r.run_id not in already_done]

    manifest_path = directory / MANIFEST_NAME
    if resume and manifest_path.exists():
        manifest = read_manifest(directory)
        manifest["status"] = "running"
    else:
        manifest = build_manifest(
            spec,
            output_dir=directory,
            jobs=jobs,
            renamed_from=renamed_from,
            spec_file=spec_file,
        )
    write_manifest(directory, manifest)

    if progress:
        _log(
            f"{spec.expname}: {len(pending)} run(s) to execute "
            f"({spec.condition_count} conditions x {spec.repetitions} reps"
            + (f", {len(already_done)} already done" if already_done else "")
            + f") on {jobs} process(es)"
        )
        _log(f"  -> {directory}")

    run_columns = (
        ["run_id", "condition_index", "repetition", "seed"]
        + list(spec.sweep_names)
        + list(spec.metrics)
    )
    step_columns = ["run_id"] + list(ElectionRecord.field_names())

    append_runs = resume and runs_path.exists()
    append_steps = resume and steps_path.exists()

    completed = len(already_done)
    started = time.monotonic()
    status = "complete"
    error: str | None = None

    runs_file = open(runs_path, "a" if append_runs else "w", newline="", encoding="utf-8")
    steps_file = None
    if spec.run_metrics_every_step:
        steps_file = open(
            steps_path, "a" if append_steps else "w", newline="", encoding="utf-8"
        )

    try:
        runs_writer = csv.DictWriter(runs_file, fieldnames=run_columns)
        if not append_runs:
            runs_writer.writeheader()

        steps_writer = None
        if steps_file is not None:
            steps_writer = csv.DictWriter(steps_file, fieldnames=step_columns)
            if not append_steps:
                steps_writer.writeheader()

        for row, step_rows in _execute_all(pending, spec, jobs):
            runs_writer.writerow(row)
            if steps_writer is not None:
                steps_writer.writerows(step_rows)
            completed += 1
            if progress:
                _report(completed, len(all_runs), started)

        runs_file.flush()
        if steps_file is not None:
            steps_file.flush()
    except KeyboardInterrupt:
        status = "interrupted"
        error = "KeyboardInterrupt"
        if progress:
            _log("\ninterrupted; partial results and manifest kept")
    except Exception as exc:  # pragma: no cover - surfaced to the caller
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        runs_file.close()
        if steps_file is not None:
            steps_file.close()
        elapsed = time.monotonic() - started
        manifest = finalize_manifest(
            directory,
            runs_completed=completed,
            wall_seconds=elapsed,
            status=status,
            error=error,
        )

    if progress:
        if sys.stderr.isatty():
            sys.stderr.write("\n")
        _log(
            f"{spec.expname}: {completed}/{len(all_runs)} runs in {elapsed:.1f}s "
            f"-> {runs_path}"
        )

    return manifest


def _execute_all(
    runs: Iterable[Run], spec: ExperimentSpec, jobs: int
) -> Iterator[tuple[dict[str, Any], list[dict[str, Any]]]]:
    runs = list(runs)
    if not runs:
        return
    jobs_iter = (
        (run, spec.steps, spec.metrics, spec.run_metrics_every_step) for run in runs
    )

    if jobs == 1:
        for job in jobs_iter:
            yield _worker(job)
        return

    chunksize = max(1, len(runs) // (jobs * 8))
    with ProcessPoolExecutor(max_workers=jobs) as executor:
        yield from executor.map(_worker, jobs_iter, chunksize=chunksize)


def _log(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


def _report(completed: int, total: int, started: float) -> None:
    """Progress to stderr: a redrawn line on a terminal, periodic lines otherwise.

    Without the second mode, redirecting stderr to a file produces one enormous
    line of carriage returns instead of a log.
    """
    interactive = sys.stderr.isatty()
    if not interactive:
        step = max(1, total // 10)
        if completed % step and completed != total:
            return

    elapsed = time.monotonic() - started
    rate = completed / elapsed if elapsed > 0 else 0.0
    remaining = (total - completed) / rate if rate > 0 else 0.0
    line = (
        f"  {completed}/{total} runs  ({100.0 * completed / total:5.1f}%)  "
        f"{rate:6.1f} runs/s  eta {remaining:5.1f}s"
    )
    sys.stderr.write(f"\r{line}   " if interactive else f"{line}\n")
    sys.stderr.flush()
