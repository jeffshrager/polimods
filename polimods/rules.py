"""The voter production system: eight IF-THEN rules, vectorized.

Every voter runs the same rule set once per election.  The rules fire differently
because voters are in different states.  Unlike the weighted-choice equation, each
rule contributes a discrete *reason* rather than a continuous weight, and conflict
is resolved by counting reasons rather than by summing terms.

Port of ``run-production-system`` in
``adaptive_two_party_model_production_rules.nlogo``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .network import Network
from .params import Params

#: Activation thresholds, collected here exactly as NetLogo collects them at the
#: top of the procedure so they are easy to inspect and revise.
POLICY_THRESHOLD = 0.15
IDENTITY_THRESHOLD = 0.25
STRONG_POLICY_THRESHOLD = 0.35
STRONG_IDENTITY_THRESHOLD = 0.60
NEIGHBOR_MAJORITY_THRESHOLD = 0.60
ALIENATION_THRESHOLD = 0.55

#: The eight rules, in firing order.  Names match the ``rule_*`` fields of
#: :class:`~polimods.params.Params` minus the prefix.
RULE_NAMES = (
    "policy",
    "identity",
    "habit",
    "neighbors",
    "engagement",
    "indifference",
    "alienation",
    "cross_pressure",
)

#: The choice score a tie-broken voter receives.  It matters beyond bookkeeping:
#: party adaptation filters persuadable voters on ``abs(choice_score)``, and under
#: the production system these hairline values are the only scores that fall inside
#: a default ``persuadable_band`` of 0.25.
TIE_BREAK_SCORE = 0.001


@dataclass
class Decision:
    """The outcome of one election's worth of voter deliberation."""

    choice_score: np.ndarray
    intended_choice: np.ndarray
    turnout_probability: np.ndarray
    voted: np.ndarray
    vote_choice: np.ndarray
    blue_reasons: np.ndarray | None = None
    red_reasons: np.ndarray | None = None
    turnout_reasons: np.ndarray | None = None
    abstention_reasons: np.ndarray | None = None
    trace: list[str] | None = None


