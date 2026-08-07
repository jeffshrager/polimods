"""Network construction and neighbour aggregation.

The interesting claim is that ``homophily`` does what it says: at 0 the network is
blind to ideology, at 1 acceptance falls linearly with ideological distance.  The
assortativity test below is what would catch a sign error that no unit test of the
acceptance formula alone would notice.
"""

from __future__ import annotations

import numpy as np
import pytest

from polimods import Model, Network, Params, build_network


def rng(seed=0):
    return np.random.default_rng(seed)


def ideologies(n=500, seed=0):
    return np.clip(np.random.default_rng(seed).normal(0, 0.25, n), -1, 1)


def test_builds_the_requested_number_of_links():
    """target_links = round(n * degree / 2), so mean degree lands on the setting."""
    voters = ideologies(500)
    network = build_network(rng(), voters, network_degree=6, homophily=0.0)

    assert len(network) == 1500
    assert network.mean_degree == pytest.approx(6.0)


def test_mean_degree_matches_the_setting_under_homophily():
    """Homophily changes *who* links, not how many links there are."""
    voters = ideologies(500)
    for homophily in (0.0, 0.5, 1.0):
        network = build_network(rng(1), voters, network_degree=6, homophily=homophily)
        assert network.mean_degree == pytest.approx(6.0)


def assortativity(voters: np.ndarray, homophily: float, seed: int) -> float:
    """Correlation between the ideologies of linked voters."""
    network = build_network(rng(seed), voters, network_degree=8, homophily=homophily)
    return float(np.corrcoef(voters[network.src], voters[network.dst])[0, 1])


def two_camp(n=800, polarization=0.6, spread=0.15, seed=3):
    centers = np.random.default_rng(seed + 100).choice([-polarization, polarization], n)
    return np.clip(np.random.default_rng(seed).normal(centers, spread), -1, 1)


def test_homophily_raises_ideological_assortativity():
    """Assortativity must rise monotonically with homophily.

    The effect is modest in a single-peaked electorate and that is not a defect:
    acceptance is ``1 - |Ia - Ib| / 2``, so when ideologies cluster near the centre
    the filter has little distance to work with.  The monotone ordering is the
    claim; the magnitude depends on the electorate.
    """
    voters = ideologies(800, seed=3)
    seeds = range(6)

    neutral = np.mean([assortativity(voters, 0.0, s) for s in seeds])
    middling = np.mean([assortativity(voters, 0.5, s) for s in seeds])
    total = np.mean([assortativity(voters, 1.0, s) for s in seeds])

    assert abs(neutral) < 0.03  # blind to ideology
    assert neutral < middling < total
    assert total > 0.05


def test_homophily_sorts_a_polarized_electorate_much_harder():
    """Two well-separated camps give the acceptance rule real distance to bite on."""
    voters = two_camp()
    seeds = range(6)

    neutral = np.mean([assortativity(voters, 0.0, s) for s in seeds])
    total = np.mean([assortativity(voters, 1.0, s) for s in seeds])

    assert abs(neutral) < 0.03
    assert total > 0.3


def test_no_self_loops_or_duplicate_links():
    voters = ideologies(200)
    network = build_network(rng(4), voters, network_degree=10, homophily=0.7)

    assert not np.any(network.edges[:, 0] == network.edges[:, 1])
    pairs = {tuple(sorted(edge)) for edge in network.edges.tolist()}
    assert len(pairs) == len(network.edges)


def test_zero_degree_gives_an_empty_network():
    network = build_network(rng(), ideologies(100), network_degree=0, homophily=0.5)
    assert len(network) == 0
    assert network.mean_degree == 0.0
    assert not network.has_neighbors.any()


def test_neighbor_mean_uses_the_fallback_for_isolated_voters():
    values = np.array([0.0, 1.0, 2.0, 9.0])
    network = Network(4, np.array([[0, 1], [1, 2]]))

    result = network.neighbor_mean(values, fallback=values)

    assert result[0] == pytest.approx(1.0)  # only neighbour is voter 1
    assert result[1] == pytest.approx(1.0)  # mean of 0.0 and 2.0
    assert result[2] == pytest.approx(1.0)
    assert result[3] == pytest.approx(9.0)  # isolated: keeps its own value


def test_neighbor_fraction_marks_empty_denominators_invalid():
    network = Network(4, np.array([[0, 1], [0, 2]]))
    last_vote = np.array([0, 1, -1, 0], dtype=np.int8)

    fraction, valid = network.neighbor_fraction(last_vote == 1, last_vote != 0)

    assert valid[0] and fraction[0] == pytest.approx(0.5)
    assert not valid[3]  # voter 3 has no links at all


def test_degree_counts_both_directions():
    network = Network(3, np.array([[0, 1], [1, 2]]))
    assert network.degree.tolist() == [1, 2, 1]


def test_switching_the_network_off_between_elections_drops_the_links():
    """NetLogo re-reads the switch every GO, so the port must too."""
    model = Model(Params(population=200, social_network=True), seed=1)
    model.step()
    assert len(model.network) > 0

    model.params = model.params.replace(social_network=False)
    model.step()
    assert len(model.network) == 0


def test_switching_the_network_on_between_elections_builds_it():
    model = Model(Params(population=200, social_network=False), seed=1)
    model.step()
    assert len(model.network) == 0

    model.params = model.params.replace(social_network=True)
    model.step()
    assert len(model.network) == 600  # 200 voters * degree 6 / 2


def test_rebuild_network_replaces_the_links():
    model = Model(Params(population=200, social_network=True), seed=1)
    first = model.network.edges.copy()
    model.build_network()
    assert not np.array_equal(first, model.network.edges)
    assert len(model.network) == len(first)
