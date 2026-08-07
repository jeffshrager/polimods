"""Single-run command line interface.

Equivalent to pressing SETUP and then clicking ONE ELECTION ``--steps`` times:

    python -m polimods --steps 100 --seed 1 --export history.tsv
    python -m polimods --production-system --no-rule-habit --steps 50
"""

from __future__ import annotations

import argparse
import dataclasses
import sys

from .model import Model
from .params import BOUNDS, ELECTORATE_SHAPES, Params


def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m polimods",
        description="Run the adaptive two-party competition model once.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--steps", type=int, default=100, help="number of elections")
    parser.add_argument("--seed", type=int, default=None, help="random seed")
    parser.add_argument("--export", metavar="PATH", help="write history as TSV")
    parser.add_argument(
        "--quiet", action="store_true", help="suppress the per-election table"
    )

    model = parser.add_argument_group("model parameters (NetLogo interface)")
    for field in dataclasses.fields(Params):
        default = getattr(Params(), field.name)
        if field.name == "electorate_shape":
            model.add_argument(
                _flag(field.name),
                choices=ELECTORATE_SHAPES,
                default=default,
            )
        elif field.type == "bool":
            model.add_argument(
                _flag(field.name),
                action=argparse.BooleanOptionalAction,
                default=default,
            )
        else:
            kind = int if field.type == "int" else float
            low, high, _step = BOUNDS.get(field.name, (None, None, None))
            hint = f"[{low}, {high}]" if low is not None else None
            model.add_argument(
                _flag(field.name), type=kind, default=default, help=hint
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    names = [f.name for f in dataclasses.fields(Params)]
    try:
        params = Params(**{name: getattr(args, name) for name in names}).validate()
    except ValueError as error:
        parser.error(str(error))

    model = Model(params, seed=args.seed)
    model.run(args.steps)

    if not args.quiet:
        for line in model.history.to_lines():
            print(line)

    if args.export:
        written = model.history.export_tsv(args.export)
        print(f"Saved {written} elections to {args.export}", file=sys.stderr)

    summary = (
        f"mean margin {model.mean_margin:.2f} pts | "
        f"control changes {model.party_control_changes} "
        f"({model.control_change_rate:.1f}%) | "
        f"party gap {model.party_gap:.3f} "
        f"(Blue {model.blue_position:+.3f}, Red {model.red_position:+.3f}) | "
        f"turnout {model.turnout_rate:.1f}%"
    )
    print(summary, file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
