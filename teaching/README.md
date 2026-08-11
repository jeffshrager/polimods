# A guide to the model

This is a reading guide to the core simulation, written for someone who wants
to understand *how the model works* before touching any code. The code
itself lives in this directory as a heavily commented copy of `polimods/` —
same logic, extra explanation. Nothing here changes behavior; it's meant to
be read, not run. If you want to run the model or modify it, use `polimods/`
(see the [top-level README](../README.md)); this copy is not kept in sync
with it automatically.

## The one-sentence version

Two political parties compete in a long series of elections; after each one
the losing party can shift its platform, and voters can shift their views —
does that back-and-forth settle into a fair fight, a permanent landslide, or
something else, and which of the model's mechanisms decide which?

## The mental model

Forget code for a second and picture the world the model builds:

- There is a population of **voters**, each a point on a line from -1
  ("fully Blue") to +1 ("fully Red"). That point is the voter's **ideology**.
- Each voter also carries a **partisan identity** — a second, separate point
  on the same -1..+1 line, representing "which team I root for," which
  usually but not always agrees with their ideology.
- There are exactly **two parties**, Blue and Red, each also a point on that
  same line — their **platform**. Blue is always kept to the left of Red.
- **Time moves in elections**, not days or years. One election is one
  "tick." The model runs for as many ticks as you ask it to (the included
  experiments typically run 100).

Every single election repeats the same five-step cycle:

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │  1. VOTE       Each voter decides: turn out or not, and if so,       │
 │                Blue or Red?  (two competing theories of how — below) │
 │                                                                       │
 │  2. ADAPT      The LOSING party shifts its platform toward voters    │
 │                it might win next time. The winner drifts a little    │
 │                toward its own base too.                              │
 │                                                                       │
 │  3. UPDATE     Voters who cast a ballot get pulled slightly toward   │
 │                the party they chose (identity reinforcement).        │
 │                Every voter's ideology drifts toward their social     │
 │                network neighbors' average (if a network exists),     │
 │                plus a little random noise.                           │
 │                                                                       │
 │  4. MEASURE    Vote shares, margin, turnout, party gap, ideology     │
 │                spread — all recomputed.                              │
 │                                                                       │
 │  5. LOG        One row appended to the election history.             │
 └──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    back to step 1, next election
```

That loop — and *only* that loop — is the entire model. Everything else
(the two vote-choice theories, the social network, all eighteen parameters)
is detail about how one of those five steps computes its answer.

## Reading order and file guide

| Order | File | What it's for |
|---|---|---|
| 1 | [`params.py`](params.py) | Every dial the model has, grouped by what it controls, with the legal range for each (inherited from the original NetLogo sliders). Read this to learn the vocabulary; nothing in it simulates anything. |
| 2 | [`network.py`](network.py) | How voters get wired into a social network, and the array tricks used to compute "the average opinion among my neighbors" for everyone at once instead of one voter at a time. |
| 3 | [`rules.py`](rules.py) | Vote-choice theory #1: eight independent IF-THEN rules that each cast a *reason*, not a weight. |
| 4 | [`model.py`](model.py) | The simulation loop itself — the five-step cycle above, spelled out as code. Vote-choice theory #2 (a single continuous equation) lives here too, for comparison against `rules.py`. |
| 5 | [`history.py`](history.py) | The per-election logbook and its export format. Pure bookkeeping — read it last. |

Open a file and its `polimods/` counterpart side by side if you want to
double check that a comment matches the real logic; they should always
agree, since this is a straight copy.

## Two theories of how a voter decides

The model can't decide between two different psychological stories about
voting, so it implements *both* and lets you switch between them
(`production_system` in `params.py`). They are not two implementations of
the same idea — they make different claims about how people think.

### Theory A — a continuous weighted equation (`production_system = False`)

Every voter computes one number, `choice_score`, by adding up three
continuous terms:

```
choice_score = |ideology − blue_position| − |ideology − red_position|
             + identity_strength × party_identity
             + noise
