"""Generic figures for any experiment this repository produces.

Nothing here knows about a particular sweep.  Point it at an experiment folder
and it draws the same four figures: where the parties are against where the
voters are, how the competition went, whether either converged, and the first of
those repeated across the sweep's conditions.

    python -m generic_analyses experiments/<stamp>_<name>

The dynamics come from ``steps.csv``, which the jig writes only when the spec
sets ``run_metrics_every_step = true``.
"""

from .dynamics import Condition, Experiment, MissingSteps, load
from .figures import (
    competition,
    convergence,
    political_space,
    space_by_condition,
    write_all,
)
from .theme import Theme, apply, get_theme

__all__ = [
    "Condition",
    "Experiment",
    "MissingSteps",
    "Theme",
    "apply",
    "competition",
    "convergence",
    "get_theme",
    "load",
    "political_space",
    "space_by_condition",
    "write_all",
]
