"""Whole-model behaviour in regimes where the answer is known in advance.

The unit tests pin individual formulas.  These check that the assembled model
does not contradict what the assembled model must do -- a symmetric electorate
cannot systematically favour one party, turnout with no sensitivity term cannot
depart from its baseline, and a model with every stochastic channel closed cannot
move at all.  Tolerances are set from the sampling noise of the statistic in
question, not chosen to make the tests pass.
"""

from __future__ import annotations

import numpy as np
import pytest

from polimods import Model, Params
from polimods.rules import RULE_NAMES

SEEDS = range(12)


def mean_over_seeds(params: Params, steps: int, extract) -> float:
    return float(np.mean([extract(Model(params, seed=s).run(steps)) for s in SEEDS]))


def mean_blue_share(model: Model) -> float:
    return float(np.mean([record.blue_share for record in model.history]))


def mean_turnout(model: Model) -> float:
    return float(np.mean([record.turnout_rate for record in model.history]))


# -- symmetry -----------------------------------------------------------------


def test_a_symmetric_electorate_does_not_favour_either_party():
    """Everything about the setup is mirror-symmetric, so the split must be even.

    A one-sided bug -- the wrong sign on the policy term, an off-by-one in the
    Blue/Red coding -- shows up here and almost nowhere else.
    """
    params = Params(adaptive_parties=False, population=2000, electorate_shape="single-peaked")
    share = mean_over_seeds(params, 30, mean_blue_share)
    assert share == pytest.approx(50.0, abs=1.0)


def test_symmetry_holds_under_the_production_system():
    params = Params.production_rules_defaults(
        adaptive_parties=False, population=2000
    )
    share = mean_over_seeds(params, 30, mean_blue_share)
    assert share == pytest.approx(50.0, abs=1.5)


# -- turnout ------------------------------------------------------------------


def test_turnout_equals_the_baseline_when_sensitivity_is_zero():
    """With no sensitivity term, turnout probability is base_turnout for everyone."""
    params = Params(population=2000, turnout_sensitivity=0.0, base_turnout=0.55)
    assert mean_over_seeds(params, 20, mean_turnout) == pytest.approx(55.0, abs=0.5)


def test_turnout_tracks_base_turnout():
    for base in (0.2, 0.8):
        params = Params(population=2000, turnout_sensitivity=0.0, base_turnout=base)
        assert mean_over_seeds(params, 15, mean_turnout) == pytest.approx(
            100 * base, abs=0.6
        )


def test_preference_strength_raises_turnout_above_the_baseline():
    """|choice_score| is non-negative, so sensitivity can only add turnout."""
    flat = Params(population=2000, turnout_sensitivity=0.0)
    steep = Params(population=2000, turnout_sensitivity=0.5)
    assert mean_over_seeds(steep, 15, mean_turnout) > mean_over_seeds(
        flat, 15, mean_turnout
    )


# -- party adaptation ---------------------------------------------------------


def test_frozen_parties_never_move():
    model = Model(Params(population=500, party_adaptation=0.5, adaptive_parties=False), seed=1)
    before = (model.blue_position, model.red_position)
    model.run(50)
    assert (model.blue_position, model.red_position) == before
    assert model.party_gap == pytest.approx(1.0)


def test_adaptation_closes_the_party_gap():
    """The model's central mechanism: losers chase voters, so the parties converge.

    ``winner_base_adaptation`` is zeroed in both arms.  Left at its default of
    0.03 the winner also drifts toward its own supporters -- who sit between the
    party and the centre -- which closes the gap on its own and would mask the
    effect being measured here.
    """
    fixed = np.mean(
        [
            Model(Params(party_adaptation=0.0, winner_base_adaptation=0.0), seed=s)
            .run(100)
            .party_gap
            for s in SEEDS
        ]
    )
    adapting = np.mean(
        [
            Model(Params(party_adaptation=0.25, winner_base_adaptation=0.0), seed=s)
            .run(100)
            .party_gap
            for s in SEEDS
        ]
    )
    assert fixed == pytest.approx(1.0)
    assert adapting < 0.6


def test_the_winner_also_closes_the_gap_on_its_own():
    """With the loser frozen, winner_base_adaptation still pulls the parties in.

    Worth pinning explicitly: it means ``party_adaptation = 0`` is not a
    no-movement control unless the winner's drift is switched off too.
    """
    still = np.mean(
        [
            Model(Params(party_adaptation=0.0, winner_base_adaptation=0.0), seed=s)
            .run(100)
            .party_gap
            for s in SEEDS
        ]
    )
    drifting = np.mean(
        [
            Model(Params(party_adaptation=0.0, winner_base_adaptation=0.03), seed=s)
            .run(100)
            .party_gap
            for s in SEEDS
        ]
    )
    assert still == pytest.approx(1.0)
    assert drifting < 0.8


def test_base_pressure_preserves_separation():
    """Chasing narrowly-lost opponents converges further than retreating to the base.

    This is the README's second suggested experiment, reduced to its directional
    claim, and it is what would break if the electoral and base targets were ever
    swapped.
    """
    chase = np.mean(
        [
            Model(
                Params(party_adaptation=0.25, base_pressure=0.0, winner_base_adaptation=0.0),
                seed=s,
            )
            .run(100)
            .party_gap
            for s in SEEDS
        ]
    )
    retreat = np.mean(
        [
            Model(
                Params(party_adaptation=0.25, base_pressure=1.0, winner_base_adaptation=0.0),
                seed=s,
            )
            .run(100)
            .party_gap
            for s in SEEDS
        ]
    )
    assert retreat > chase + 0.05


