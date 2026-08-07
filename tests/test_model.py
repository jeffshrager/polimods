"""Mechanism-by-mechanism checks against hand-computed values.

Each test pins one formula from the NetLogo source.  Where a number appears
without derivation it is worked out in the test's docstring, so a failure tells
you which equation drifted rather than only that something changed.
"""

from __future__ import annotations

import numpy as np
import pytest

from polimods import Model, Network, Params
from polimods.history import netlogo_number, netlogo_precision

MIN_POPULATION = 50  # the smallest a NetLogo slider allows


def make_model(**overrides) -> Model:
    """A model with the stochastic parts switched off, ready to be posed by hand."""
    defaults = dict(
        population=MIN_POPULATION,
        election_noise=0.0,
        opinion_drift=0.0,
        identity_noise=0.0,
    )
    defaults.update(overrides)
    return Model(Params(**defaults), seed=0)


# -- vote choice --------------------------------------------------------------


def test_choice_score_matches_readme_worked_example():
    """README example: ideology 0.2, Blue -0.5, Red 0.5, identity -0.3, strength 0.6.

    Policy term:   |0.2 - (-0.5)| - |0.2 - 0.5| = 0.7 - 0.3 = +0.4
    Identity term: 0.6 * (-0.3)                              = -0.18
    Total                                                    = +0.22  -> Red
    """
    model = make_model(identity_strength=0.6)
    model.blue_position, model.red_position = -0.5, 0.5
    model.ideology[:] = 0.2
    model.party_identity[:] = -0.3

    decision = model.run_weighted_choice_model()

    assert decision.choice_score == pytest.approx(0.22)
    assert np.all(decision.intended_choice == 1)


def test_exact_zero_choice_score_goes_to_red():
    """NetLogo's IFELSE sends only strictly negative scores to Blue."""
    model = make_model(identity_strength=0.6)
    model.blue_position, model.red_position = -0.5, 0.5
    model.ideology[:] = 0.0
    model.party_identity[:] = 0.0

    decision = model.run_weighted_choice_model()

    assert np.all(decision.choice_score == 0.0)
    assert np.all(decision.intended_choice == 1)


def test_turnout_probability_formula_and_clipping():
    """base_turnout + turnout_sensitivity * |C|, clipped to [0, 1]."""
    model = make_model(base_turnout=0.5, turnout_sensitivity=0.25)
    model.blue_position, model.red_position = -0.5, 0.5
    model.ideology[:] = 0.2  # |C| = 0.4 with identity 0
    model.party_identity[:] = 0.0
    model.params = model.params.replace(identity_strength=0.6)

    decision = model.run_weighted_choice_model()
    assert decision.turnout_probability == pytest.approx(0.5 + 0.25 * 0.4)

    ceiling = make_model(base_turnout=1.0, turnout_sensitivity=0.5)
    ceiling.blue_position, ceiling.red_position = -1.0, 1.0
    ceiling.ideology[:] = 1.0
    ceiling.party_identity[:] = 1.0
    assert np.all(ceiling.run_weighted_choice_model().turnout_probability == 1.0)


def test_abstainers_get_vote_choice_zero():
    model = make_model(base_turnout=0.0, turnout_sensitivity=0.0)
    decision = model.run_weighted_choice_model()
    assert np.all(decision.vote_choice == 0)
    assert not decision.voted.any()
    # intended_choice is still recorded, as in the production-rules NetLogo.
    assert np.all(np.isin(decision.intended_choice, (-1, 1)))


def test_no_votes_cast_reports_a_dead_heat():
    model = make_model(base_turnout=0.0, turnout_sensitivity=0.0)
    model.step()
    assert model.total_votes == 0
    assert model.blue_share == 50.0
    assert model.red_share == 50.0
    assert model.election_margin == 0.0
    assert model.turnout_rate == 0.0
    assert "tie-break" in model.winner_name


# -- party adaptation ---------------------------------------------------------


