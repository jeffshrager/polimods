"""The eight production rules, one at a time, at their thresholds.

Each rule is tested in isolation -- all other rules switched off -- so a failure
names the rule that broke.  Boundary cases matter here: the NetLogo uses a mix of
strict and non-strict comparisons (``<`` for policy, ``<=`` for identity), and
getting one wrong shifts every voter sitting exactly on a threshold.
"""

from __future__ import annotations

import numpy as np
import pytest

from polimods import Network, Params
from polimods.rules import (
    ALIENATION_THRESHOLD,
    IDENTITY_THRESHOLD,
    NEIGHBOR_MAJORITY_THRESHOLD,
    POLICY_THRESHOLD,
    RULE_NAMES,
    STRONG_IDENTITY_THRESHOLD,
    STRONG_POLICY_THRESHOLD,
    TIE_BREAK_SCORE,
    run_production_system,
)

ALL_RULES_OFF = {f"rule_{name}": False for name in RULE_NAMES}


def fire(
    rule: str | None = None,
    *,
    ideology,
    party_identity=0.0,
    last_vote=0,
    blue_position=-0.5,
    red_position=0.5,
    network=None,
    seed=0,
    **param_overrides,
):
    """Run the production system with only ``rule`` enabled and return the reasons."""
    values = np.atleast_1d(np.asarray(ideology, dtype=float))
    n = len(values)

    switches = dict(ALL_RULES_OFF)
    if rule is not None:
        switches[f"rule_{rule}"] = True
    # Explicit rule_* overrides win, so a test can enable several rules at once.
    switches.update(
        {k: param_overrides.pop(k) for k in list(param_overrides) if k in ALL_RULES_OFF}
    )

    params = Params(
        population=max(n, 50),
        production_system=True,
        **switches,
        **param_overrides,
    )

    return run_production_system(
        params=params,
        rng=np.random.default_rng(seed),
        ideology=values,
        party_identity=np.full(n, party_identity, dtype=float)
        if np.isscalar(party_identity)
        else np.asarray(party_identity, dtype=float),
        last_vote=np.full(n, last_vote, dtype=np.int8)
        if np.isscalar(last_vote)
        else np.asarray(last_vote, dtype=np.int8),
        blue_position=blue_position,
        red_position=red_position,
        network=network if network is not None else Network(n),
        trace=True,
    )


# With Blue at -0.5 and Red at +0.5, a voter at ideology x inside the interval has
# policy_advantage = |x + 0.5| - |x - 0.5| = 2x.  So the policy threshold of 0.15
# corresponds to an ideology of 0.075.
POLICY_EDGE = POLICY_THRESHOLD / 2


# -- rule 1: policy proximity -------------------------------------------------


def test_policy_rule_fires_beyond_the_threshold():
    decision = fire("policy", ideology=[-0.2, 0.2])
    assert decision.blue_reasons.tolist() == [1, 0]
    assert decision.red_reasons.tolist() == [0, 1]


def test_policy_rule_is_silent_exactly_on_the_threshold():
    """The NetLogo test is strict (``<`` / ``>``), so the boundary does not fire."""
    decision = fire("policy", ideology=[-POLICY_EDGE, POLICY_EDGE])
    assert decision.blue_reasons.tolist() == [0, 0]
    assert decision.red_reasons.tolist() == [0, 0]


def test_policy_rule_records_a_trace():
    decision = fire("policy", ideology=[-0.4])
    assert "policy->Blue" in decision.trace[0]


# -- rule 2: partisan identity ------------------------------------------------


def test_identity_rule_uses_identity_strength():
    """effective_identity = identity_strength * party_identity, tested with <=."""
    edge = IDENTITY_THRESHOLD / 0.6  # exactly on the threshold at strength 0.6
    decision = fire(
        "identity",
        ideology=[0.0, 0.0, 0.0],
        party_identity=[-edge, -edge * 0.9, edge],
        identity_strength=0.6,
    )
    assert decision.blue_reasons.tolist() == [1, 0, 0]  # non-strict: the edge fires
    assert decision.red_reasons.tolist() == [0, 0, 1]