```

The first term is "how much closer is Red than Blue" (positive favors Red,
negative favors Blue). The second term adds a pull toward whichever party
the voter identifies with, scaled by `identity_strength`. The third is
random noise (`election_noise`) standing in for everything the model
doesn't otherwise model.

**Worked example.** A voter sits at ideology `0.2`. Blue is at `-0.5`, Red
is at `0.5`. Policy distance: `|0.2 − (−0.5)| − |0.2 − 0.5| = 0.7 − 0.3 =
0.4` (favors Red). Say this voter's partisan identity is a mild `-0.3`
(leans Blue) and `identity_strength = 0.6`: that term contributes
`0.6 × (−0.3) = −0.18`. Total, before noise: `0.4 − 0.18 = 0.22` — positive,
so the voter leans Red, though their Blue-leaning identity has pulled that
preference most of the way back toward the middle.

The *sign* of `choice_score` picks the party (negative → Blue, positive →
Red, and — a small, deliberate asymmetry inherited from the original NetLogo
`ifelse` — an exact zero also goes to Red). The *magnitude* separately
drives turnout: `turnout_probability = base_turnout + turnout_sensitivity ×
|choice_score|`, clipped to `[0, 1]`. So a voter's certainty (how far their
score is from zero) makes them more likely to show up, regardless of which
way they lean — strongly Blue and strongly Red voters both turn out more
than near-indifferent ones.

### Theory B — eight IF-THEN rules, reasons not weights (`production_system = True`)

Instead of one smooth equation, each voter runs eight independent rules.
Each rule looks at the voter's own situation and, if its condition is met,
adds exactly one *reason* to a tally — for Blue, for Red, for turning out,
or for abstaining. Nothing is weighted; a voter barely past a rule's
threshold gets the same one-reason credit as a voter far past it.

| # | Rule | Fires when... | Adds a reason for... |
|---|---|---|---|
| 1 | Policy proximity | one party is substantially closer | that party |
| 2 | Partisan identity | scaled identity is strong enough | the corresponding party |
| 3 | Voting habit | the voter chose a party last time | repeating that choice |
| 4 | Social majority | ≥60% of *active* neighbors backed one party last time | that party (needs a network) |
| 5 | Engagement | policy *or* identity signal is unusually strong | turning out |
| 6 | Indifference | the two parties are nearly equally attractive | abstaining |
| 7 | Alienation | even the closer party is still far away | abstaining |
| 8 | Cross-pressure | policy and identity point to *opposite* parties | abstaining |

After all eight rules fire, `choice_score = (reasons for Red) − (reasons
for Blue)`. Whoever has more reasons wins; an exact tie is broken with a
small random nudge (see `rules.TIE_BREAK_SCORE`) rather than defaulting to
either side. Turnout probability shifts by whole steps of
`turnout_sensitivity` per net (turnout − abstention) reason, rather than
scaling continuously.

**Why this matters beyond mechanism-trivia**: because scores here are
integer reason-counts (1, 2, 3...) rather than a continuum, almost no voter
ever lands near zero — except the handful who got tie-broken, whose score
is exactly `±0.001`. Party adaptation (next section) targets voters within
`persuadable_band` (default `0.25`) of zero, so under this theory the
losing party's "persuadable voters" pool is usually *only* the tie-broken
ones — a very different, much smaller group than the weighted-choice model
produces from the same `persuadable_band` setting.

## Party adaptation: how Blue and Red respond

After every election, the **losing** party can move (if `adaptive_parties`
is on). It blends two possible targets:

- **Electoral target** — the mean ideology of "persuadable" voters: people
  who voted for the *other* party but whose `choice_score` was within
  `persuadable_band` of zero, i.e. voters it narrowly failed to win. If
  there are none, it falls back to the whole electorate's mean.
- **Base target** — the mean ideology of the losing party's *own* current
  supporters.

```
target = (1 − base_pressure) × electoral_target + base_pressure × base_target
```

`base_pressure = 0` means "chase the voters I nearly won"; `base_pressure =
1` means "retreat to my base instead." The party then closes a
`party_adaptation` fraction of the remaining distance to that target —
`0` means don't move, `1` means jump straight there.

The **winning** party moves too, independently, toward its own supporters'
mean, at a separate (usually much smaller) rate, `winner_base_adaptation`.
**This is the model's single most surprising behavior**: because the winner
moves via this separate term, setting `party_adaptation = 0` does *not*
freeze the parties — the winner keeps creeping toward its base every
election regardless, unless `winner_base_adaptation` is *also* zero. A
"parties never move" control condition needs both set to zero, not just one.

Finally, `enforce_party_order` clamps both parties to `[-1, 1]` and — if
adaptation would ever push Blue to the right of Red, or collapse them
together — snaps them back apart to sit `0.02` apart around their midpoint.
Blue is always the left party; that invariant is never allowed to break.

## Voters updating: identity and ideology drift

Two independent things happen to every voter after the election, regardless
of which vote-choice theory was used:

**Identity reinforcement.** A voter who actually cast a ballot (not an
abstainer) has their `party_identity` pulled a little toward the party they
just voted for:

```
new_identity = (1 − identity_reinforcement) × old_identity
             + identity_reinforcement × vote_choice