def test_enforce_party_order_separates_crossed_parties():
    """Blue at 0.5 and Red at 0.4 -> midpoint 0.45 -> Blue 0.44, Red 0.46."""
    model = make_model()
    model.blue_position, model.red_position = 0.5, 0.4
    model.enforce_party_order()
    assert model.blue_position == pytest.approx(0.44)
    assert model.red_position == pytest.approx(0.46)


def test_enforce_party_order_leaves_ordered_parties_alone():
    model = make_model()
    model.blue_position, model.red_position = -0.3, 0.4
    model.enforce_party_order()
    assert (model.blue_position, model.red_position) == (-0.3, 0.4)


def test_enforce_party_order_clamps_to_the_scale():
    model = make_model()
    model.blue_position, model.red_position = -3.0, 2.0
    model.enforce_party_order()
    assert model.blue_position == -1.0
    assert model.red_position == 1.0


def test_frozen_parties_are_never_reordered():
    """With adaptive_parties off, enforce_party_order never runs after setup."""
    model = make_model(adaptive_parties=False, initial_party_gap=1.0)
    before = (model.blue_position, model.red_position)
    model.run(10)
    assert (model.blue_position, model.red_position) == before


def test_move_losing_party_targets_persuadable_opponents():
    """Blue lost; it should chase Red voters whose |score| is within the band.

    Persuadables here have ideology 0.2 and 0.4 -> electoral target 0.3.
    Blue's own supporters have ideology -0.6 and -0.4 -> base target -0.5.
    With base_pressure 0.5 the blended target is -0.1, and with adaptation 0.5
    Blue moves halfway from -0.5 to -0.1, landing at -0.3.
    """
    model = make_model(party_adaptation=0.5, base_pressure=0.5, persuadable_band=0.25)
    model.blue_position, model.red_position = -0.5, 0.5

    n = MIN_POPULATION
    model.ideology = np.zeros(n)
    model.vote_choice = np.zeros(n, dtype=np.int8)
    model.choice_score = np.zeros(n)

    # Two Blue supporters, two narrowly-lost Red voters, and one Red voter who is
    # far outside the persuadable band and must therefore be ignored.
    model.ideology[0], model.vote_choice[0], model.choice_score[0] = -0.6, -1, -0.9
    model.ideology[1], model.vote_choice[1], model.choice_score[1] = -0.4, -1, -0.7
    model.ideology[2], model.vote_choice[2], model.choice_score[2] = 0.2, 1, 0.1
    model.ideology[3], model.vote_choice[3], model.choice_score[3] = 0.4, 1, 0.25
    model.ideology[4], model.vote_choice[4], model.choice_score[4] = 0.9, 1, 0.8

    model.move_losing_party(-1)

    assert model.blue_position == pytest.approx(-0.3)


def test_move_losing_party_falls_back_to_the_whole_electorate():
    """With no persuadables, the electoral target is the mean of all voters."""
    model = make_model(party_adaptation=1.0, base_pressure=0.0, persuadable_band=0.01)
    model.blue_position, model.red_position = -0.5, 0.5

    n = MIN_POPULATION
    model.ideology = np.linspace(-1.0, 1.0, n)
    model.vote_choice = np.ones(n, dtype=np.int8)  # everyone voted Red
    model.choice_score = np.full(n, 0.9)  # nobody is close to persuadable

    model.move_losing_party(-1)

    assert model.blue_position == pytest.approx(model.ideology.mean())


def test_base_target_falls_back_when_the_loser_has_no_supporters():
    """base_pressure=1 with no supporters still moves toward the electoral target."""
    model = make_model(party_adaptation=1.0, base_pressure=1.0, persuadable_band=1.0)
    model.blue_position, model.red_position = -0.5, 0.5

    n = MIN_POPULATION
    model.ideology = np.full(n, 0.25)
    model.vote_choice = np.ones(n, dtype=np.int8)  # no Blue voters at all
    model.choice_score = np.zeros(n)

    model.move_losing_party(-1)

    assert model.blue_position == pytest.approx(0.25)


