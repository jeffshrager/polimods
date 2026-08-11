"""
================================================================================
 TEACHING -- a heavily-commented copy of polimods/, for reading and learning
================================================================================
This package is a line-for-line copy of the core simulation code in
`polimods/` (model.py, network.py, params.py, rules.py, history.py), with
extensive block and inline comments added throughout to explain not just
*what* each piece of code does but *why* it's written that way.

It is NOT a fork with different behaviour -- the logic here is identical to
the original. This exists purely as a companion reading copy: open these
files side by side with the originals (or instead of them) when you want to
understand the model rather than modify it. If you're changing the model
itself, change `polimods/`, not this copy -- this package is not kept in
sync automatically.

SUGGESTED READING ORDER:

  1. params.py   -- the vocabulary: every input the model accepts, and what
                     each one means. Nothing here simulates anything; skim
                     it to learn the knobs, then refer back as needed.
  2. network.py  -- how voters get linked into a social network, and the
                     numpy tricks used to compute neighbour averages fast.
  3. rules.py    -- one of the two theories of how a single voter decides:
                     eight independent IF-THEN rules, reasons counted rather
                     than weighted.
  4. model.py    -- the simulation loop itself: setup, then one election
                     after another (vote -> parties adapt -> voters update
                     -> stats logged). This is where params.py, network.py,
                     and rules.py all get called in the right order, and
                     where the *other* vote-choice theory (a single
                     continuous weighted equation) lives, for comparison
                     against rules.py's discrete one.
  5. history.py  -- the per-election logbook and its NetLogo-compatible
                     export format; read this last, it's pure bookkeeping.

    >>> from teaching import Model, Params
    >>> m = Model(Params(population=500), seed=1).run(100)
    >>> round(m.mean_margin, 1) > 0
    True
================================================================================
"""

from .history import ElectionRecord, History
from .model import Model, clamp_value
from .network import Network, build_network
from .params import BOUNDS, ELECTORATE_SHAPES, NETLOGO_DEFAULTS, Params
from .rules import RULE_NAMES, Decision, run_production_system

__all__ = [
    "BOUNDS",
    "Decision",
    "ELECTORATE_SHAPES",
    "ElectionRecord",
    "History",
    "Model",
    "NETLOGO_DEFAULTS",
    "Network",
    "Params",
    "RULE_NAMES",
    "build_network",
    "clamp_value",
    "run_production_system",
]