def test_parties_never_cross_or_leave_the_scale():
    for seed in SEEDS:
        model = Model(Params(party_adaptation=1.0, base_pressure=1.0), seed=seed).run(60)
        for record in model.history:
            assert -1.0 <= record.blue_position <= 1.0
            assert -1.0 <= record.red_position <= 1.0
            assert record.blue_position < record.red_position


# -- determinism where nothing should move ------------------------------------


def test_ideology_is_frozen_without_drift_or_influence():
    model = Model(
        Params(population=500, opinion_drift=0.0, social_influence=0.0), seed=2
    )
    before = model.ideology.copy()
    model.run(25)
    assert np.array_equal(model.ideology, before)


def test_identity_is_frozen_without_reinforcement():
    model = Model(Params(population=500, identity_reinforcement=0.0), seed=2)
    before = model.party_identity.copy()
    model.run(25)
    assert np.array_equal(model.party_identity, before)


def test_social_influence_pulls_the_electorate_together():
    """Peer influence can only contract the ideology distribution, never spread it.

    Checked on spread rather than mean: both electorate shapes are symmetric, so
    the mean sits near zero however much the voters move.
    """
    base = dict(
        population=500,
        social_network=True,
        electorate_shape="two-camp",
        electorate_polarization=0.35,
    )
    isolated = Model(Params(**base, social_influence=0.0), seed=1).run(60)
    connected = Model(Params(**base, social_influence=0.2), seed=1).run(60)

    assert isolated.ideology_sd > 0.3  # the two camps survive
    assert connected.ideology_sd < 0.1  # they merge
    assert connected.ideology_sd < isolated.ideology_sd


def test_social_influence_does_nothing_without_the_network():
    model = Model(
        Params(population=500, social_network=False, social_influence=0.4, opinion_drift=0.0),
        seed=1,
    )
    before = model.ideology.copy()
    model.run(20)
    assert np.array_equal(model.ideology, before)


def test_homophily_slows_the_collapse_of_the_camps():
    """Linking like to like keeps the camps apart a little longer."""
    base = dict(
        population=500,
        social_network=True,
        electorate_shape="two-camp",
        social_influence=0.05,
    )
    mixed = np.mean(
        [Model(Params(**base, homophily=0.0), seed=s).run(100).ideology_sd for s in SEEDS]
    )
    sorted_ = np.mean(
        [Model(Params(**base, homophily=1.0), seed=s).run(100).ideology_sd for s in SEEDS]
    )
    assert sorted_ > mixed


def test_ideology_stays_on_the_scale_under_maximum_drift():
    model = Model(Params(population=500, opinion_drift=0.1), seed=2).run(50)
    assert model.ideology.min() >= -1.0
    assert model.ideology.max() <= 1.0


# -- the production system as a whole -----------------------------------------


def test_every_rule_off_is_a_fair_coin_at_the_baseline_turnout():
    """No rule fires, so every voter is tie-broken and turnout is untouched."""
    params = Params(
        population=2000,
        production_system=True,
        adaptive_parties=False,
        base_turnout=0.55,
        **{f"rule_{name}": False for name in RULE_NAMES},
    )
    assert mean_over_seeds(params, 25, mean_blue_share) == pytest.approx(50.0, abs=1.0)
    assert mean_over_seeds(params, 25, mean_turnout) == pytest.approx(55.0, abs=0.5)


def test_habit_rule_suppresses_vote_switching():
    """A rule that says "do what you did last time" must reduce switching."""
    off = mean_over_seeds(
        Params.production_rules_defaults(population=1000, rule_habit=False),
        40,
        lambda m: float(np.mean([r.switch_rate for r in m.history])),
    )
    on = mean_over_seeds(
        Params.production_rules_defaults(population=1000, rule_habit=True),
        40,
        lambda m: float(np.mean([r.switch_rate for r in m.history])),
    )
    assert on < off


def test_abstention_rules_lower_turnout():
    """Indifference and alienation only ever push turnout down."""
    without = mean_over_seeds(
        Params.production_rules_defaults(
            population=1000, rule_indifference=False, rule_alienation=False,
            rule_cross_pressure=False,
        ),
        30,
        mean_turnout,
    )
    with_them = mean_over_seeds(
        Params.production_rules_defaults(population=1000), 30, mean_turnout
    )
    assert with_them < without


# -- electorate construction --------------------------------------------------


def test_two_camp_electorate_is_bimodal():
    model = Model(
        Params(
            population=2000,
            electorate_shape="two-camp",
            electorate_polarization=0.6,
            ideology_spread=0.1,
        ),
        seed=1,
    )
    centre = float(np.mean(np.abs(model.ideology) < 0.2))
    camps = float(np.mean(np.abs(np.abs(model.ideology) - 0.6) < 0.2))
    assert camps > 0.85
    assert centre < 0.05


def test_polarization_is_ignored_by_a_single_peaked_electorate():
    a = Model(Params(population=500, electorate_polarization=0.0), seed=7)
    b = Model(Params(population=500, electorate_polarization=0.9), seed=7)
    assert np.array_equal(a.ideology, b.ideology)
