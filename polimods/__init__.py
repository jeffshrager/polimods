"""Adaptive two-party competition -- Python port of the NetLogo model.

A model of repeated electoral competition between two adaptive political parties.
One tick is one election.  See ``docs/PORTING.md`` for the NetLogo-to-Python
mapping and the list of deliberate deviations.

    >>> from polimods import Model, Params
    >>> m = Model(Params(population=500), seed=1).run(100)
    >>> round(m.mean_margin, 1) > 0
    True
"""

from .history import ElectionRecord, History
from .model import Model, clamp_value
from .network import Network, build_network
from .params import BOUNDS, ELECTORATE_SHAPES, NETLOGO_DEFAULTS, Params
from .rules import RULE_NAMES, Decision, run_production_system

__version__ = "1.0.0"

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