```

This is a positive feedback loop — vote Red enough times and your identity
drifts toward Red, making you more likely to vote Red again next time.
Abstainers are left untouched: **abstaining does not erase a voter's
partisan history.** Their identity and `last_vote` simply don't update that
round, so an abstaining voter's most recent *actual* vote still counts as
their "habit" (rule 3) and "last vote" for switch-rate purposes indefinitely,
until they vote again.

**Ideology drift.** Separately, every voter's ideology moves a little
toward the mean ideology of their social network neighbors (if the network
is on and they have any), plus independent random noise (`opinion_drift`):

```
next_ideology = ideology + social_influence × (neighbor_mean − ideology) + noise
```

This update is **synchronous**: every voter's next ideology is computed from
everyone's *current* (pre-update) values first, and only afterward does the
whole population switch to the new values at once. That rules out a subtle
bug class where an early-updated voter's new opinion would leak into a
later voter's neighbor-average within the *same* election, making the
result depend on an arbitrary processing order.

## The social network

When `social_network` is on, voters are wired into an undirected graph with
roughly `network_degree` connections each, built once (or on demand via
`Model.build_network`). Two candidate voters are proposed at random and
linked with probability:

```
acceptance = (1 − homophily) + homophily × (1 − |ideology_a − ideology_b| / 2)
```

At `homophily = 0`, every proposed pair links regardless of ideology — pure
random wiring. At `homophily = 1`, acceptance falls off linearly with
ideological distance — "birds of a feather," strongly preferring to link
similar voters. Intermediate values blend the two.

Network effects only ever *pull voters together* (the drift equation above
always moves a voter toward its neighbors' mean, never away). Whatever
`homophily` is, if `social_influence` is also nonzero, ideology drift is
occurring. What `homophily` changes is *whose* mean you're drifting toward,
not *whether* you drift at all.

## Everything the model measures

`Model.metrics()` (backed by `Model.METRICS` in `model.py`) exposes:

`ticks`, `winner_id`, `blue_share`, `red_share`, `turnout_rate`,
`election_margin`, `mean_margin`, `party_control_changes`,
`control_change_rate`, `blue_position`, `red_position`, `party_gap`,
`mean_voter_ideology`, `ideology_sd`, `switch_rate`, `mean_degree`,
`link_count`.

Two are worth flagging specifically: `mean_voter_ideology` looks flat near
zero in both electorate shapes the model supports *by construction* (they're
both symmetric around 0), so it can't tell you whether voters are spread out
or collapsed together — only `ideology_sd` (added beyond the original
NetLogo monitors) can. If a sweep result looks suspiciously flat, check
whether it's being measured with the mean when it should be measured with
the spread.

`History` (in `history.py`) additionally logs, per election, the ideology
distribution's 10th/50th/90th percentiles and the mean ideology of each
party's *actual voters that election* (`blue_voter_ideology` /
`red_voter_ideology`) — the exact quantity party adaptation is chasing, so
you can watch a party visibly close in on its own coalition's center over
time.

## Non-obvious behaviors worth knowing before trusting a result

These aren't bugs; they're real, sometimes surprising, consequences of how
the mechanisms above compose. Each one has bitten someone reading a result
without knowing it was there:

- **`party_adaptation = 0` is not a "parties never move" control.** See
  "Party adaptation" above — the winner still drifts via
  `winner_base_adaptation`, whose default is `0.03`, not `0`.
- **Under the production system, only tie-broken voters are usually
  "persuadable."** Integer reason-counts rarely land inside a
  `persuadable_band` of `0.25`; the `±0.001` tie-break scores almost always
  do. See "Theory B" above.
- **A perfectly tied `choice_score` votes Red** in the weighted-choice
  model (an inherited NetLogo `ifelse` asymmetry) — but is resolved by a
  genuine random draw in the production system instead.
- **Abstention does not erase partisan history.** An abstainer's
  `last_vote` and `party_identity` simply stop updating that round; they
  don't reset.
- **Homophily only decides *who* you drift toward, not *whether* you
  drift.** Any positive `social_influence` pulls voters together regardless
  of `homophily`; homophily changes the speed/shape of that convergence, not
  whether it happens. See "The social network" above.
- **`electorate_polarization` does nothing under `electorate_shape =
  "single-peaked"`** — it only positions the two camp centers in the
  `"two-camp"` shape (see `Model.setup_voters` / `params.py`).

## Parameter reference

Full descriptions live as comments on each field in `params.py`; this is
just the map of what's grouped where.

| Group | Parameters |
|---|---|
| Electorate construction | `electorate_shape`, `population`, `ideology_spread`, `electorate_polarization`, `identity_noise` |
| Party construction & adaptation | `initial_party_gap`, `adaptive_parties`, `party_adaptation`, `persuadable_band`, `base_pressure`, `winner_base_adaptation` |
| Vote choice, identity, turnout (Theory A) | `identity_strength`, `identity_reinforcement`, `base_turnout`, `turnout_sensitivity`, `election_noise` |
| Network & opinion change | `social_network`, `network_degree`, `homophily`, `social_influence`, `opinion_drift` |
| Production system (Theory B) | `production_system`, `rule_policy`, `rule_identity`, `rule_habit`, `rule_neighbors`, `rule_engagement`, `rule_indifference`, `rule_alienation`, `rule_cross_pressure` |

`Params()` reproduces the plain NetLogo model's defaults (Theory A);
`Params.production_rules_defaults()` reproduces the production-rules
interface's defaults (Theory B). `BOUNDS` in `params.py` records the legal
range for every numeric field, inherited from the original NetLogo sliders.

## Where to go from here

- To actually **run** the model, sweep parameters, or reproduce a
  result: use `polimods/` and its experiment jig — see the
  [top-level README](../README.md).
- To see the model's central claims tested against real runs, read one of
  the experiment write-ups under `experiments/*/paper/paper.md`, e.g.
  `experiments/*_homophily_polarization/paper/paper.md`.
- To see exactly which NetLogo procedure each piece of this code descends
  from, see `docs/PORTING.md` and the frozen originals in `netlogo/`.