def run_production_system(
    *,
    params: Params,
    rng: np.random.Generator,
    ideology: np.ndarray,
    party_identity: np.ndarray,
    last_vote: np.ndarray,
    blue_position: float,
    red_position: float,
    network: Network,
    trace: bool = False,
) -> Decision:
    n = len(ideology)
    zeros = lambda: np.zeros(n, dtype=np.int64)  # noqa: E731

    blue_reasons = zeros()
    red_reasons = zeros()
    turnout_reasons = zeros()
    abstention_reasons = zeros()
    traces: list[list[str]] | None = [[] for _ in range(n)] if trace else None

    def note(mask: np.ndarray, label: str) -> None:
        if traces is None:
            return
        for i in np.flatnonzero(mask):
            traces[i].append(label)

    blue_distance = np.abs(ideology - blue_position)
    red_distance = np.abs(ideology - red_position)
    policy_advantage = blue_distance - red_distance
    effective_identity = params.identity_strength * party_identity

    # RULE 1: POLICY PROXIMITY
    # IF one party is substantially closer, THEN add a reason for that party.
    if params.rule_policy:
        favors_blue = policy_advantage < -POLICY_THRESHOLD
        favors_red = policy_advantage > POLICY_THRESHOLD
        blue_reasons += favors_blue
        red_reasons += favors_red
        note(favors_blue, "policy->Blue")
        note(favors_red, "policy->Red")

    # RULE 2: PARTISAN IDENTITY
    # IF partisan identity is sufficiently strong, THEN add a party reason.
    if params.rule_identity:
        favors_blue = effective_identity <= -IDENTITY_THRESHOLD
        favors_red = effective_identity >= IDENTITY_THRESHOLD
        blue_reasons += favors_blue
        red_reasons += favors_red
        note(favors_blue, "identity->Blue")
        note(favors_red, "identity->Red")

    # RULE 3: VOTING HABIT
    # IF the voter previously chose a party, THEN add a reason to repeat it.
    if params.rule_habit:
        was_blue = last_vote == -1
        was_red = last_vote == 1
        blue_reasons += was_blue
        red_reasons += was_red
        note(was_blue, "habit->Blue")
        note(was_red, "habit->Red")

    # RULE 4: SOCIAL MAJORITY
    # IF a clear majority of politically active neighbours previously chose one
    # party, THEN add a reason for that party.
    if params.rule_neighbors and params.social_network and len(network):
        active = last_vote != 0
        red_fraction, valid = network.neighbor_fraction(last_vote == 1, active)
        favors_blue = valid & (red_fraction <= 1 - NEIGHBOR_MAJORITY_THRESHOLD)
        favors_red = valid & (red_fraction >= NEIGHBOR_MAJORITY_THRESHOLD)
        blue_reasons += favors_blue
        red_reasons += favors_red
        note(favors_blue, "neighbors->Blue")
        note(favors_red, "neighbors->Red")

    # RULE 5: ENGAGEMENT
    # IF policy preference or identity is strong, THEN add a turnout reason.
    if params.rule_engagement:
        strong_policy = np.abs(policy_advantage) >= STRONG_POLICY_THRESHOLD
        strong_identity = np.abs(effective_identity) >= STRONG_IDENTITY_THRESHOLD
        turnout_reasons += strong_policy
        turnout_reasons += strong_identity
        note(strong_policy, "strong-policy->turnout")
        note(strong_identity, "strong-identity->turnout")

    # RULE 6: INDIFFERENCE
    # IF the parties are nearly equally attractive, THEN add an abstention reason.
    if params.rule_indifference:
        indifferent = np.abs(policy_advantage) <= POLICY_THRESHOLD
        abstention_reasons += indifferent
        note(indifferent, "indifference->abstain")

    # RULE 7: ALIENATION
    # IF even the nearer party is far away, THEN add an abstention reason.
    if params.rule_alienation:
        alienated = np.minimum(blue_distance, red_distance) >= ALIENATION_THRESHOLD
        abstention_reasons += alienated
        note(alienated, "alienation->abstain")

    # RULE 8: CROSS-PRESSURE
    # IF policy and identity clearly favour opposite parties, THEN add an
    # abstention reason.  This fires even when rules 1 and 2 are switched off,
    # because cross-pressure is itself an independent rule.
    if params.rule_cross_pressure:
        policy_direction = np.zeros(n, dtype=np.int64)
        policy_direction[policy_advantage < -POLICY_THRESHOLD] = -1
        policy_direction[policy_advantage > POLICY_THRESHOLD] = 1

        identity_direction = np.zeros(n, dtype=np.int64)
        identity_direction[effective_identity <= -IDENTITY_THRESHOLD] = -1
        identity_direction[effective_identity >= IDENTITY_THRESHOLD] = 1

        conflicted = (
            (policy_direction != 0)
            & (identity_direction != 0)
            & (policy_direction != identity_direction)
        )
        abstention_reasons += conflicted
        note(conflicted, "cross-pressure->abstain")

    # Conflict resolution: the side with more reasons becomes the intended vote.
    choice_score = (red_reasons - blue_reasons).astype(np.float64)
    intended_choice = np.zeros(n, dtype=np.int8)
    intended_choice[choice_score < 0] = -1
    intended_choice[choice_score > 0] = 1

    # Exact ties are resolved stochastically.  ELECTION-NOISE controls the scale of
    # that residual uncertainty without continuously weighting the rules.
    tied = choice_score == 0
    if tied.any():
        if params.election_noise > 0:
            tie_break = rng.normal(0.0, params.election_noise, size=n)
        else:
            tie_break = rng.choice(np.array([-1.0, 1.0]), size=n)
        tie_blue = tied & (tie_break < 0)
        tie_red = tied & ~(tie_break < 0)
        intended_choice[tie_blue] = -1
        choice_score[tie_blue] = -TIE_BREAK_SCORE
        intended_choice[tie_red] = 1
        choice_score[tie_red] = TIE_BREAK_SCORE
        note(tied, "tie-break")

    # Turnout stays probabilistic, but enabled turnout and abstention rules shift
    # the baseline in discrete steps of TURNOUT-SENSITIVITY.
    turnout_probability = np.clip(
        params.base_turnout
        + params.turnout_sensitivity * (turnout_reasons - abstention_reasons),
        0.0,
        1.0,
    )

    voted = rng.random(n) < turnout_probability
    vote_choice = np.where(voted, intended_choice, 0).astype(np.int8)

    return Decision(
        choice_score=choice_score,
        intended_choice=intended_choice,
        turnout_probability=turnout_probability,
        voted=voted,
        vote_choice=vote_choice,
        blue_reasons=blue_reasons,
        red_reasons=red_reasons,
        turnout_reasons=turnout_reasons,
        abstention_reasons=abstention_reasons,
        trace=["; ".join(t) for t in traces] if traces is not None else None,
    )
