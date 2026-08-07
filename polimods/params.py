"""Model parameters, transcribed from the NetLogo interface widgets.

Every field below corresponds to a slider, switch, or chooser in
``adaptive_two_party_model_production_rules.nlogo``.  Defaults, minima, maxima,
and step sizes are taken verbatim from that file's widget section so the Python
model starts in the same state as the NetLogo model does after SETUP.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any

ELECTORATE_SHAPES = ("single-peaked", "two-camp")

#: Slider ranges from the NetLogo widget section: name -> (minimum, maximum, step).
#: The jig validates swept values against this table, which is what stops a typo in
#: an experiment spec from producing runs NetLogo itself could never have produced.
BOUNDS: dict[str, tuple[float, float, float]] = {
    "population": (50, 2000, 50),
    "initial_party_gap": (0.1, 1.8, 0.05),
    "ideology_spread": (0.02, 0.8, 0.01),
    "party_adaptation": (0.0, 1.0, 0.01),
    "electorate_polarization": (0.0, 0.9, 0.01),
    "base_pressure": (0.0, 1.0, 0.01),
    "identity_noise": (0.0, 1.0, 0.01),
    "persuadable_band": (0.01, 1.0, 0.01),
    "identity_strength": (0.0, 2.0, 0.02),
    "winner_base_adaptation": (0.0, 0.5, 0.01),
    "identity_reinforcement": (0.0, 0.25, 0.005),
    "base_turnout": (0.0, 1.0, 0.01),
    "turnout_sensitivity": (0.0, 0.5, 0.01),
    "election_noise": (0.0, 0.5, 0.01),
    "network_degree": (0, 20, 1),
    "homophily": (0.0, 1.0, 0.01),
    "social_influence": (0.0, 0.5, 0.01),
    "opinion_drift": (0.0, 0.1, 0.002),
}


@dataclass(frozen=True)
class Params:
    """One complete parameterization of the model.

    Defaults reproduce ``adaptive_two_party_model.nlogo`` -- the model the README
    documents -- which means ``production_system`` is off.  The production-rules
    interface ships with that switch ON; use :meth:`production_rules_defaults` for
    that preset.
    """

    # -- electorate construction -------------------------------------------------
    electorate_shape: str = "single-peaked"
    population: int = 500
    ideology_spread: float = 0.25
    electorate_polarization: float = 0.35
    identity_noise: float = 0.35

    # -- party construction and adaptation ---------------------------------------
    initial_party_gap: float = 1.0
    adaptive_parties: bool = True
    party_adaptation: float = 0.25
    persuadable_band: float = 0.25
    base_pressure: float = 0.15
    winner_base_adaptation: float = 0.03

    # -- vote choice, identity, turnout ------------------------------------------
    identity_strength: float = 0.6
    identity_reinforcement: float = 0.03
    base_turnout: float = 0.55
    turnout_sensitivity: float = 0.12
    election_noise: float = 0.08

    # -- network and opinion change ----------------------------------------------
    social_network: bool = False
    network_degree: int = 6
    homophily: float = 0.7
    social_influence: float = 0.08
    opinion_drift: float = 0.01

    # -- voter production system -------------------------------------------------
    production_system: bool = False
    rule_policy: bool = True
    rule_identity: bool = True
    rule_habit: bool = True
    rule_neighbors: bool = True
    rule_engagement: bool = True
    rule_indifference: bool = True
    rule_alienation: bool = True
    rule_cross_pressure: bool = True

    @classmethod
    def production_rules_defaults(cls, **overrides: Any) -> "Params":
        """The defaults shown by the production-rules interface (switch ON)."""
        return cls(production_system=True, **overrides)

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        return tuple(f.name for f in fields(cls))

    def replace(self, **changes: Any) -> "Params":
        return replace(self, **changes)

    def as_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def validate(self) -> "Params":
        """Reject values a NetLogo slider or chooser could not have produced.

        Returns ``self`` so it can be used inline.  Raises :class:`ValueError` with
        the offending field named, because a sweep of 300 runs should fail before
        the first one starts rather than halfway through.
        """
        if self.electorate_shape not in ELECTORATE_SHAPES:
            raise ValueError(
                f"electorate_shape must be one of {ELECTORATE_SHAPES}, "
                f"got {self.electorate_shape!r}"
            )

        for name, (low, high, _step) in BOUNDS.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be numeric, got {value!r}")
            if not low <= value <= high:
                raise ValueError(
                    f"{name} must be in [{low}, {high}] (NetLogo slider range), "
                    f"got {value}"
                )

        for name in ("population", "network_degree"):
            value = getattr(self, name)
            if int(value) != value:
                raise ValueError(f"{name} must be a whole number, got {value}")

        for f in fields(self):
            if f.type == "bool" and not isinstance(getattr(self, f.name), bool):
                raise ValueError(
                    f"{f.name} must be a boolean, got {getattr(self, f.name)!r}"
                )

        return self


#: The NetLogo defaults, for manifests and docs that want to report what a given
#: experiment changed relative to a fresh copy of the model.
NETLOGO_DEFAULTS = Params().as_dict()