def test_winning_party_stays_put_when_winner_base_adaptation_is_zero():
    model = make_model(winner_base_adaptation=0.0)
    model.blue_position = -0.5
    model.vote_choice = np.full(MIN_POPULATION, -1, dtype=np.int8)
    model.ideology = np.full(MIN_POPULATION, -0.9)

    model.move_winning_party(-1)

    assert model.blue_position == -0.5


def test_winning_party_moves_toward_its_own_supporters():
    model = make_model(winner_base_adaptation=0.5)
    model.blue_position = -0.5
    model.vote_choice = np.full(MIN_POPULATION, -1, dtype=np.int8)
    model.ideology = np.full(MIN_POPULATION, -0.9)

    model.move_winning_party(-1)

    assert model.blue_position == pytest.approx(-0.7)


# -- voter updating -----------------------------------------------------------


def test_identity_reinforcement_skips_abstainers():
    """(1 - r) * identity + r * vote, and abstainers keep their prior vote."""
    model = make_model(identity_reinforcement=0.1, social_influence=0.0)
    model.party_identity[:] = 0.0
    model.vote_choice = np.zeros(MIN_POPULATION, dtype=np.int8)
    model.vote_choice[0] = 1
    model.last_vote = np.zeros(MIN_POPULATION, dtype=np.int8)
    model.last_vote[1] = -1  # abstained this time, voted Blue before

    model.update_voter_states()

    assert model.party_identity[0] == pytest.approx(0.1)
    assert model.party_identity[1] == pytest.approx(0.0)
    assert model.last_vote[0] == 1
    assert model.last_vote[1] == -1  # abstention does not erase the earlier vote


def test_opinion_update_is_synchronous():
    """Every voter must move toward the *old* neighbour mean, not a partial update.

    Three voters in a line at -1, 0, +1 with social_influence 0.5.  Synchronously,
    the middle voter's neighbours average 0 so it stays put, while the outer two
    move halfway to 0.  Sequentially, the second voter would see an already-moved
    neighbour and land somewhere else.
    """
    model = make_model(social_network=True, social_influence=0.5, opinion_drift=0.0)
    n = MIN_POPULATION
    model.ideology = np.zeros(n)
    model.ideology[:3] = [-1.0, 0.0, 1.0]
    model.network = Network(n, np.array([[0, 1], [1, 2]]))
    model.vote_choice = np.zeros(n, dtype=np.int8)

    model.update_voter_states()

    assert model.ideology[0] == pytest.approx(-0.5)  # halfway from -1 to 0
    assert model.ideology[1] == pytest.approx(0.0)  # neighbours -1 and +1
    assert model.ideology[2] == pytest.approx(0.5)


def test_isolated_voters_keep_their_own_ideology():
    model = make_model(social_network=True, social_influence=0.5, opinion_drift=0.0)
    n = MIN_POPULATION
    model.ideology = np.linspace(-1, 1, n)
    original = model.ideology.copy()
    model.network = Network(n)  # no links at all
    model.vote_choice = np.zeros(n, dtype=np.int8)

    model.update_voter_states()

    assert np.allclose(model.ideology, original)


# -- summary statistics -------------------------------------------------------


def test_mean_margin_is_the_running_mean_of_recorded_margins():
    model = Model(Params(population=200), seed=3).run(20)
    margins = [record.margin for record in model.history]
    assert model.mean_margin == pytest.approx(float(np.mean(margins)))


def test_control_change_rate_divides_by_ticks_not_elections():
    """NetLogo computes the rate before incrementing the tick counter."""
    steps = 25
    model = Model(Params(population=200), seed=4).run(steps)

    winners = [record.winner for record in model.history]
    changes = sum(
        1
        for previous, current in zip(winners, winners[1:])
        if previous.split()[0] != current.split()[0]
    )

    assert model.party_control_changes == changes
    assert model.control_change_rate == pytest.approx(100.0 * changes / (steps - 1))


