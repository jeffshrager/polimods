"""The adaptive two-party competition model.

A direct port of ``adaptive_two_party_model_production_rules.nlogo``.  Each method
below corresponds to a NetLogo procedure of the same name, in the same order, so
the two sources can be read side by side.

One tick is one election.  Voters decide whether to vote and, if so, for whom;
the losing party then adapts toward voters it nearly won or toward its own base;
finally voter identity and ideology update before the next election.

Voters are stored as parallel numpy arrays rather than turtle objects.  This is
safe because every voter-level computation in the NetLogo is independent of
execution order -- ``run-election`` reads only each voter's own state, and opinion
updating is explicitly synchronous.  The one place order matters, network
construction, stays sequential in :mod:`polimods.network`.

The political state is ``ideology``, ``party_identity``, ``blue_position``, and
``red_position``.  NetLogo's ``xcor``/``ycor`` display layer is not ported: the
model never reads it, so it is a visualization of the model rather than part of it.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .history import ElectionRecord, History
from .network import Network, build_network
from .params import Params
from .rules import Decision, run_production_system

#: Minimum separation enforced between the parties by ``enforce-party-order``.
MINIMUM_PARTY_GAP = 0.02


def clamp_value(value, minimum, maximum):
    """NetLogo's ``clamp-value`` reporter."""
    return np.clip(value, minimum, maximum)


