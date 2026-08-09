"""Draw the generic figures for an experiment folder.

    python -m generic_analyses experiments/202608081246_dynamics_demo
    python -m generic_analyses <folder> --condition 3 --theme dark
    python -m generic_analyses <folder> --all

Figures are written into the experiment folder by default, next to the spec and
the manifest that produced them.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .dynamics import MissingSteps, load
from .figures import MAX_FACETS, space_by_condition, write_all
from .theme import apply, get_theme


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m generic_analyses",
        description="Plot the dynamics of an experiment: parties, voters, competition.",
    )
    parser.add_argument("experiment", type=Path, help="an experiment folder")
    parser.add_argument(
        "--condition",
        type=int,
        help="condition index to plot (default: the first; see --list)",
    )
    parser.add_argument(
        "--all", action="store_true", help="write one set of figures per condition"
    )
    parser.add_argument("--theme", choices=("light", "dark"), default="light")
    parser.add_argument("--out", type=Path, help="where to write (default: the folder)")
    parser.add_argument(
        "--list", action="store_true", help="list the conditions and exit"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        experiment = load(args.experiment)
    except (MissingSteps, FileNotFoundError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if not experiment.conditions:
        print("error: no runs found in that folder", file=sys.stderr)
        return 2

    if args.list:
        print(f"{experiment.name}: {len(experiment.conditions)} condition(s)")
        for condition in experiment.conditions:
            print(f"  {condition.index:>3}  {condition.runs:>3} runs  {condition.label}")
        return 0

    theme = get_theme(args.theme)
    apply(theme)
    out = args.out or experiment.directory
    suffix = "" if theme.name == "light" else f"_{theme.name}"

    if args.all:
        chosen = experiment.conditions
    elif args.condition is not None:
        chosen = [experiment.condition(args.condition)]
    else:
        chosen = [experiment.conditions[0]]
        if len(experiment.conditions) > 1:
            print(
                f"plotting condition {chosen[0].index} of {len(experiment.conditions)} "
                f"({chosen[0].label}); --condition N or --all for the rest"
            )

    written = []
    for condition in chosen:
        tag = f"_c{condition.index}" if len(chosen) > 1 else ""
        written += write_all(experiment, condition, theme, out, suffix=f"{tag}{suffix}")

    if len(experiment.conditions) > 1:
        figure = space_by_condition(experiment, theme)
        path = out / f"space_by_condition{suffix}.png"
        figure.savefig(path, bbox_inches="tight")
        written.append(path)
        if len(experiment.conditions) > MAX_FACETS:
            print(
                f"note: {path.name} shows the first {MAX_FACETS} of "
                f"{len(experiment.conditions)} conditions; the rest are not drawn"
            )

    for path in written:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
