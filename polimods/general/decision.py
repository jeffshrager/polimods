"""Turning rule contributions into ballots.

The rules say what matters; a combiner says how to put those things together.
Keeping the two apart is what lets one rule set be read three different ways:

``weighted``
    Add the contributions up and take the best party.  Voters trade off freely --
    a big advantage on one rule can outweigh small deficits on several others.

``production``
    Each rule casts a discrete vote of its own, and the party with the most
    reasons wins.  Voters no longer trade off: a rule either fires or it does
    not, and a rule that fires strongly counts no more than one that barely
    fires.

``logit``
    Add the contributions up, then choose *probabilistically* in proportion to
    the exponentiated scores.  Voters are noisy maximizers, and ``temperature``
    controls how noisy.  As temperature approaches zero this becomes ``weighted``.

Turnout works the same way under all three: a base rate plus the sum of whatever
the turnout rules had to say, scaled by one sensitivity parameter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .rules import Context, Rule, build_rules
from .state import ABSTAIN

COMBINERS = ("weighted", "production", "logit")

#: Score penalty applied to a party that has been eliminated from a round.
ELIMINATED = 1e6


@dataclass
class DecisionOutcome:
    """One election's worth of voter deliberation."""

    utility: np.ndarray  # (n, p) -- reason counts under the production combiner
    preference: np.ndarray  # (n,) the party each voter would choose
    turnout_score: np.ndarray  # (n,)
    turnout_probability: np.ndarray  # (n,)
    voted: np.ndarray  # (n,) bool
    vote: np.ndarray  # (n,) party index or ABSTAIN
    reasons: np.ndarray | None = None


def argmax_with_random_ties(values: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Row-wise argmax, breaking exact ties uniformly rather than by column order.

    Column order is arbitrary -- it is just the order parties happen to sit in --
    so letting ``np.argmax`` resolve ties would hand a systematic advantage to
    whichever party was created first.
    """
    if values.shape[1] == 0:
        return np.full(len(values), ABSTAIN, dtype=np.int64)
    tied = values == values.max(axis=1, keepdims=True)
    return (rng.random(values.shape) * tied).argmax(axis=1).astype(np.int64)


def softmax_sample(
    values: np.ndarray, temperature: float, rng: np.random.Generator
) -> np.ndarray:
    """Sample a column per row with probability proportional to ``exp(value / T)``."""
    if values.shape[1] == 0:
        return np.full(len(values), ABSTAIN, dtype=np.int64)
    if temperature <= 0:
        return argmax_with_random_ties(values, rng)

    scaled = values / temperature
    scaled = scaled - scaled.max(axis=1, keepdims=True)  # overflow guard
    weights = np.exp(scaled)
    cumulative = np.cumsum(weights, axis=1)
    draws = rng.random((len(values), 1)) * cumulative[:, -1:]
    return np.clip((draws > cumulative).sum(axis=1), 0, values.shape[1] - 1).astype(np.int64)


def discrete_reasons(utility: np.ndarray, threshold: float) -> np.ndarray:
    """One reason for the leading party, if it leads by at least ``threshold``.

    The generalization of the two-party production rules, where "Blue is
    substantially closer" meant a policy advantage past a cutoff.  With more than
    two parties the comparison that matters is still the leader against the
    runner-up.
    """
    reasons = np.zeros_like(utility)
    if utility.shape[1] < 2:
        return reasons

    top = np.partition(utility, -2, axis=1)[:, -2:]
    leads = (top[:, 1] - top[:, 0]) >= threshold
    if not leads.any():
        return reasons

    leader = utility.argmax(axis=1)
    reasons[leads, leader[leads]] = 1.0
    return reasons


@dataclass
class DecisionModel:
    """How a voter gets from a pile of rules to a ballot."""

    rules: list[Rule] = field(default_factory=list)
    combiner: str = "weighted"
    base_turnout: float = 0.55
    turnout_sensitivity: float = 0.12
    temperature: float = 0.1

    def __post_init__(self) -> None:
        if self.combiner not in COMBINERS:
            raise ValueError(
                f"combiner must be one of {COMBINERS}, got {self.combiner!r}"
            )
        self.rules = [r if isinstance(r, Rule) else build_rules([r])[0] for r in self.rules]

    @property
    def choice_rules(self) -> list[Rule]:
        return [r for r in self.rules if r.phase == "choice"]

    @property
    def turnout_rules(self) -> list[Rule]:
        return [r for r in self.rules if r.phase == "turnout"]

    def decide(self, ctx: Context, contenders: np.ndarray | None = None) -> DecisionOutcome:
        n, p = ctx.n, ctx.p
        if p == 0:
            empty = np.zeros((n, 0))
            return DecisionOutcome(
                utility=empty,
                preference=np.full(n, ABSTAIN, dtype=np.int64),
                turnout_score=np.zeros(n),
                turnout_probability=np.zeros(n),
                voted=np.zeros(n, dtype=bool),
                vote=np.full(n, ABSTAIN, dtype=np.int64),
            )

        # Phase one: build the utility surface.
        totals = np.zeros((n, p))
        reasons = np.zeros((n, p))
        for rule in self.choice_rules:
            contribution = rule.contribute(ctx)
            if contribution.utility is None:
                continue
            totals += contribution.utility
            if self.combiner == "production":
                reasons += discrete_reasons(contribution.utility, rule.threshold)

        scores = reasons if self.combiner == "production" else totals

        # A runoff restricts the field without re-running the rules: an eliminated
        # party simply cannot be chosen.  The penalty is large but finite, so that
        # the turnout rules below still see a well-defined gap between the
        # surviving contenders rather than a difference of infinities.
        if contenders is not None:
            excluded = np.ones(p, dtype=bool)
            excluded[contenders] = False
            scores = np.where(excluded[None, :], -ELIMINATED, scores)

        if self.combiner == "logit":
            preference = softmax_sample(scores, self.temperature, ctx.rng)
        else:
            preference = argmax_with_random_ties(scores, ctx.rng)

        # Phase two: turnout rules read the aggregated surface, so they run now.
        ctx.electorate.utility = scores
        turnout_score = np.zeros(n)
        for rule in self.turnout_rules:
            contribution = rule.contribute(ctx)
            if contribution.turnout is not None:
                turnout_score += contribution.turnout

        probability = np.clip(
            self.base_turnout + self.turnout_sensitivity * turnout_score, 0.0, 1.0
        )
        voted = ctx.rng.random(n) < probability
        vote = np.where(voted, preference, ABSTAIN).astype(np.int64)

        return DecisionOutcome(
            utility=totals,
            preference=preference,
            turnout_score=turnout_score,
            turnout_probability=probability,
            voted=voted,
            vote=vote,
            reasons=reasons if self.combiner == "production" else None,
        )

    def describe(self) -> str:
        names = ", ".join(rule.describe() for rule in self.rules)
        return f"{self.combiner}({names})"