class Model:
    """One run of the model, from SETUP to an arbitrary number of elections."""

    def __init__(
        self,
        params: Params | None = None,
        seed: Any = None,
        *,
        trace: bool = False,
        validate: bool = True,
    ):
        self.params = (params or Params())
        if validate:
            self.params.validate()
        self.rng = np.random.default_rng(seed)
        self.trace = trace
        self.setup()

    # -- setup ---------------------------------------------------------------

    def setup(self) -> "Model":
        p = self.params

        self.blue_position = float(clamp_value(-p.initial_party_gap / 2, -1, 1))
        self.red_position = float(clamp_value(p.initial_party_gap / 2, -1, 1))

        self.blue_votes = 0
        self.red_votes = 0
        self.total_votes = 0
        self.blue_share = 50.0
        self.red_share = 50.0
        self.turnout_rate = 0.0
        self.election_margin = 0.0
        self.switch_rate = 0.0
        self.winner_id = 0
        self.winner_name = "none yet"

        self.cumulative_margin = 0.0
        self.mean_margin = 0.0
        self.party_control_changes = 0
        self.last_winner_id = 0
        self.control_change_rate = 0.0
        self.party_gap = self.red_position - self.blue_position
        self.mean_voter_ideology = 0.0

        self.ticks = 0
        self.history = History()
        self.decision: Decision | None = None

        self.setup_voters()
        self.network = Network(p.population)
        if p.social_network:
            self.build_network()

        return self

    def setup_voters(self) -> None:
        p = self.params
        n = p.population

        centers = np.zeros(n)
        if p.electorate_shape == "two-camp":
            # Each voter independently joins one of the two camps.
            centers = self.rng.choice(
                np.array([-p.electorate_polarization, p.electorate_polarization]),
                size=n,
            )

        self.ideology = clamp_value(
            self.rng.normal(centers, p.ideology_spread), -1, 1
        )
        self.party_identity = clamp_value(
            self.ideology + self.rng.normal(0.0, p.identity_noise, size=n), -1, 1
        )

        self.choice_score = np.zeros(n)
        self.turnout_probability = np.zeros(n)
        self.vote_choice = np.zeros(n, dtype=np.int8)
        self.last_vote = np.zeros(n, dtype=np.int8)
        self.voted = np.zeros(n, dtype=bool)
        self.next_ideology = self.ideology.copy()

        self.mean_voter_ideology = float(self.ideology.mean()) if n else 0.0

    # -- the election cycle ---------------------------------------------------

    def step(self) -> "Model":
        """One call to NetLogo's ``go``: one complete election."""
        if self.params.population == 0:
            return self

        # Let switches take effect even if changed after SETUP.
        if not self.params.social_network and len(self.network):
            self.network = Network(self.params.population)
        if (
            self.params.social_network
            and self.params.network_degree > 0
            and not len(self.network)
        ):
            self.build_network()

        self.run_election()
        self.adapt_parties()
        self.update_voter_states()
        self.update_summary_statistics()
        self.record_history()
        self.ticks += 1
        return self

    def run(self, steps: int) -> "Model":
        for _ in range(steps):
            self.step()
        return self

    def run_election(self) -> None:
        p = self.params

        if p.production_system:
            decision = run_production_system(
                params=p,
                rng=self.rng,
                ideology=self.ideology,
                party_identity=self.party_identity,
                last_vote=self.last_vote,
                blue_position=self.blue_position,
                red_position=self.red_position,
                network=self.network,
                trace=self.trace,
            )
        else:
            decision = self.run_weighted_choice_model()

        self.decision = decision
        self.choice_score = decision.choice_score
        self.turnout_probability = decision.turnout_probability
        self.voted = decision.voted
        self.vote_choice = decision.vote_choice

        # Vote switching is measured among voters who turned out this election and
        # had cast a non-abstaining ballot at some point before it.
        repeat_voters = self.voted & (self.last_vote != 0)
        repeat_count = int(repeat_voters.sum())
        if repeat_count:
            switched = int(
                (self.vote_choice[repeat_voters] != self.last_vote[repeat_voters]).sum()
            )
            self.switch_rate = 100.0 * switched / repeat_count
        else:
            self.switch_rate = 0.0

        self.blue_votes = int((self.vote_choice == -1).sum())
        self.red_votes = int((self.vote_choice == 1).sum())
        self.total_votes = self.blue_votes + self.red_votes
        self.turnout_rate = 100.0 * self.total_votes / p.population

        if self.total_votes > 0:
            self.blue_share = 100.0 * self.blue_votes / self.total_votes
            self.red_share = 100.0 * self.red_votes / self.total_votes
        else:
            self.blue_share = 50.0
            self.red_share = 50.0

        self.election_margin = abs(self.blue_share - self.red_share)

        if self.red_votes > self.blue_votes:
            self.winner_id = 1
            self.winner_name = "Red"
        elif self.blue_votes > self.red_votes:
            self.winner_id = -1
            self.winner_name = "Blue"
        else:
            self.winner_id = int(self.rng.choice(np.array([-1, 1])))
            self.winner_name = (
                "Blue (tie-break)" if self.winner_id == -1 else "Red (tie-break)"
            )

    def run_weighted_choice_model(self) -> Decision:
        """The original continuous voter model, retained for direct comparison."""
        p = self.params
        n = p.population

        choice_score = (
            np.abs(self.ideology - self.blue_position)
            - np.abs(self.ideology - self.red_position)
            + p.identity_strength * self.party_identity
            + self.rng.normal(0.0, p.election_noise, size=n)
        )

        turnout_probability = clamp_value(
            p.base_turnout + p.turnout_sensitivity * np.abs(choice_score), 0, 1
        )

        voted = self.rng.random(n) < turnout_probability

        # A score of exactly zero goes to Red, as in NetLogo's IFELSE.
        intended_choice = np.where(choice_score < 0, -1, 1).astype(np.int8)
        vote_choice = np.where(voted, intended_choice, 0).astype(np.int8)

        return Decision(
            choice_score=choice_score,
            intended_choice=intended_choice,
            turnout_probability=turnout_probability,
            voted=voted,
            vote_choice=vote_choice,
        )

    # -- party adaptation -----------------------------------------------------

    def adapt_parties(self) -> None:
        if not self.params.adaptive_parties:
            return

        if self.winner_id == 1:
            self.move_losing_party(-1)
            self.move_winning_party(1)

        if self.winner_id == -1:
            self.move_losing_party(1)
            self.move_winning_party(-1)

        self.enforce_party_order()

    def move_losing_party(self, loser_id: int) -> None:
        p = self.params
        opposing_id = -loser_id

        supporters = self.vote_choice == loser_id
        opposing_voters = self.vote_choice == opposing_id
        persuadables = opposing_voters & (
            np.abs(self.choice_score) <= p.persuadable_band
        )

        # With no narrowly-lost voters to chase, the party falls back to the whole
        # electorate's centre of gravity.
        electoral_target = float(self.ideology.mean())
        if persuadables.any():
            electoral_target = float(self.ideology[persuadables].mean())

        base_target = electoral_target
        if supporters.any():
            base_target = float(self.ideology[supporters].mean())

        # BASE-PRESSURE = 0 means chase narrowly lost voters.
        # BASE-PRESSURE = 1 means move toward current supporters instead.
        target = (1 - p.base_pressure) * electoral_target + p.base_pressure * base_target

        if loser_id == -1:
            self.blue_position += p.party_adaptation * (target - self.blue_position)
        if loser_id == 1:
            self.red_position += p.party_adaptation * (target - self.red_position)

    def move_winning_party(self, winning_id: int) -> None:
        p = self.params
        if p.winner_base_adaptation <= 0:
            return

        supporters = self.vote_choice == winning_id
        if not supporters.any():
            return
        target = float(self.ideology[supporters].mean())

        if winning_id == -1:
            self.blue_position += p.winner_base_adaptation * (
                target - self.blue_position
            )
        if winning_id == 1:
            self.red_position += p.winner_base_adaptation * (target - self.red_position)

    def enforce_party_order(self) -> None:
        self.blue_position = float(clamp_value(self.blue_position, -1, 1))
        self.red_position = float(clamp_value(self.red_position, -1, 1))

        # Keep the named Blue party to the left of the named Red party.
        if self.blue_position > self.red_position - MINIMUM_PARTY_GAP:
            midpoint = (self.blue_position + self.red_position) / 2
            self.blue_position = float(clamp_value(midpoint - 0.01, -1, 1))
            self.red_position = float(clamp_value(midpoint + 0.01, -1, 1))

    # -- voter updating -------------------------------------------------------

    def update_voter_states(self) -> None:
        p = self.params

        # Voting can reinforce partisan identity, producing path dependence.
        # Abstainers are untouched, so an abstention does not erase a prior vote.
        participated = self.vote_choice != 0
        if participated.any():
            self.party_identity[participated] = clamp_value(
                (1 - p.identity_reinforcement) * self.party_identity[participated]
                + p.identity_reinforcement * self.vote_choice[participated],
                -1,
                1,
            )
            self.last_vote[participated] = self.vote_choice[participated]

        # Opinion updating is synchronous: everyone computes NEXT-IDEOLOGY from the
        # old state before any voter adopts its new value.
        peer_mean = self.ideology
        if p.social_network and len(self.network):
            peer_mean = self.network.neighbor_mean(self.ideology, self.ideology)

        self.next_ideology = clamp_value(
            self.ideology
            + p.social_influence * (peer_mean - self.ideology)
            + self.rng.normal(0.0, p.opinion_drift, size=p.population),
            -1,
            1,
        )
        self.ideology = self.next_ideology

    def update_summary_statistics(self) -> None:
        self.cumulative_margin += self.election_margin
        self.mean_margin = self.cumulative_margin / (self.ticks + 1)

        if self.last_winner_id != 0 and self.winner_id != self.last_winner_id:
            self.party_control_changes += 1
        self.last_winner_id = self.winner_id

        if self.ticks > 0:
            self.control_change_rate = 100.0 * self.party_control_changes / self.ticks
        else:
            self.control_change_rate = 0.0

        self.party_gap = self.red_position - self.blue_position
        self.mean_voter_ideology = float(self.ideology.mean())

    def record_history(self) -> None:
        # Like mean_ideology, the distribution fields describe the electorate as
        # it stands at the end of the election -- after update_voter_states has
        # moved everyone -- split by how they voted during it.
        p10, p50, p90 = (
            np.percentile(self.ideology, (10, 50, 90))
            if len(self.ideology)
            else (0.0, 0.0, 0.0)
        )
        self.history.append(
            ElectionRecord(
                election=self.ticks + 1,
                winner=self.winner_name,
                blue_share=self.blue_share,
                red_share=self.red_share,
                turnout_rate=self.turnout_rate,
                margin=self.election_margin,
                blue_position=self.blue_position,
                red_position=self.red_position,
                party_gap=self.party_gap,
                mean_ideology=self.mean_voter_ideology,
                switch_rate=self.switch_rate,
                ideology_sd=self.ideology_sd,
                ideology_p10=float(p10),
                ideology_p50=float(p50),
                ideology_p90=float(p90),
                blue_voter_ideology=self._camp_mean(-1),
                red_voter_ideology=self._camp_mean(1),
                mean_identity=(
                    float(self.party_identity.mean()) if len(self.party_identity) else 0.0
                ),
            )
        )

    def _camp_mean(self, choice: int) -> float:
        """Mean ideology of the voters who chose ``choice``; NaN if there are none."""
        voters = self.vote_choice == choice
        return float(self.ideology[voters].mean()) if voters.any() else float("nan")

    # -- network and manual controls -----------------------------------------

    def build_network(self) -> None:
        """Port of NetLogo's ``build-network`` / REBUILD NETWORK button."""
        p = self.params
        if not p.social_network or p.network_degree <= 0:
            self.network = Network(p.population)
            return
        self.network = build_network(
            self.rng, self.ideology, p.network_degree, p.homophily
        )

    def reset_party_positions(self) -> None:
        """Port of the RESET PARTY POSITIONS button."""
        p = self.params
        self.blue_position = float(clamp_value(-p.initial_party_gap / 2, -1, 1))
        self.red_position = float(clamp_value(p.initial_party_gap / 2, -1, 1))
        self.enforce_party_order()
        self.party_gap = self.red_position - self.blue_position

    # -- reporters ------------------------------------------------------------

    #: Everything the jig can record as a metric, matching the NetLogo monitor and
    #: BehaviorSpace reporter names (hyphens become underscores).
    METRICS = (
        "ticks",
        "winner_id",
        "blue_share",
        "red_share",
        "turnout_rate",
        "election_margin",
        "mean_margin",
        "party_control_changes",
        "control_change_rate",
        "blue_position",
        "red_position",
        "party_gap",
        "mean_voter_ideology",
        "ideology_sd",
        "switch_rate",
        "mean_degree",
        "link_count",
    )

    @property
    def ideology_sd(self) -> float:
        """Dispersion of the electorate.

        Not a NetLogo monitor, but the electorate's *mean* ideology is pinned near
        zero by symmetry in both electorate shapes, so it cannot show whether
        social influence is pulling voters together.  Spread can.
        """
        return float(self.ideology.std()) if len(self.ideology) else 0.0

    @property
    def mean_degree(self) -> float:
        return self.network.mean_degree

    @property
    def link_count(self) -> int:
        return len(self.network)

    def metrics(self, names: tuple[str, ...] | list[str] | None = None) -> dict[str, Any]:
        names = tuple(names) if names is not None else self.METRICS
        unknown = [n for n in names if n not in self.METRICS]
        if unknown:
            raise ValueError(
                f"unknown metric(s): {', '.join(unknown)}. "
                f"Available: {', '.join(self.METRICS)}"
            )
        return {name: getattr(self, name) for name in names}
