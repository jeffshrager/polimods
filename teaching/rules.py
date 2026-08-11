"""
================================================================================
 RULES -- the voter "production system": eight IF-THEN rules
================================================================================
This file implements one of the model's two alternate theories of how a
voter decides what to do. It only runs when `params.production_system` is
True (see params.py); otherwise Model.run_election in model.py uses the
simpler continuous weighted-choice equation instead.

MENTAL MODEL: think of each voter as consulting eight independent
IF-THEN rules, once per election. Each rule looks only at that voter's own
situation (their ideology, identity, voting history, and neighbours) and, if
its condition holds, casts one vote for "Blue", one for "Red", one for
"turn out", or one for "abstain" -- a discrete *reason*, not a weighted
number. After all eight rules have fired (or not), the votes are simply
counted:

    choice_score = (reasons for Red) - (reasons for Blue)

This is qualitatively different from a weighted sum of continuous factors
(which is what the *other* decision model, run_weighted_choice_model in
model.py, does): here, a voter who is 0.01 away from POLICY_THRESHOLD gets
*zero* credit for that near-miss, while a voter who is barely past the
threshold gets exactly the same one-reason credit as a voter who is far,
far past it. The production system is a model of qualitative, threshold-
triggered reasoning; the weighted-choice model is a model of graded,
continuous preference. They are two different psychological theories of
voting, not two implementations of the same idea -- that's why the switch
between them lives at the top of Params rather than being an
implementation detail.

Each function below is vectorized: every array is indexed by voter, so a
single call to run_production_system evaluates all eight rules for every
voter in the electorate at once (no per-voter Python loop).
================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .network import Network
from .params import Params

# --------------------------------------------------------------------------
# Activation thresholds. Collected here, at the top, exactly the way NetLogo
# collects its threshold constants at the top of run-production-system --
# gathering them in one place makes them easy to find, inspect, and tune
# without hunting through the rule bodies below.
# --------------------------------------------------------------------------

#: How much closer one party has to be (in absolute ideology distance) before
#: RULE 1 (policy proximity) counts it as a reason.
POLICY_THRESHOLD = 0.15

#: How strong (in absolute value) a voter's identity_strength-scaled identity
#: has to be before RULE 2 (partisan identity) counts it as a reason.
IDENTITY_THRESHOLD = 0.25

#: A *higher* bar than POLICY_THRESHOLD, used only by RULE 5 (engagement):
#: policy preference has to be unusually strong -- not just enough to pick a
#: side, but enough to motivate showing up -- to add a turnout reason.
STRONG_POLICY_THRESHOLD = 0.35

#: The engagement-triggering counterpart of IDENTITY_THRESHOLD -- also a
#: higher bar than the ordinary identity threshold.
STRONG_IDENTITY_THRESHOLD = 0.60

#: RULE 4 (social majority) requires a *clear* majority of a voter's
#: politically active neighbours to have voted the same way -- not just a
#: bare 51%, but 60%+ -- before it treats that as a reason.
NEIGHBOR_MAJORITY_THRESHOLD = 0.60

#: RULE 7 (alienation): if even the *nearer* of the two parties is at least
#: this far away, that's a reason to abstain regardless of which party it is.
ALIENATION_THRESHOLD = 0.55

# The eight rules, in the order they fire. Each name matches a `rule_*`
# boolean field on Params (minus the "rule_" prefix), e.g. RULE_NAMES[0]
# == "policy" corresponds to Params.rule_policy.
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

#: The choice_score assigned to a voter whose reason-count came out
#: perfectly tied (see the tie-break block below). This is a very small
#: nonzero number rather than exactly 0 -- and that distinction matters well
#: beyond bookkeeping: model.py's move_losing_party filters "persuadable"
#: voters using `abs(choice_score) <= persuadable_band`, and under the
#: production system these hairline +/-0.001 values are typically the *only*
#: scores small enough to fall inside a default persuadable_band of 0.25
#: (every other voter's score is a whole-number reason count, e.g. 1, 2, 3).
#: So in practice, tie-broken voters end up being the losing party's entire
#: pool of "voters it can plausibly win over."
TIE_BREAK_SCORE = 0.001


@dataclass
class Decision:
    """Everything one election's worth of voter deliberation produced, for
    the whole electorate at once (each field is an array indexed by voter,
    except `trace`, a list of per-voter debug strings).

    Populated either by run_production_system (below, with the reason-count
    fields filled in) or by Model.run_weighted_choice_model in model.py
    (which leaves the reason-count fields as None, since that model doesn't
    have discrete reasons to report)."""

    choice_score: np.ndarray
    intended_choice: np.ndarray
    turnout_probability: np.ndarray
    voted: np.ndarray
    vote_choice: np.ndarray
    #: How many reasons each voter accumulated for Blue / Red / turning out /
    #: abstaining. None when produced by the weighted-choice model instead.
    blue_reasons: np.ndarray | None = None
    red_reasons: np.ndarray | None = None
    turnout_reasons: np.ndarray | None = None
    abstention_reasons: np.ndarray | None = None
    #: Optional human-readable "why did voter i do that" strings, one per
    #: voter, only populated when run_production_system is called with
    #: trace=True (expensive -- skipped by default).
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
    """Run all eight (independently switchable) rules for every voter at
    once, then resolve each voter's accumulated reasons into a vote choice
    and a turnout decision. See the module docstring above for the overall
    "reasons, not weights" design, and the module-level constants above for
    each rule's activation threshold."""

    n = len(ideology)
    zeros = lambda: np.zeros(n, dtype=np.int64)  # noqa: E731

    # Running per-voter tallies: how many reasons has each voter accumulated
    # for each side, and for turning out or abstaining? Every rule below
    # adds 0 or 1 to some subset of these four arrays.
    blue_reasons = zeros()
    red_reasons = zeros()
    turnout_reasons = zeros()
    abstention_reasons = zeros()

    # Optional debugging aid: if trace=True, remember which rule fired for
    # which voter and why, as a growing list of human-readable strings per
    # voter (e.g. "policy->Blue"). Left as None (and `note` becomes a no-op)
    # when trace=False, since building these strings for every voter every
    # election would be needlessly slow for a normal run.
    traces: list[list[str]] | None = [[] for _ in range(n)] if trace else None

    def note(mask: np.ndarray, label: str) -> None:
        if traces is None:
            return
        for i in np.flatnonzero(mask):
            traces[i].append(label)

    # Two quantities nearly every rule below depends on: how far each voter
    # is (in ideology) from each party, and how strongly identity pulls them
    # (scaled by identity_strength, same as the weighted-choice model uses).
    blue_distance = np.abs(ideology - blue_position)
    red_distance = np.abs(ideology - red_position)
    # Positive = Red is closer (favors Red); negative = Blue is closer.
    policy_advantage = blue_distance - red_distance
    effective_identity = params.identity_strength * party_identity

    # ------------------------------------------------------------------
    # RULE 1: POLICY PROXIMITY
    # IF one party is substantially closer on ideology than the other,
    # THEN that's a reason to prefer it.
    # ------------------------------------------------------------------
    if params.rule_policy:
        favors_blue = policy_advantage < -POLICY_THRESHOLD
        favors_red = policy_advantage > POLICY_THRESHOLD
        blue_reasons += favors_blue
        red_reasons += favors_red
        note(favors_blue, "policy->Blue")
        note(favors_red, "policy->Red")

    # ------------------------------------------------------------------
    # RULE 2: PARTISAN IDENTITY
    # IF a voter's (scaled) partisan identity is strong enough on its own,
    # THEN that's a reason to prefer the corresponding party -- independent
    # of where the parties currently stand on policy.
    # ------------------------------------------------------------------
    if params.rule_identity:
        favors_blue = effective_identity <= -IDENTITY_THRESHOLD
        favors_red = effective_identity >= IDENTITY_THRESHOLD
        blue_reasons += favors_blue
        red_reasons += favors_red
        note(favors_blue, "identity->Blue")
        note(favors_red, "identity->Red")

    # ------------------------------------------------------------------
    # RULE 3: VOTING HABIT
    # IF a voter chose a party last time, THEN that's a reason to repeat
    # it -- pure behavioural inertia, no reasoning about current positions
    # involved at all.
    # ------------------------------------------------------------------
    if params.rule_habit:
        was_blue = last_vote == -1
        was_red = last_vote == 1
        blue_reasons += was_blue
        red_reasons += was_red
        note(was_blue, "habit->Blue")
        note(was_red, "habit->Red")

    # ------------------------------------------------------------------
    # RULE 4: SOCIAL MAJORITY
    # IF a clear majority (>= NEIGHBOR_MAJORITY_THRESHOLD) of a voter's
    # politically active neighbours (i.e. neighbours who voted last time,
    # not abstainers) chose one party, THEN that's a reason to follow them.
    # Only evaluated at all when social_network is on and there is at least
    # one edge -- with no network, "neighbours" is meaningless.
    # ------------------------------------------------------------------
    if params.rule_neighbors and params.social_network and len(network):
        active = last_vote != 0
        red_fraction, valid = network.neighbor_fraction(last_vote == 1, active)
        # `valid` is False for voters with no politically-active neighbours
        # at all -- for them the rule simply doesn't fire (see
        # Network.neighbor_fraction's docstring for why 0/0 is excluded
        # rather than treated as 0%).
        favors_blue = valid & (red_fraction <= 1 - NEIGHBOR_MAJORITY_THRESHOLD)
        favors_red = valid & (red_fraction >= NEIGHBOR_MAJORITY_THRESHOLD)
        blue_reasons += favors_blue
        red_reasons += favors_red
        note(favors_blue, "neighbors->Blue")
        note(favors_red, "neighbors->Red")

    # ------------------------------------------------------------------
    # RULE 5: ENGAGEMENT
    # IF either policy preference or partisan identity is *unusually*
    # strong (using the higher STRONG_* thresholds, not the ordinary ones
    # rules 1/2 use), THEN that's a reason to turn out -- regardless of
    # which party it favours. Note this can add up to two turnout reasons
    # (one from strong policy, one from strong identity) to the same voter.
    # ------------------------------------------------------------------
    if params.rule_engagement:
        strong_policy = np.abs(policy_advantage) >= STRONG_POLICY_THRESHOLD
        strong_identity = np.abs(effective_identity) >= STRONG_IDENTITY_THRESHOLD
        turnout_reasons += strong_policy
        turnout_reasons += strong_identity
        note(strong_policy, "strong-policy->turnout")
        note(strong_identity, "strong-identity->turnout")

    # ------------------------------------------------------------------
    # RULE 6: INDIFFERENCE
    # IF the two parties are nearly equally attractive on policy (within
    # POLICY_THRESHOLD of each other), THEN that's a reason to abstain --
    # "why bother, they're basically the same to me."
    # ------------------------------------------------------------------
    if params.rule_indifference:
        indifferent = np.abs(policy_advantage) <= POLICY_THRESHOLD
        abstention_reasons += indifferent
        note(indifferent, "indifference->abstain")

    # ------------------------------------------------------------------
    # RULE 7: ALIENATION
    # IF even the *closer* of the two parties is still far away (both
    # distances >= ALIENATION_THRESHOLD), THEN that's a reason to abstain --
    # "neither one represents me."
    # ------------------------------------------------------------------
    if params.rule_alienation:
        alienated = np.minimum(blue_distance, red_distance) >= ALIENATION_THRESHOLD
        abstention_reasons += alienated
        note(alienated, "alienation->abstain")

    # ------------------------------------------------------------------
    # RULE 8: CROSS-PRESSURE
    # IF policy preference and partisan identity point to *opposite*
    # parties (one clearly favours Blue, the other clearly favours Red),
    # THEN that's a reason to abstain -- an internally conflicted voter.
    # Deliberately evaluated independently of whether rules 1/2 are
    # switched on: cross-pressure asks "do policy and identity disagree,"
    # which is a coherent question even if neither policy nor identity
    # alone is being counted as its own reason this run.
    # ------------------------------------------------------------------
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

    # ==================================================================
    # CONFLICT RESOLUTION: turn accumulated reasons into an actual vote.
    # The side with more reasons wins; ties are broken with noise.
    # ==================================================================

    # Positive => more reasons for Red than Blue => Red preferred; negative
    # => Blue preferred; exactly zero => a perfect tie (handled below).
    choice_score = (red_reasons - blue_reasons).astype(np.float64)
    intended_choice = np.zeros(n, dtype=np.int8)
    intended_choice[choice_score < 0] = -1
    intended_choice[choice_score > 0] = 1

    # Exact ties (equal reason counts for both sides, including "zero
    # reasons for either") get resolved stochastically rather than defaulting
    # to one party. election_noise controls how that randomness behaves:
    # with noise > 0, a random draw's *sign* breaks the tie (so the
    # resulting choice_score sits infinitesimally off zero, at
    # +/-TIE_BREAK_SCORE); with no noise configured, a coin flip breaks it
    # instead. Either way the *result* used below is just a sign, so this
    # doesn't reintroduce continuous weighting into an otherwise discrete
    # reason-counting model -- it only decides which way an otherwise-
    # undecidable tie falls.
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

    # Turnout stays probabilistic (as in the weighted-choice model), but here
    # the *baseline* probability is nudged by whole steps of
    # turnout_sensitivity for each net turnout/abstention reason, rather than
    # by a continuously varying quantity.
    turnout_probability = np.clip(
        params.base_turnout
        + params.turnout_sensitivity * (turnout_reasons - abstention_reasons),
        0.0,
        1.0,
    )

    voted = rng.random(n) < turnout_probability
    # Voters who didn't turn out cast no ballot (vote_choice=0), regardless
    # of which way they were leaning.
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
