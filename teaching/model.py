"""
================================================================================
 MODEL -- the simulation loop
================================================================================
This is the file that actually *runs* the model. Everything else in this
directory (params.py, network.py, rules.py, history.py) is a supporting
character; this is where they get called in the right order, once per
election.

THE BIG PICTURE, before any code: this is a model of repeated two-party
elections. One "tick" is one election. Each election:

  1. Every voter decides whether to vote, and if so, for Blue or Red
     (run_election -- delegates to either the continuous weighted-choice
     equation below, or the eight-rule production system in rules.py,
     depending on params.production_system).
  2. The *losing* party shifts its platform toward voters it might be able
     to win next time; the *winning* party drifts slightly too
     (adapt_parties / move_losing_party / move_winning_party).
  3. Voters' partisan identity and ideology update for next time: voting
     can reinforce identity, and ideology can drift toward one's social
     network (update_voter_states).
  4. Summary statistics are recomputed and one row is appended to History
     (update_summary_statistics / record_history).

Do this hundreds of times (Model.run(n)) and you get a trajectory: does the
electorate stay put or drift? Do the two parties converge to the centre or
stay polarized? Does one party keep winning, or does control flip back and
forth?

DESIGN NOTE ON PERFORMANCE: every voter is a *row* in a set of parallel
numpy arrays (self.ideology, self.party_identity, self.vote_choice, ...) --
there is no "Voter" object. This is what lets an election for a population
of 500-2000 voters run as a handful of vectorized array operations instead
of a Python loop over each voter. That's safe here because nothing about
one voter's election-day computation depends on the order voters are
processed in -- the one genuinely order-dependent step, building the social
network, is deliberately kept sequential and lives in network.py instead.

This file was originally a line-by-line port of a NetLogo model
(adaptive_two_party_model_production_rules.nlogo): each method below
corresponds to one NetLogo procedure of the same name, in the same order, so
the two sources could be read side by side during the port. That NetLogo
provenance still shows in some naming and ordering choices below, even
though this Python version is now the actively developed implementation.
================================================================================
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .history import ElectionRecord, History
from .network import Network, build_network
from .params import Params
from .rules import Decision, run_production_system

#: The two parties are never allowed to sit closer together than this on the
#: ideology line (see enforce_party_order below) -- a floor under
#: convergence, not a realistic claim, just a guard against them collapsing
#: onto literally the same point.
MINIMUM_PARTY_GAP = 0.02


def clamp_value(value, minimum, maximum):
    """Restrict `value` to [minimum, maximum]. Ideology, identity, and party
    positions in this model all live on a bounded axis from -1 (fully Blue)
    to +1 (fully Red); this is the function that enforces those bounds
    everywhere they'd otherwise be violated by an update (e.g. adding noise
    could push a voter's ideology past +1 without this)."""
    return np.clip(value, minimum, maximum)


