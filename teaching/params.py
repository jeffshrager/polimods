"""
================================================================================
 PARAMS -- the model's dashboard of dials
================================================================================
This file defines every *input* the model accepts.  Nothing in here simulates
anything; it just names the knobs and says what values are legal for each one.

Historical note: this model began life as a NetLogo program, where every one
of these numbers was a slider, switch, or dropdown ("chooser") on screen that
you dragged with a mouse.  Each field below corresponds to exactly one of
those widgets, and BOUNDS (further down) records the min/max/step the widget
allowed -- so "validate a Params" literally means "could this value have come
from dragging that slider?"

If you are new to the model, the fields are grouped by what they control:

  1. electorate construction   -- how the voters are generated at the start
  2. party construction        -- where the two parties start, how they adapt
  3. vote choice / turnout     -- how a voter decides whether & who to vote for
  4. network and opinion change-- whether voters talk to each other and drift
  5. production system         -- an alternate, rule-based way to decide votes
                                   (see rules.py for what these switches do)

Read Params first, then model.py (the simulation loop), then rules.py and
network.py (the two pieces model.py delegates to).
================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any

# The only two ways the initial electorate can be shaped.  "single-peaked"
# means most voters start near the political centre (a bell curve around 0).
# "two-camp" means voters start clustered into two separate piles, left and
# right, which is a crude stand-in for a pre-polarized electorate.
ELECTORATE_SHAPES = ("single-peaked", "two-camp")

# --------------------------------------------------------------------------
# BOUNDS: name -> (minimum, maximum, step)
#
# This is a direct transcription of the NetLogo slider ranges.  Two things
# use it:
#   1. Params.validate() below, which rejects any value outside its range.
#   2. The experiment "jig" (see polimods/jig/), which sweeps values and
#      checks *before* running anything that every value in the sweep is
#      something the original interface could actually produce. That way a
#      typo in an experiment spec fails immediately, not 200 runs in.
#
# The "step" (third number) isn't enforced by validate() -- only the range
# is -- but it's kept here because it documents the sliders' real
# granularity even though Python doesn't need it to run the model.
# --------------------------------------------------------------------------
BOUNDS: dict[str, tuple[float, float, float]] = {
    "population": (50, 2000, 50),
    "initial_party_gap": (0.1, 1.8, 0.05),
    "ideology_spread": (0.02, 0.8, 0.01),
    "party_adaptation": (0.0, 1.0, 0.01),
    "electorate_polarization": (0.0, 0.9, 0.01),
    "base_pressure": (0.0, 1.0, 0.01),
    "identity_noise": (0.0, 1.0, 0.01),
    "persuadable_band": (0.01, 1.0, 0.01),
    "identity_strength": (0.0, 2.0, 0.02),
    "winner_base_adaptation": (0.0, 0.5, 0.01),
    "identity_reinforcement": (0.0, 0.25, 0.005),
    "base_turnout": (0.0, 1.0, 0.01),
    "turnout_sensitivity": (0.0, 0.5, 0.01),
    "election_noise": (0.0, 0.5, 0.01),
    "network_degree": (0, 20, 1),
    "homophily": (0.0, 1.0, 0.01),
    "social_influence": (0.0, 0.5, 0.01),
    "opinion_drift": (0.0, 0.1, 0.002),
}


@dataclass(frozen=True)
class Params:
    """One complete parameterization of the model -- i.e. one setting of every
    dial, bundled into a single immutable object.

    ``frozen=True`` means a Params instance can never be mutated after it is
    built.  That matters for an experiment sweep: dozens of Model runs can
    all point at the *same* Params object (or variations produced by
    ``.replace()``) without any risk that one run's changes leak into
    another's.

    The defaults below reproduce the plain ``adaptive_two_party_model.nlogo``
    (production_system=False, the continuous weighted-choice equation).  The
    companion "production rules" NetLogo file ships with that switch turned
    ON instead; use ``Params.production_rules_defaults()`` to get that
    starting point.
    """

    # =========================================================================
    # 1. ELECTORATE CONSTRUCTION
    #    These fields control how the population of voters is generated once,
    #    at the start of a run (see Model.setup_voters in model.py).
    # =========================================================================

    #: "single-peaked" (one bell curve centred on 0) or "two-camp" (two piles,
    #: one left of centre, one right).  See ELECTORATE_SHAPES above.
    electorate_shape: str = "single-peaked"

    #: Number of simulated voters. Every per-voter quantity in the model is a
    #: numpy array of this length.
    population: int = 500

    #: Standard deviation of each voter's ideology draw around its "camp
    #: centre" (0 for single-peaked; +/-electorate_polarization for two-camp).
    #: Bigger = more spread-out / heterogeneous electorate.
    ideology_spread: float = 0.25

    #: Only used when electorate_shape == "two-camp": how far apart the two
    #: camp centres sit from 0, i.e. half the initial gap between the camps.
    electorate_polarization: float = 0.35

    #: How loosely a voter's declared party_identity tracks their true
    #: ideology at birth. 0 = identity is a perfect copy of ideology; larger
    #: values add independent noise, so identity and ideology can disagree.
    identity_noise: float = 0.35

    # =========================================================================
    # 2. PARTY CONSTRUCTION AND ADAPTATION
    #    These fields control where Blue and Red start out on the ideology
    #    line, and how aggressively they chase votes after losing or winning.
    #    See Model.adapt_parties / move_losing_party / move_winning_party.
    # =========================================================================

    #: Distance between the two parties' starting positions (Blue starts at
    #: -gap/2, Red at +gap/2).  A big gap means clearly differentiated
    #: parties at the outset; a small gap means near-identical platforms.
    initial_party_gap: float = 1.0

    #: Master switch. If False, party positions never move -- a fixed,
    #: unresponsive two-party system, useful as a baseline/control.
    adaptive_parties: bool = True

    #: How far the *losing* party moves toward its target each election
    #: (0 = no movement even though adaptive_parties is on; 1 = jumps
    #: straight to the target in one election).
    party_adaptation: float = 0.25

    #: How close a losing voter's choice_score must be to zero to count as
    #: "persuadable" -- i.e. someone the losing party plausibly could have
    #: won and will now chase.
    persuadable_band: float = 0.25

    #: Blends the losing party's target between "the persuadable voters it
    #: nearly won" (base_pressure=0) and "its own current supporters"
    #: (base_pressure=1). See move_losing_party for the exact mix.
    base_pressure: float = 0.15

    #: Unlike the loser, the *winning* party also drifts slightly toward its
    #: own supporters' mean ideology, at this (usually much smaller) rate.
    #: Important: this means party_adaptation=0 is NOT a true "parties never
    #: move" control -- the winner still creeps via this term. See
    #: move_winning_party.
    winner_base_adaptation: float = 0.03

    # =========================================================================
    # 3. VOTE CHOICE, IDENTITY, TURNOUT
    #    Used by the *default* (non-production-system) decision rule: a
    #    single continuous equation for "which party do I prefer, and by how
    #    much." See Model.run_weighted_choice_model.
    # =========================================================================

    #: How much a voter's partisan identity (a number from -1=Blue to +1=Red)
    #: pulls their vote choice, independent of policy distance.
    identity_strength: float = 0.6

    #: After voting, how much a voter's identity shifts toward the party they
    #: just voted for. This is the mechanism that can entrench identity over
    #: time -- vote Red enough times and your "identity" number drifts red.
    identity_reinforcement: float = 0.03

    #: Baseline probability of turning out to vote, before any adjustment.
    base_turnout: float = 0.55

    #: How much a stronger (more lopsided) choice_score raises turnout
    #: probability above the baseline -- people with a clear preference are
    #: more likely to show up.
    turnout_sensitivity: float = 0.12

    #: Standard deviation of random noise added to each voter's choice_score
    #: in the weighted-choice model, representing idiosyncratic factors the
    #: model doesn't otherwise capture.
    election_noise: float = 0.08

    # =========================================================================
    # 4. NETWORK AND OPINION CHANGE
    #    Voters can be linked in a social network and drift their ideology
    #    toward their neighbours' average each election. See network.py and
    #    Model.update_voter_states.
    # =========================================================================

    #: Master switch for the social network. If False, voters have no
    #: neighbours and only drift via independent random noise.
    social_network: bool = False

    #: Target average number of connections (edges) per voter.
    network_degree: int = 6

    #: How strongly the network favours linking similar voters over
    #: dissimilar ones when it's built. 0 = random linking regardless of
    #: ideology; 1 = strongly prefers linking voters who already agree.
    #: See build_network in network.py for the exact acceptance formula.
    homophily: float = 0.7

    #: How much each voter's ideology moves, per election, toward the mean
    #: ideology of their network neighbours (or their own value, if isolated).
    social_influence: float = 0.08

    #: Standard deviation of independent random ideology drift applied to
    #: every voter every election, on top of any social pull.
    opinion_drift: float = 0.01

    # =========================================================================
    # 5. VOTER PRODUCTION SYSTEM
    #    An alternate, entirely separate way of deciding each voter's vote:
    #    instead of one continuous equation, eight independent IF-THEN rules
    #    each cast a vote for a reason, and the reasons are simply counted.
    #    See rules.py for what each rule_* switch actually does.
    # =========================================================================

    #: Master switch. False -> Model.run_election uses the continuous
    #: weighted-choice equation above. True -> it uses the eight rules in
    #: rules.py instead. These are two different *models* of voter cognition,
    #: not two implementations of the same one.
    production_system: bool = False

    #: RULE 1: "the party that's substantially closer on policy gets a
    #: reason." See rules.POLICY_THRESHOLD.
    rule_policy: bool = True

    #: RULE 2: "sufficiently strong partisan identity is itself a reason."
    #: See rules.IDENTITY_THRESHOLD.
    rule_identity: bool = True

    #: RULE 3: "whichever party you voted for last time gets a reason to
    #: repeat" -- pure inertia/habit.
    rule_habit: bool = True

    #: RULE 4: "if a clear majority of your politically-active network
    #: neighbours voted one way last time, that's a reason." Requires
    #: social_network to actually be on -- see run_production_system.
    rule_neighbors: bool = True

    #: RULE 5: "strong policy or identity signal is itself a reason to turn
    #: out," independent of which party it favours.
    rule_engagement: bool = True

    #: RULE 6: "if the parties are nearly equally attractive, that's a
    #: reason to abstain" -- indifference.
    rule_indifference: bool = True

    #: RULE 7: "if even the nearer party is still far away, that's a reason
    #: to abstain" -- alienation from both parties.
    rule_alienation: bool = True

    #: RULE 8: "if policy and identity point to *opposite* parties, that's a
    #: reason to abstain" -- cross-pressure / conflicted voters sit out.
    rule_cross_pressure: bool = True

    # -------------------------------------------------------------------
    # Convenience constructors and helpers -- none of these change what a
    # Params *is*; they just make common ways of building or inspecting one
    # less verbose.
    # -------------------------------------------------------------------

    @classmethod
    def production_rules_defaults(cls, **overrides: Any) -> "Params":
        """Same defaults as above, but with the production system switched
        on -- i.e. what the production-rules NetLogo interface starts at."""
        return cls(production_system=True, **overrides)

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        """Every dataclass field name, e.g. for building a CLI or a table
        header without hand-typing the field list twice."""
        return tuple(f.name for f in fields(cls))

    def replace(self, **changes: Any) -> "Params":
        """Return a *new* Params with some fields changed, leaving this one
        untouched (it's frozen, so this is the only way to "change" it)."""
        return replace(self, **changes)

    def as_dict(self) -> dict[str, Any]:
        """Every field as a plain dict, e.g. for writing to JSON/CSV."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def validate(self) -> "Params":
        """Reject any value a real NetLogo slider or chooser could not have
        produced.

        Why this exists: an experiment sweep can generate hundreds of Params
        combinations from a spec file. Without this check, a typo (say,
        homophily=7 instead of 0.7) would only surface as a weird result
        buried in run #150 of 300 -- or not surface at all. Calling
        validate() up front turns that into an immediate, clearly-labelled
        error before any simulation runs.

        Returns ``self`` so it can be chained, e.g. ``Params(...).validate()``.
        """
        # electorate_shape is a chooser, not a slider -- check it's one of
        # the two allowed strings rather than in a numeric range.
        if self.electorate_shape not in ELECTORATE_SHAPES:
            raise ValueError(
                f"electorate_shape must be one of {ELECTORATE_SHAPES}, "
                f"got {self.electorate_shape!r}"
            )

        # Every numeric slider: must be a real number (not a bool -- True/
        # False pass Python's `isinstance(x, int)` check, which would let a
        # stray boolean sneak through a numeric field) and within its range.
        for name, (low, high, _step) in BOUNDS.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be numeric, got {value!r}")
            if not low <= value <= high:
                raise ValueError(
                    f"{name} must be in [{low}, {high}] (NetLogo slider range), "
                    f"got {value}"
                )

        # Two sliders (population, network_degree) are integer-only in
        # NetLogo even though Python would happily store 500.5 in them.
        for name in ("population", "network_degree"):
            value = getattr(self, name)
            if int(value) != value:
                raise ValueError(f"{name} must be a whole number, got {value}")

        # Every switch (bool-typed field) must actually be a bool, not e.g.
        # the integer 1 -- keeps switches and numeric sliders from being
        # silently interchangeable.
        for f in fields(self):
            if f.type == "bool" and not isinstance(getattr(self, f.name), bool):
                raise ValueError(
                    f"{f.name} must be a boolean, got {getattr(self, f.name)!r}"
                )

        return self


# The NetLogo defaults, exposed as a plain dict. Useful for manifests/docs
# that want to report what a given experiment changed relative to a fresh
# copy of the model (i.e. diff an experiment's Params against this).
NETLOGO_DEFAULTS = Params().as_dict()