def test_identity_rule_silent_when_identity_strength_is_zero():
    decision = fire(
        "identity", ideology=[0.0], party_identity=[-1.0], identity_strength=0.0
    )
    assert decision.blue_reasons.tolist() == [0]


# -- rule 3: voting habit -----------------------------------------------------


def test_habit_rule_repeats_the_previous_vote():
    decision = fire("habit", ideology=[0.0, 0.0, 0.0], last_vote=[-1, 0, 1])
    assert decision.blue_reasons.tolist() == [1, 0, 0]
    assert decision.red_reasons.tolist() == [0, 0, 1]


# -- rule 4: social majority --------------------------------------------------


def make_star(n: int, spokes: int) -> Network:
    """Voter 0 linked to voters 1..spokes."""
    return Network(n, np.array([[0, i] for i in range(1, spokes + 1)]))


def test_neighbor_rule_needs_a_clear_majority():
    """Four active neighbours: 3 Red is 0.75 (fires), 2 Red is 0.5 (does not)."""
    n = 50
    network = make_star(n, 4)

    three_red = np.zeros(n, dtype=np.int8)
    three_red[1:4] = 1
    three_red[4] = -1
    decision = fire(
        "neighbors",
        ideology=np.zeros(n),
        last_vote=three_red,
        network=network,
        social_network=True,
    )
    assert decision.red_reasons[0] == 1
    assert decision.blue_reasons[0] == 0

    two_red = np.zeros(n, dtype=np.int8)
    two_red[1:3] = 1
    two_red[3:5] = -1
    decision = fire(
        "neighbors",
        ideology=np.zeros(n),
        last_vote=two_red,
        network=network,
        social_network=True,
    )
    assert decision.red_reasons[0] == 0
    assert decision.blue_reasons[0] == 0


def test_neighbor_rule_ignores_abstaining_neighbours():
    """Neighbours who abstained are excluded from the denominator entirely."""
    n = 50
    network = make_star(n, 4)
    last_vote = np.zeros(n, dtype=np.int8)
    last_vote[1] = 1  # the only politically active neighbour
    decision = fire(
        "neighbors",
        ideology=np.zeros(n),
        last_vote=last_vote,
        network=network,
        social_network=True,
    )
    assert decision.red_reasons[0] == 1  # 1/1 = 100% Red


def test_neighbor_rule_silent_without_the_social_network_switch():
    n = 50
    last_vote = np.zeros(n, dtype=np.int8)
    last_vote[1:5] = 1
    decision = fire(
        "neighbors",
        ideology=np.zeros(n),
        last_vote=last_vote,
        network=make_star(n, 4),
        social_network=False,
    )
    assert decision.red_reasons[0] == 0


def test_neighbor_rule_silent_for_isolated_voters():
    n = 50
    last_vote = np.zeros(n, dtype=np.int8)
    last_vote[1:5] = 1
    decision = fire(
        "neighbors",
        ideology=np.zeros(n),
        last_vote=last_vote,
        network=make_star(n, 4),
        social_network=True,
    )
    assert decision.red_reasons[10] == 0  # voter 10 has no links
    assert decision.blue_reasons[10] == 0


def test_neighbor_majority_threshold_is_symmetric():
    assert 1 - NEIGHBOR_MAJORITY_THRESHOLD == pytest.approx(0.4)


# -- rule 5: engagement -------------------------------------------------------


def test_engagement_rule_counts_policy_and_identity_separately():
    """Both halves can fire for the same voter, giving two turnout reasons."""
    strong = STRONG_POLICY_THRESHOLD / 2 + 0.01
    decision = fire(
        "engagement",
        ideology=[strong],
        party_identity=[1.0],
        identity_strength=STRONG_IDENTITY_THRESHOLD,
    )
    assert decision.turnout_reasons.tolist() == [2]


def test_engagement_rule_silent_for_a_lukewarm_voter():
    decision = fire("engagement", ideology=[0.05], party_identity=[0.1])
    assert decision.turnout_reasons.tolist() == [0]


# -- rule 6: indifference -----------------------------------------------------


def test_indifference_rule_fires_on_the_threshold():
    """Non-strict ``<=``: a voter exactly at the boundary is counted indifferent."""
    decision = fire("indifference", ideology=[0.0, POLICY_EDGE, 0.4])
    assert decision.abstention_reasons.tolist() == [1, 1, 0]