def test_switch_rate_counts_only_returning_voters():
    """Denominator is voters who turned out now and had voted at some earlier point."""
    model = make_model(base_turnout=1.0, turnout_sensitivity=0.0)
    model.last_vote = np.zeros(MIN_POPULATION, dtype=np.int8)
    model.last_vote[:10] = 1  # ten previous Red voters
    model.blue_position, model.red_position = -0.5, 0.5
    model.ideology[:] = -1.0  # everyone now strongly prefers Blue
    model.party_identity[:] = 0.0

    model.run_election()

    # All ten returning voters switched; the other 40 have no history and are
    # excluded from the denominator entirely.
    assert model.switch_rate == pytest.approx(100.0)


def test_first_election_has_no_control_change():
    model = Model(Params(population=100), seed=5).run(1)
    assert model.party_control_changes == 0
    assert model.control_change_rate == 0.0


# -- history and export -------------------------------------------------------


def test_history_has_one_row_per_election_with_netlogo_columns():
    model = Model(Params(population=100), seed=6).run(7)
    lines = model.history.to_lines()

    assert len(lines) == 8  # header + 7 elections
    assert lines[0].split("\t") == [
        "election",
        "winner",
        "blue-share",
        "red-share",
        "turnout",
        "margin",
        "blue-position",
        "red-position",
        "party-gap",
        "mean-ideology",
        "switch-rate",
    ]
    assert all(len(line.split("\t")) == 11 for line in lines)
    assert [line.split("\t")[0] for line in lines[1:]] == [str(i) for i in range(1, 8)]


def test_export_writes_the_file(tmp_path):
    model = Model(Params(population=100), seed=7).run(3)
    path = tmp_path / "history.tsv"

    assert model.history.export_tsv(path) == 3
    assert path.read_text().splitlines()[0].startswith("election\twinner")


def test_netlogo_precision_rounds_half_away_from_zero():
    """NetLogo's PRECISION is not Python's banker's rounding."""
    assert netlogo_precision(0.125, 2) == 0.13
    assert netlogo_precision(-0.125, 2) == -0.13
    assert netlogo_precision(2.5, 0) == 2.0 + 1.0
    assert round(2.5) == 2  # what we are deliberately not doing


def test_netlogo_number_drops_trailing_zero():
    assert netlogo_number(50.0) == "50"
    assert netlogo_number(50.125) == "50.125"
    assert netlogo_number(0.0) == "0"


# -- reproducibility ----------------------------------------------------------


def test_same_seed_gives_identical_runs():
    a = Model(Params(population=300), seed=99).run(20)
    b = Model(Params(population=300), seed=99).run(20)
    assert a.history.to_tsv() == b.history.to_tsv()


def test_different_seeds_diverge():
    a = Model(Params(population=300), seed=1).run(20)
    b = Model(Params(population=300), seed=2).run(20)
    assert a.history.to_tsv() != b.history.to_tsv()


# -- parameter validation -----------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"identity_strength": 2.5},  # above the slider maximum
        {"population": 10},  # below the slider minimum
        {"electorate_shape": "three-camp"},  # not on the chooser
        {"homophily": -0.1},
        {"persuadable_band": 0.0},  # slider starts at 0.01
    ],
)
def test_validate_rejects_values_outside_the_netlogo_interface(overrides):
    with pytest.raises(ValueError):
        Params(**overrides).validate()


def test_validate_accepts_the_netlogo_defaults():
    assert Params().validate() is not None
    assert Params.production_rules_defaults().validate().production_system is True


def test_unknown_metric_is_rejected():
    model = Model(Params(population=100), seed=1)
    with pytest.raises(ValueError, match="unknown metric"):
        model.metrics(("no_such_metric",))
