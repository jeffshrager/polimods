"""Command line interface for the experimental jig.

    python -m polimods.jig run experiments/parity_sweep.toml --jobs 12
    python -m polimods.jig run experiments/parity_sweep.toml --dry-run
    python -m polimods.jig summarize results/parity_sweep
    python -m polimods.jig summarize results/parity_sweep --plot mean_margin
    python -m polimods.jig list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .manifest import read_manifest
from .runner import DEFAULT_JOBS, default_results_root, resolve_output_dir, run_experiment
from .spec import ExperimentSpec, SpecError
from .summarize import format_table, plot, summarize


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m polimods.jig",
        description="Run and summarize parameter sweeps of the two-party model.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="execute an experiment spec")
    run.add_argument("spec", help="path to a .toml experiment spec")
    run.add_argument("--jobs", "-j", type=int, default=DEFAULT_JOBS)
    run.add_argument("--out", type=Path, help="explicit output directory")
    run.add_argument(
        "--results-root", type=Path, help="root for results/ (default: repo results/)"
    )
    run.add_argument(
        "--resume",
        action="store_true",
        help="reuse the existing folder and skip runs already in runs.csv",
    )
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="print the expanded grid and run count, then exit",
    )
    run.add_argument("--quiet", action="store_true", help="suppress progress output")

    show = sub.add_parser("summarize", help="aggregate a finished sweep")
    show.add_argument("target", help="results folder or manifest.json")
    show.add_argument("--by", nargs="+", help="group by these columns")
    show.add_argument("--metrics", nargs="+", help="restrict to these metrics")
    show.add_argument(
        "--show",
        choices=("mean", "sd", "ci"),
        default="ci",
        help="what to print in each cell",
    )
    show.add_argument("--plot", metavar="METRIC", help="also write a PNG for METRIC")
    show.add_argument("--plot-path", type=Path, help="where to write the PNG")

    listing = sub.add_parser("list", help="list available specs and past results")
    listing.add_argument(
        "--experiments", type=Path, help="experiments directory to scan"
    )
    listing.add_argument("--results-root", type=Path)

    return parser


def _dry_run(spec: ExperimentSpec, args) -> int:
    directory, renamed_from = resolve_output_dir(
        spec, results_root=args.results_root, out=args.out, resume=args.resume
    )
    print(f"experiment      {spec.name}")
    if spec.description:
        print(f"description     {spec.description}")
    print(f"steps           {spec.steps}")
    print(f"repetitions     {spec.repetitions}")
    print(f"conditions      {spec.condition_count}")
    print(f"total runs      {spec.total_runs}")
    print(f"base seed       {spec.base_seed}")
    print(f"metrics         {', '.join(spec.metrics)}")
    print(f"output          {directory}")
    if renamed_from:
        print(f"                (a folder already exists at {renamed_from})")
    print("\nsweep")
    for sweep in spec.sweeps:
        values = ", ".join(str(v) for v in sweep.values)
        print(f"  {sweep.name:<24} {sweep.n:>3} value(s): {values}")
    if spec.constants:
        print("\nconstants")
        for key, value in sorted(spec.constants.items()):
            print(f"  {key:<24} {value}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        try:
            spec = ExperimentSpec.from_file(args.spec)
        except SpecError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2

        if args.dry_run:
            return _dry_run(spec, args)

        run_experiment(
            spec,
            jobs=args.jobs,
            results_root=args.results_root,
            out=args.out,
            resume=args.resume,
            progress=not args.quiet,
        )
        return 0

    if args.command == "summarize":
        summary = summarize(args.target, by=args.by, metrics=args.metrics)
        print(format_table(summary, show=args.show))
        if args.plot:
            if args.plot not in summary.metrics:
                print(
                    f"error: {args.plot} is not a recorded metric "
                    f"({', '.join(summary.metrics)})",
                    file=sys.stderr,
                )
                return 2
            path = args.plot_path or summary.directory / f"{args.plot}.png"
            plot(summary, args.plot, path)
            print(f"\nwrote {path}")
        return 0

    if args.command == "list":
        return _list(args)

    return 1


def _list(args) -> int:
    repo = Path(__file__).resolve().parents[2]
    experiments = args.experiments or repo / "experiments"
    results = args.results_root or default_results_root()

    print("specs")
    if experiments.exists():
        for path in sorted(experiments.glob("*.toml")):
            try:
                spec = ExperimentSpec.from_file(path)
                print(f"  {path.name:<28} {spec.total_runs:>5} runs  {spec.description}")
            except SpecError as error:
                print(f"  {path.name:<28} !! {error}")
    else:
        print(f"  (no {experiments})")

    print("\nresults")
    if results.exists():
        for directory in sorted(p for p in results.iterdir() if p.is_dir()):
            manifest_path = directory / "manifest.json"
            if not manifest_path.exists():
                continue
            manifest = read_manifest(manifest_path)
            print(
                f"  {directory.name:<28} {manifest['runs_completed']}/"
                f"{manifest['total_runs']} runs  {manifest['status']}  "
                f"{manifest['created']}"
            )
    else:
        print(f"  (no {results})")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