# -- rule 7: alienation -------------------------------------------------------


def test_alienation_rule_needs_both_parties_to_be_distant():
    """Parties at -0.9 and +0.9: a centrist is 0.9 from both and feels alienated."""
    decision = fire(
        "alienation",
        ideology=[0.0, 0.85],
        blue_position=-0.9,
        red_position=0.9,
    )
    assert decision.abstention_reasons.tolist() == [1, 0]


def test_alienation_threshold_boundary_is_inclusive():
    decision = fire(
        "alienation",
        ideology=[0.0],
        blue_position=-ALIENATION_THRESHOLD,
        red_position=ALIENATION_THRESHOLD,
    )
    assert decision.abstention_reasons.tolist() == [1]


# -- rule 8: cross-pressure ---------------------------------------------------


def test_cross_pressure_fires_when_policy_and_identity_disagree():
    """Ideology leans Red, partisan identity leans Blue."""
    decision = fire(
        "cross_pressure",
        ideology=[0.4],
        party_identity=[-1.0],
        identity_strength=0.6,
    )
    assert decision.abstention_reasons.tolist() == [1]


def test_cross_pressure_is_independent_of_rules_one_and_two():
    """It fires with the policy and identity rules switched off, as in NetLogo."""
    decision = fire(
        "cross_pressure", ideology=[0.4], party_identity=[-1.0], identity_strength=0.6
    )
    assert decision.blue_reasons.tolist() == [0]  # rule 1/2 really are off
    assert decision.red_reasons.tolist() == [0]
    assert decision.abstention_reasons.tolist() == [1]


def test_cross_pressure_silent_when_both_point_the_same_way():
    decision = fire(
        "cross_pressure", ideology=[0.4], party_identity=[1.0], identity_strength=0.6
    )
    assert decision.abstention_reasons.tolist() == [0]


# -- conflict resolution and turnout -----------------------------------------


def test_reason_counting_decides_the_vote():
    """Two Blue reasons against one Red reason gives a score of -1."""
    decision = fire(
        None,
        ideology=[-0.4],
        party_identity=[-1.0],
        last_vote=[1],
        identity_strength=0.6,
        rule_policy=True,
        rule_identity=True,
        rule_habit=True,
    )
    assert decision.blue_reasons.tolist() == [2]
    assert decision.red_reasons.tolist() == [1]
    assert decision.choice_score.tolist() == [-1.0]
    assert decision.intended_choice.tolist() == [-1]


def test_ties_are_broken_and_never_left_at_zero():
    """With every rule off, all voters tie and must be resolved stochastically."""
    decision = fire(None, ideology=np.zeros(200), election_noise=0.08)
    assert np.all(np.abs(decision.choice_score) == TIE_BREAK_SCORE)
    assert np.all(np.isin(decision.intended_choice, (-1, 1)))
    # A fair coin over 200 voters: both sides must appear.
    assert 0 < int((decision.intended_choice == 1).sum()) < 200


def test_tie_break_works_with_zero_election_noise():
    decision = fire(None, ideology=np.zeros(200), election_noise=0.0)
    assert np.all(np.abs(decision.choice_score) == TIE_BREAK_SCORE)
    assert 0 < int((decision.intended_choice == 1).sum()) < 200


def test_turnout_moves_in_discrete_steps():
    """base_turnout + turnout_sensitivity * (turnout_reasons - abstention_reasons)."""
    decision = fire(
        "indifference",
        ideology=[0.0],
        base_turnout=0.5,
        turnout_sensitivity=0.12,
    )
    assert decision.turnout_probability.tolist() == [pytest.approx(0.38)]


def test_turnout_probability_is_clipped():
    decision = fire(
        "indifference", ideology=[0.0], base_turnout=0.05, turnout_sensitivity=0.5
    )
    assert decision.turnout_probability.tolist() == [0.0]


def test_trace_is_omitted_unless_requested():
    from polimods import Model

    model = Model(Params.production_rules_defaults(population=100), seed=1)
    model.step()
    assert model.decision.trace is None
