"""Voter decision rules.

A rule is a small, independent reason to prefer a party or to bother voting at
all.  Rules do not decide anything on their own: each returns a
:class:`Contribution` -- an ``(n_voters, n_parties)`` utility surface, a
``(n_voters,)`` turnout term, or both -- and a *combiner* in
:mod:`polimods.general.decision` turns the accumulated contributions into an
actual ballot.

Splitting it this way is what makes the four axes compose.  A rule is written
once against ``n_parties`` columns and a ``d``-dimensional space, so it works
unchanged whether there are two parties on a line or six in a five-issue space;
and because combination is somebody else's job, the same rule set can be read as
a weighted sum, as a count of discrete reasons, or as a random-utility model.

Adding a rule means writing one class and decorating it with ``@rule``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar

import numpy as np

from .state import ABSTAIN, Electorate, PartySystem


@dataclass
class Contribution:
    """What one rule contributes to one election.

    ``utility`` is added to every voter's score for each party.  ``turnout`` is
    added to each voter's turnout score, which the decision model turns into a
    probability.  Either may be ``None`` when a rule speaks only to one of them.
    """

    utility: np.ndarray | None = None
    turnout: np.ndarray | None = None


@dataclass
class Context:
    """Everything a rule is allowed to look at."""

    electorate: Electorate
    parties: PartySystem
    distances: np.ndarray  # (n_voters, n_parties)
    network: Any
    rng: np.random.Generator
    election: int
    incumbent: int | None = None
    #: Parties still in contention, e.g. the top two in a runoff round.
    contenders: np.ndarray | None = None

    @property
    def n(self) -> int:
        return len(self.electorate)

    @property
    def p(self) -> int:
        return len(self.parties)

    def zeros(self) -> np.ndarray:
        return np.zeros((self.n, self.p))


RULES: dict[str, type["Rule"]] = {}


def rule(cls: type["Rule"]) -> type["Rule"]:
    """Register a rule class under its ``name`` so configs can refer to it."""
    if not getattr(cls, "name", None):
        raise ValueError(f"{cls.__name__} needs a name")
    if cls.name in RULES:
        raise ValueError(f"duplicate rule name: {cls.name}")
    RULES[cls.name] = cls
    return cls


@dataclass
class Rule:
    """Base class: a named, weighted, independently switchable reason."""

    name: ClassVar[str] = ""
    #: ``"choice"`` rules run first and build the utility surface.  ``"turnout"``
    #: rules run afterwards and may therefore read the *aggregated* utility, which
    #: is what lets a rule like "vote only if you care" be written at all.
    phase: ClassVar[str] = "choice"
    #: Scales this rule's utility contribution when scores are summed.
    weight: float = 1.0
    #: How large a lead this rule must give a party before the production-style
    #: combiner counts it as a discrete reason.  Ignored by the other combiners.
    threshold: float = 0.0

    def contribute(self, ctx: Context) -> Contribution:  # pragma: no cover - abstract
        raise NotImplementedError

    def describe(self) -> str:
        return self.name


def build_rule(spec: str | dict[str, Any]) -> Rule:
    """Construct a rule from ``"proximity"`` or ``{"rule": "proximity", "weight": 2}``."""
    if isinstance(spec, str):
        spec = {"rule": spec}
    spec = dict(spec)
    name = spec.pop("rule", None) or spec.pop("name", None)
    if name is None:
        raise ValueError(f"rule spec needs a 'rule' key: {spec}")
    if name not in RULES:
        raise ValueError(f"unknown rule {name!r}. Available: {', '.join(sorted(RULES))}")
    try:
        return RULES[name](**spec)
    except TypeError as error:
        raise ValueError(f"bad options for rule {name!r}: {error}") from None


def build_rules(specs) -> list[Rule]:
    return [build_rule(spec) for spec in (specs or [])]


# -- party-choice rules -------------------------------------------------------


@rule
@dataclass
class Proximity(Rule):
    """Prefer the party whose platform is nearest in issue space.

    Utility is the negated salience-weighted distance, so it generalizes the
    two-party model's ``|I - B| - |I - R|``: with two parties, differences in
    this utility reproduce that expression exactly.
    """

    name: ClassVar[str] = "proximity"
    threshold: float = 0.15

    def contribute(self, ctx: Context) -> Contribution:
        return Contribution(utility=-self.weight * ctx.distances)


@rule
@dataclass
class Identity(Rule):
    """Prefer the party you already feel attached to.

    Attachment is a full ``(n_voters, n_parties)`` matrix here, so a voter can be
    warm toward several parties at once -- something a single signed number on a
    two-party line cannot express.
    """

    name: ClassVar[str] = "identity"
    strength: float = 0.6
    threshold: float = 0.25

    def contribute(self, ctx: Context) -> Contribution:
        return Contribution(utility=self.weight * self.strength * ctx.electorate.identity)


@rule
@dataclass
class Habit(Rule):
    """Do what you did last time."""

    name: ClassVar[str] = "habit"
    strength: float = 1.0
    threshold: float = 0.5

    def contribute(self, ctx: Context) -> Contribution:
        utility = ctx.zeros()
        previous = ctx.electorate.last_vote
        returning = previous != ABSTAIN
        utility[returning, previous[returning]] = self.weight * self.strength
        return Contribution(utility=utility)


@rule
@dataclass
class SocialConformity(Rule):
    """Prefer whatever your politically active neighbours chose last time."""

    name: ClassVar[str] = "social"
    strength: float = 1.0
    threshold: float = 0.1

    def contribute(self, ctx: Context) -> Contribution:
        network = ctx.network
        if network is None or not len(network):
            return Contribution()

        previous = ctx.electorate.last_vote
        active = (previous != ABSTAIN).astype(float)
        active_neighbours = network.neighbor_sum(active)
        has_active = active_neighbours > 0

        utility = ctx.zeros()
        for party in range(ctx.p):
            backing = network.neighbor_sum((previous == party).astype(float))
            share = np.zeros(ctx.n)
            np.divide(backing, active_neighbours, out=share, where=has_active)
            utility[:, party] = share
        return Contribution(utility=self.weight * self.strength * utility)


@rule
@dataclass
class Incumbency(Rule):
    """Reward -- or punish -- whoever is currently in government.

    A negative ``bonus`` makes this a cost-of-ruling rule, which is the more
    commonly observed pattern and is unavailable in the two-party model because
    it has no notion of who governs between elections.
    """

    name: ClassVar[str] = "incumbency"
    bonus: float = 0.1
    threshold: float = 0.05

    def contribute(self, ctx: Context) -> Contribution:
        if ctx.incumbent is None or not 0 <= ctx.incumbent < ctx.p:
            return Contribution()
        utility = ctx.zeros()
        utility[:, ctx.incumbent] = self.weight * self.bonus
        return Contribution(utility=utility)


@rule
@dataclass
class Valence(Rule):
    """A shared, position-free judgement of party quality that varies by election.

    Every voter sees the same draw, so this shifts the whole electorate at once:
    scandals and good campaigns, as against the idiosyncratic noise below.
    """

    name: ClassVar[str] = "valence"
    scale: float = 0.1
    persistence: float = 0.0
    threshold: float = 0.05

    def contribute(self, ctx: Context) -> Contribution:
        if self.scale <= 0:
            return Contribution()
        draw = ctx.rng.normal(0.0, self.scale, size=ctx.p)

        if self.persistence > 0:
            # Carry part of last election's valence forward, so quality shocks
            # decay rather than being independent across elections.
            for index, party in enumerate(ctx.parties):
                previous = party.memory.get("valence", 0.0)
                draw[index] += self.persistence * previous
                party.memory["valence"] = float(draw[index])

        return Contribution(utility=self.weight * np.broadcast_to(draw, (ctx.n, ctx.p)))


@rule
@dataclass
class IdiosyncraticNoise(Rule):
    """An independent shock per voter and party.

    The generalization of the two-party model's ``election-noise``: with two
    parties, the difference between two independent normal draws is itself
    normal, so this reproduces a single shock on the choice score.
    """

    name: ClassVar[str] = "noise"
    scale: float = 0.08

    def contribute(self, ctx: Context) -> Contribution:
        if self.scale <= 0:
            return Contribution()
        return Contribution(utility=ctx.rng.normal(0.0, self.scale, size=(ctx.n, ctx.p)))


# -- turnout rules ------------------------------------------------------------


def _top_two_gap(utility: np.ndarray) -> np.ndarray:
    """How much better the best party is than the runner-up, per voter."""
    if utility.shape[1] < 2:
        return np.zeros(len(utility))
    top = np.partition(utility, -2, axis=1)[:, -2:]
    return top[:, 1] - top[:, 0]


@rule
@dataclass
class PreferenceIntensity(Rule):
    """Vote more readily the more you prefer your favourite to the runner-up.

    This is the continuous turnout term from the two-party model, restated for
    an arbitrary number of parties: there, ``|choice_score|`` *was* the gap
    between the two available options.
    """

    name: ClassVar[str] = "intensity"
    phase: ClassVar[str] = "turnout"
    scale: float = 1.0

    def contribute(self, ctx: Context) -> Contribution:
        return Contribution(turnout=self.weight * self.scale * _top_two_gap(ctx.electorate.utility))


@rule
@dataclass
class Engagement(Rule):
    """Turn out when some party is clearly worth turning out for."""

    name: ClassVar[str] = "engagement"
    phase: ClassVar[str] = "turnout"
    gap: float = 0.35

    def contribute(self, ctx: Context) -> Contribution:
        engaged = _top_two_gap(ctx.electorate.utility) >= self.gap
        return Contribution(turnout=self.weight * engaged.astype(float))


@rule
@dataclass
class Indifference(Rule):
    """Stay home when the leading parties are hard to tell apart."""

    name: ClassVar[str] = "indifference"
    phase: ClassVar[str] = "turnout"
    gap: float = 0.15

    def contribute(self, ctx: Context) -> Contribution:
        torn = _top_two_gap(ctx.electorate.utility) <= self.gap
        return Contribution(turnout=-self.weight * torn.astype(float))


@rule
@dataclass
class Alienation(Rule):
    """Stay home when even the nearest party is far away."""

    name: ClassVar[str] = "alienation"
    phase: ClassVar[str] = "turnout"
    distance: float = 0.55

    def contribute(self, ctx: Context) -> Contribution:
        if ctx.p == 0:
            return Contribution()
        nearest = ctx.distances.min(axis=1)
        return Contribution(turnout=-self.weight * (nearest >= self.distance).astype(float))


@rule
@dataclass
class CrossPressure(Rule):
    """Stay home when proximity and loyalty point at different parties.

    With more than two parties this is a strictly richer condition than the
    two-party version, which could only detect a straight left-right conflict.
    """

    name: ClassVar[str] = "cross_pressure"
    phase: ClassVar[str] = "turnout"
    identity_floor: float = 0.25

    def contribute(self, ctx: Context) -> Contribution:
        if ctx.p < 2:
            return Contribution()
        identity = ctx.electorate.identity
        nearest = np.argmin(ctx.distances, axis=1)
        dearest = np.argmax(identity, axis=1)
        committed = identity.max(axis=1) >= self.identity_floor
        conflicted = committed & (nearest != dearest)
        return Contribution(turnout=-self.weight * conflicted.astype(float))


@rule
@dataclass
class CivicDuty(Rule):
    """A flat, unconditional propensity to vote, independent of the parties."""

    name: ClassVar[str] = "duty"
    phase: ClassVar[str] = "turnout"
    amount: float = 1.0

    def contribute(self, ctx: Context) -> Contribution:
        return Contribution(turnout=np.full(ctx.n, self.weight * self.amount))


#: The rule set that reproduces the two-party model's continuous voter, and the
#: one that reproduces its production system.  Useful as configuration starting
#: points rather than as claims of exact equivalence.
WEIGHTED_RULES = ("proximity", "identity", "noise", "intensity")
PRODUCTION_RULES = (
    "proximity",
    "identity",
    "habit",
    "social",
    "engagement",
    "indifference",
    "alienation",
    "cross_pressure",
)