class Model:
    """One complete run of the model, from initial setup through however
    many elections you ask it to simulate.

    Typical usage::

        m = Model(Params(population=500), seed=1)
        m.run(100)                  # simulate 100 elections
        m.history.to_dicts()        # inspect every election's results
    """

    def __init__(
        self,
        params: Params | None = None,
        seed: Any = None,
        *,
        trace: bool = False,
        validate: bool = True,
    ):
        # Falls back to Params()'s defaults if none given.
        self.params = (params or Params())
        if validate:
            # Catch a bad Params (out-of-range slider value, etc.) here,
            # before any simulation work happens -- see Params.validate's
            # docstring for why that matters for sweeps of many runs.
            self.params.validate()

        # One numpy random Generator drives *every* random draw in this run
        # (voter placement, election noise, tie-breaks, network wiring).
        # Passing the same `seed` always reproduces the same run bit-for-bit
        # -- essential for debugging a specific surprising trajectory, and
        # for the experiment jig's reproducibility guarantees.
        self.rng = np.random.default_rng(seed)

        # If True, rules.py additionally records a human-readable "why did
        # this voter do that" string per voter per election (expensive;
        # off by default).
        self.trace = trace

        self.setup()

    # =========================================================================
    # SETUP -- everything that happens once, before the first election.
    # =========================================================================

    def setup(self) -> "Model":
        """(Re)initialize the whole model to its starting state: place the
        two parties, generate the electorate, and build the social network
        if one is configured. Called automatically by __init__; calling it
        again would restart the run from scratch with the same params and
        rng (continuing to draw from wherever the rng currently is)."""
        p = self.params

        # Parties start symmetric around the centre (0), initial_party_gap
        # apart. clamp_value here mostly matters for very large gaps that
        # would otherwise push a party past the +/-1 ideology bound.
        self.blue_position = float(clamp_value(-p.initial_party_gap / 2, -1, 1))
        self.red_position = float(clamp_value(p.initial_party_gap / 2, -1, 1))

        # Per-election result fields. These get overwritten every election
        # by run_election/update_summary_statistics; the values here are
        # just sensible "before the first election has happened" starting
        # points (e.g. a 50/50 vote share with nobody having voted yet).
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

        # Running totals across the whole run so far.
        self.cumulative_margin = 0.0
        self.mean_margin = 0.0
        self.party_control_changes = 0
        self.last_winner_id = 0
        self.control_change_rate = 0.0
        self.party_gap = self.red_position - self.blue_position
        self.mean_voter_ideology = 0.0

        self.ticks = 0  # number of elections completed so far
        self.history = History()
        self.decision: Decision | None = None  # last election's raw Decision object

        self.setup_voters()

        # The network object always exists (possibly with zero edges) so
        # downstream code never has to special-case "no network configured"
        # vs. "network configured but not built yet."
        self.network = Network(p.population)
        if p.social_network:
            self.build_network()

        return self

    def setup_voters(self) -> None:
        """Generate the initial electorate: every voter's starting ideology
        and partisan identity, plus empty per-voter arrays for everything
        that gets filled in once elections start happening."""
        p = self.params
        n = p.population

        # Where is each voter's ideology centred *before* individual noise
        # is added? For a single-peaked electorate, everyone is centred on
        # 0 (one bell curve). For a two-camp electorate, each voter
        # independently and randomly joins one of the two camp centres
        # (-electorate_polarization or +electorate_polarization) -- so the
        # *population* ends up roughly split 50/50 between camps, even
        # though no single voter "decides" the split; it falls out of n
        # independent coin flips.
        centers = np.zeros(n)
        if p.electorate_shape == "two-camp":
            centers = self.rng.choice(
                np.array([-p.electorate_polarization, p.electorate_polarization]),
                size=n,
            )

        # Each voter's actual ideology: their camp centre plus independent
        # Gaussian noise (ideology_spread controls how tightly clustered
        # around the centre each camp is), clamped to the [-1, 1] axis.
        self.ideology = clamp_value(
            self.rng.normal(centers, p.ideology_spread), -1, 1
        )
        # Partisan identity starts as a noisy copy of ideology -- most
        # voters' declared identity roughly matches their actual views, but
        # identity_noise lets the two diverge from the very start (e.g. a
        # centrist voter who nonetheless identifies strongly as a partisan).
        self.party_identity = clamp_value(
            self.ideology + self.rng.normal(0.0, p.identity_noise, size=n), -1, 1
        )

        # Per-voter election-outcome arrays, all starting "blank" (nobody
        # has voted yet). These get overwritten by run_election every tick.
        self.choice_score = np.zeros(n)
        self.turnout_probability = np.zeros(n)
        self.vote_choice = np.zeros(n, dtype=np.int8)   # -1 Blue, 0 abstained, 1 Red
        self.last_vote = np.zeros(n, dtype=np.int8)     # vote_choice as of the last time they voted
        self.voted = np.zeros(n, dtype=bool)
        self.next_ideology = self.ideology.copy()

        self.mean_voter_ideology = float(self.ideology.mean()) if n else 0.0

    # =========================================================================
    # THE ELECTION CYCLE -- what happens on every tick (Model.step).
    # =========================================================================

    def step(self) -> "Model":
        """Simulate exactly one election, in five phases: hold the election,
        let the losing/winning parties adapt, update voters for next time,
        recompute summary statistics, and log the result to history."""
        if self.params.population == 0:
            return self  # nothing to simulate with zero voters

        # If social_network was toggled after setup() ran (e.g. interactively,
        # or between conditions in an experiment sweep reusing a Model), make
        # sure the network reflects the *current* setting rather than
        # whatever was true when setup() last ran: tear it down if the
        # network was switched off, or build it if it was switched on and
        # hasn't been built yet.
        if not self.params.social_network and len(self.network):
            self.network = Network(self.params.population)
        if (
            self.params.social_network
            and self.params.network_degree > 0
            and not len(self.network)
        ):
            self.build_network()

        self.run_election()             # 1. who votes, and for whom
        self.adapt_parties()            # 2. parties respond to the result
        self.update_voter_states()      # 3. voters update for next time
        self.update_summary_statistics()  # 4. running totals/rates
        self.record_history()           # 5. log this election
        self.ticks += 1
        return self

    def run(self, steps: int) -> "Model":
        """Simulate `steps` elections in a row -- the usual entry point for
        actually running the model, e.g. Model(params, seed=1).run(100)."""
        for _ in range(steps):
            self.step()
        return self

    # -------------------------------------------------------------------
    # Phase 1: the election itself.
    # -------------------------------------------------------------------

    def run_election(self) -> None:
        """Decide every voter's turnout and vote choice, then tally the
        result into party vote shares and a winner.

        This is the branch point between the model's two different theories
        of how voters decide: the eight-rule production system in rules.py
        (when params.production_system is True) or the continuous
        weighted-choice equation below (when it's False). Both return a
        Decision object with the same shape, so everything downstream of
        this point doesn't need to know which one was used.
        """
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

        # "Switching" only makes sense for a voter who (a) actually cast a
        # ballot this election and (b) has a prior non-abstaining vote to
        # compare against. A first-time voter, or one who only ever
        # abstained before, can't be said to have "switched."
        repeat_voters = self.voted & (self.last_vote != 0)
        repeat_count = int(repeat_voters.sum())
        if repeat_count:
            switched = int(
                (self.vote_choice[repeat_voters] != self.last_vote[repeat_voters]).sum()
            )
            self.switch_rate = 100.0 * switched / repeat_count
        else:
            self.switch_rate = 0.0

        # Tally raw vote counts and shares.
        self.blue_votes = int((self.vote_choice == -1).sum())
        self.red_votes = int((self.vote_choice == 1).sum())
        self.total_votes = self.blue_votes + self.red_votes
        self.turnout_rate = 100.0 * self.total_votes / p.population

        if self.total_votes > 0:
            self.blue_share = 100.0 * self.blue_votes / self.total_votes
            self.red_share = 100.0 * self.red_votes / self.total_votes
        else:
            # Nobody voted at all (can happen with extreme turnout
            # settings) -- report a neutral 50/50 rather than dividing by
            # zero.
            self.blue_share = 50.0
            self.red_share = 50.0

        self.election_margin = abs(self.blue_share - self.red_share)

        # Winner determination, with a random tie-break if the vote counts
        # come out exactly equal (winner_id: -1 = Blue, +1 = Red).
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
        """The model's *other* theory of vote choice: a single continuous
        equation, rather than rules.py's eight discrete IF-THEN rules. Kept
        alongside the production system specifically so the two can be
        compared head-to-head on the same electorate.

        Each voter's choice_score combines three continuous terms:
          - policy distance:  how much closer Blue is than Red (or vice
            versa) on the ideology line;
          - identity:         identity_strength * party_identity, i.e. how
            strongly and in which direction their declared identity pulls;
          - noise:            idiosyncratic randomness (election_noise).

        Unlike the production system's whole-number reason counts, this
        score is a smooth real number -- a voter 0.01 past a threshold and
        one far past it get correspondingly different scores, not the same
        flat credit.
        """
        p = self.params
        n = p.population

        choice_score = (
            np.abs(self.ideology - self.blue_position)
            - np.abs(self.ideology - self.red_position)
            + p.identity_strength * self.party_identity
            + self.rng.normal(0.0, p.election_noise, size=n)
        )

        # Turnout probability rises with how *strong* a voter's preference
        # is (the magnitude of choice_score), regardless of which way it
        # points -- strongly-decided voters are more likely to show up than
        # near-indifferent ones.
        turnout_probability = clamp_value(
            p.base_turnout + p.turnout_sensitivity * np.abs(choice_score), 0, 1
        )

        voted = self.rng.random(n) < turnout_probability

        # A choice_score of exactly zero (a perfect tie between the two
        # parties) is assigned to Red, not resolved randomly -- this
        # mirrors an IFELSE branch in the original NetLogo code, where
        # "not negative" fell through to the Red branch. It's a real, if
        # small, asymmetry: Red benefits from perfect ties.
        intended_choice = np.where(choice_score < 0, -1, 1).astype(np.int8)
        vote_choice = np.where(voted, intended_choice, 0).astype(np.int8)

        return Decision(
            choice_score=choice_score,
            intended_choice=intended_choice,
            turnout_probability=turnout_probability,
            voted=voted,
            vote_choice=vote_choice,
        )

    # -------------------------------------------------------------------
    # Phase 2: party adaptation -- how Blue and Red respond to the result.
    # -------------------------------------------------------------------

    def adapt_parties(self) -> None:
        """After an election, the loser adjusts its platform to try to do
        better next time, and the winner drifts slightly toward its own
        base. Does nothing at all if adaptive_parties is off (a "frozen
        two-party system" baseline)."""
        if not self.params.adaptive_parties:
            return

        if self.winner_id == 1:      # Red won -> Blue lost
            self.move_losing_party(-1)
            self.move_winning_party(1)

        if self.winner_id == -1:     # Blue won -> Red lost
            self.move_losing_party(1)
            self.move_winning_party(-1)

        self.enforce_party_order()

    def move_losing_party(self, loser_id: int) -> None:
        """Shift the losing party's position toward a target that blends
        two different notions of "who to chase":

          - electoral_target: the mean ideology of "persuadable" voters --
            opposing-party voters whose choice_score was close enough to
            zero (within persuadable_band) that they plausibly could have
            been won. If there are none, falls back to the mean ideology of
            the *entire* electorate (better than not moving at all).

          - base_target: the mean ideology of the losing party's own
            current supporters -- i.e. "shore up the base" instead of
            chasing the centre.

        `base_pressure` (a Params field, 0..1) blends between the two:
        base_pressure=0 means chase persuadable voters entirely;
        base_pressure=1 means retreat to the base entirely. The party then
        moves a `party_adaptation` fraction of the remaining distance to
        that blended target -- 0 means don't move at all, 1 means jump
        straight there in one election.
        """
        p = self.params
        opposing_id = -loser_id

        supporters = self.vote_choice == loser_id
        opposing_voters = self.vote_choice == opposing_id
        persuadables = opposing_voters & (
            np.abs(self.choice_score) <= p.persuadable_band
        )

        electoral_target = float(self.ideology.mean())
        if persuadables.any():
            electoral_target = float(self.ideology[persuadables].mean())

        base_target = electoral_target
        if supporters.any():
            base_target = float(self.ideology[supporters].mean())

        # base_pressure = 0 -> chase narrowly-lost (persuadable) voters.
        # base_pressure = 1 -> move toward current supporters instead.
        target = (1 - p.base_pressure) * electoral_target + p.base_pressure * base_target

        if loser_id == -1:
            self.blue_position += p.party_adaptation * (target - self.blue_position)
        if loser_id == 1:
            self.red_position += p.party_adaptation * (target - self.red_position)

    def move_winning_party(self, winning_id: int) -> None:
        """The winning party ALSO moves, slightly, toward its own
        supporters' mean ideology -- at rate winner_base_adaptation, which
        defaults much smaller than party_adaptation.

        This matters more than it might look: because this runs even when
        party_adaptation is set to 0, "party_adaptation=0" is NOT a true
        "the parties never move" control -- the winner still creeps toward
        its base every single election via this separate rate. Anyone
        reading results at party_adaptation=0 and expecting frozen party
        positions will be surprised; they aren't frozen unless
        winner_base_adaptation is *also* 0.
        """
        p = self.params
        if p.winner_base_adaptation <= 0:
            return

        supporters = self.vote_choice == winning_id
        if not supporters.any():
            return  # no supporters to compute a target from
        target = float(self.ideology[supporters].mean())

        if winning_id == -1:
            self.blue_position += p.winner_base_adaptation * (
                target - self.blue_position
            )
        if winning_id == 1:
            self.red_position += p.winner_base_adaptation * (target - self.red_position)

    def enforce_party_order(self) -> None:
        """Two housekeeping guarantees after any party movement: (1) clamp
        both parties back onto the [-1, 1] ideology axis, and (2) never let
        Blue drift to the right of Red (or the two collapse onto the same
        point) -- if adaptation would put them within MINIMUM_PARTY_GAP of
        each other, snap them apart to sit symmetrically around their
        midpoint instead. This preserves "Blue is the left party, Red is
        the right party" as an invariant that always holds, even under
        aggressive adaptation settings that might otherwise cross them."""
        self.blue_position = float(clamp_value(self.blue_position, -1, 1))
        self.red_position = float(clamp_value(self.red_position, -1, 1))

        if self.blue_position > self.red_position - MINIMUM_PARTY_GAP:
            midpoint = (self.blue_position + self.red_position) / 2
            self.blue_position = float(clamp_value(midpoint - 0.01, -1, 1))
            self.red_position = float(clamp_value(midpoint + 0.01, -1, 1))

    # -------------------------------------------------------------------
    # Phase 3: voter updating -- identity reinforcement and ideology drift.
    # -------------------------------------------------------------------

    def update_voter_states(self) -> None:
        """After the election and party adaptation, update every voter for
        next time in two independent ways:

          1. Identity reinforcement: voting for a party pulls a voter's
             declared identity slightly toward that party (a positive
             feedback loop -- vote Red enough times and your identity
             number drifts toward +1). Abstainers are left untouched, so
             abstaining does NOT erase a voter's prior partisan history --
             their `last_vote` and identity simply don't update this round.

          2. Ideology drift: every voter's ideology moves a little toward
             the mean ideology of their social network neighbours (if any),
             plus independent random noise (opinion_drift) representing
             influences the model doesn't otherwise capture.
        """
        p = self.params

        participated = self.vote_choice != 0
        if participated.any():
            self.party_identity[participated] = clamp_value(
                (1 - p.identity_reinforcement) * self.party_identity[participated]
                + p.identity_reinforcement * self.vote_choice[participated],
                -1,
                1,
            )
            self.last_vote[participated] = self.vote_choice[participated]

        # Opinion updating is SYNCHRONOUS: every voter's next_ideology is
        # computed from everyone's *current* (pre-update) ideology first,
        # and only afterward does self.ideology get replaced all at once.
        # This matters because it's an order-independence guarantee: if
        # voters updated one at a time instead, an early-updated voter's new
        # ideology would leak into a later voter's neighbour-mean in the
        # same election, which would make the outcome depend on an
        # arbitrary voter processing order. Computing peer_mean and
        # next_ideology entirely from the frozen "before" state, then
        # swapping it in at the very end, rules that out.
        peer_mean = self.ideology  # voters with no network just "peer" with themselves
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

    # -------------------------------------------------------------------
    # Phase 4 & 5: bookkeeping -- running stats, then the history log entry.
    # -------------------------------------------------------------------

    def update_summary_statistics(self) -> None:
        """Recompute the run's running totals after this election: average
        margin so far, how many times control of the "winning" party has
        flipped, and the current party gap / mean electorate ideology."""
        self.cumulative_margin += self.election_margin
        self.mean_margin = self.cumulative_margin / (self.ticks + 1)

        # A "control change" is when the winner differs from the *previous*
        # election's winner. last_winner_id starts at 0 (meaning "no
        # previous election yet"), so the very first election never counts
        # as a change no matter who wins it.
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
        """Append one ElectionRecord describing this election to
        self.history. Uses the electorate's state *after*
        update_voter_states has already moved everyone for next time --
        i.e. this row shows "who voted how" for this election, cross-
        referenced against "where the electorate ended up right after,"
        not where it started."""
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
        """Mean ideology of whichever voters chose `choice` (-1 or 1) this
        election; NaN (not a number) if nobody chose it -- the mean of an
        empty group is genuinely undefined, so this deliberately returns
        NaN rather than a misleading 0."""
        voters = self.vote_choice == choice
        return float(self.ideology[voters].mean()) if voters.any() else float("nan")

    # =========================================================================
    # NETWORK CONSTRUCTION AND OTHER MANUAL CONTROLS
    # (Not part of the automatic per-election cycle -- called explicitly.)
    # =========================================================================

    def build_network(self) -> None:
        """(Re)build the social network from the current ideology
        distribution. Delegates to network.build_network, which does the
        actual random-pair-proposal work; this method just handles the
        "network is off, or degree is zero" cases by leaving the network
        empty instead."""
        p = self.params
        if not p.social_network or p.network_degree <= 0:
            self.network = Network(p.population)
            return
        self.network = build_network(
            self.rng, self.ideology, p.network_degree, p.homophily
        )

    def reset_party_positions(self) -> None:
        """Snap both parties back to their symmetric starting positions
        (based on initial_party_gap) without touching anything else about
        the run -- e.g. for exploring "what if the parties restarted from
        scratch mid-run, with the electorate as it currently stands?"."""
        p = self.params
        self.blue_position = float(clamp_value(-p.initial_party_gap / 2, -1, 1))
        self.red_position = float(clamp_value(p.initial_party_gap / 2, -1, 1))
        self.enforce_party_order()
        self.party_gap = self.red_position - self.blue_position

    # =========================================================================
    # REPORTERS -- read-only views of the model's current state, for
    # experiment tooling (the "jig") to record as metrics.
    # =========================================================================

    #: Every metric name the jig is allowed to ask this model for. Keeping
    #: an explicit allowlist (rather than letting the jig read arbitrary
    #: attributes) means a typo'd metric name in an experiment spec fails
    #: fast with a clear error instead of silently returning nothing, and it
    #: documents in one place everything a run can be measured by.
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
        """Standard deviation of the whole electorate's ideology right now
        -- how spread out vs. collapsed-to-a-point the population is.

        Added deliberately alongside the original metrics: both electorate
        shapes this model supports are symmetric around 0, so the
        electorate's *mean* ideology stays near zero almost no matter what
        is happening internally -- it can look identical whether social
        influence has pulled everyone together or left them exactly as
        spread out as they started. Standard deviation can tell the two
        apart; mean alone cannot.
        """
        return float(self.ideology.std()) if len(self.ideology) else 0.0

    @property
    def mean_degree(self) -> float:
        return self.network.mean_degree

    @property
    def link_count(self) -> int:
        return len(self.network)

    def metrics(self, names: tuple[str, ...] | list[str] | None = None) -> dict[str, Any]:
        """Read a set of metrics off the model's current state as a plain
        dict, e.g. for logging one row of an experiment sweep. Defaults to
        every metric in METRICS if `names` isn't given; raises immediately
        (rather than silently skipping) if any requested name isn't in
        METRICS."""
        names = tuple(names) if names is not None else self.METRICS
        unknown = [n for n in names if n not in self.METRICS]
        if unknown:
            raise ValueError(
                f"unknown metric(s): {', '.join(unknown)}. "
                f"Available: {', '.join(self.METRICS)}"
            )
        return {name: getattr(self, name) for name in names}
