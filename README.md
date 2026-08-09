# Adaptive Two-Party Competition

A heavily commented NetLogo teaching model of repeated electoral competition between two adaptive political parties, with a Python port and a scriptable experiment runner.

The model asks a deliberately narrow question:

> Can two parties that adjust their positions after elections generate persistent electoral parity, and under what conditions does that parity disappear?

Each tick represents one election. Individual voters decide whether to vote and which party to support; parties then adapt to the result; partisan identity and voter ideology may evolve before the next election.

## Two implementations

| | NetLogo | Python |
|---|---|---|
| Files | `adaptive_two_party_model*.nlogo` | `polimods/` |
| Best for | reading, teaching, watching one run unfold | running thousands of runs and analyzing them |
| Experiments | BehaviorSpace, through the GUI | `polimods.jig`, from a TOML spec |

The two are the same model. The Python port reproduces every mechanism and both
BehaviorSpace experiments; it does not reproduce the display layer, which the
model never reads. Runs are not bit-identical across the two, because NetLogo and
numpy use different random number generators — see
[`docs/PORTING.md`](docs/PORTING.md) for the full mapping and the handful of
behaviours worth knowing about before interpreting results.

# Python

## Install

```bash
pip install -e .            # requires Python 3.11+ and numpy
pip install -e '.[dev]'     # adds pytest and matplotlib
```

## Run one model

```bash
python -m polimods --steps 100 --seed 1 --export history.tsv
```

Every interface parameter is a flag, and every switch has a `--no-` form:

```bash
python -m polimods --steps 100 --population 2000 --party-adaptation 0.4 \
                   --electorate-shape two-camp --social-network
python -m polimods --steps 100 --production-system --no-rule-habit
```

The TSV it writes has the same columns, rounding, and number formatting as
NetLogo's **EXPORT HISTORY (TSV)** button.

From Python:

```python
from polimods import Model, Params

model = Model(Params(party_adaptation=0.4, social_network=True), seed=1).run(100)
print(model.mean_margin, model.party_gap, model.control_change_rate)

for record in model.history:
    ...
```

`Params()` reproduces `adaptive_two_party_model.nlogo`;
`Params.production_rules_defaults()` reproduces the production-rules interface.
`Params.validate()` rejects any value the NetLogo sliders could not have
produced, and every model validates its parameters on construction.

## The experimental jig

The jig is a scriptable replacement for BehaviorSpace. An experiment is a TOML
file; running it fans out across processes, seeds every run deterministically,
and writes a self-describing timestamped folder next to the spec.

```bash
python -m polimods.jig list                                    # every experiment
python -m polimods.jig run experiments/202608071014_parity_sweep/parity_sweep.toml --dry-run
python -m polimods.jig run experiments/202608071014_parity_sweep/parity_sweep.toml --jobs 12
python -m polimods.jig summarize experiments/202608071014_parity_sweep
python -m polimods.jig summarize experiments/202608071014_parity_sweep --plot mean_margin
```

An experiment spec mirrors BehaviorSpace's vocabulary:

```toml
name = "parity_sweep"
repetitions = 10                 # runs per condition
steps = 100                      # elections per run (timeLimit)
base_seed = 20260807
metrics = ["mean_margin", "control_change_rate", "party_gap"]

[constants]                      # held fixed
social_network = false
population = 500

[sweep]                          # crossed with each other
party_adaptation = { first = 0.0, step = 0.1, last = 0.5 }   # steppedValueSet
base_pressure = [0.0, 0.25, 0.5, 0.75, 1.0]                  # enumeratedValueSet
```

Sweep values are validated against the NetLogo slider ranges before the first run
starts, so a typo fails the experiment immediately rather than 200 runs in.

Useful flags: `--jobs` (default: cores − 2), `--resume` (skip runs already in
`runs.csv`), `--dry-run`, `--root`, `--out`, `--quiet`.

## Experiment layout

One experiment is one timestamped folder under `experiments/`, named
`YYYYMMDDHHMM_<name>` and holding the spec that produced it plus everything the
run wrote:

```
experiments/
  202608071014_parity_sweep/
    parity_sweep.toml # the spec this folder was produced by
    manifest.json     # what was run: every variable, its setting, its sweep range
    runs.csv          # one row per run: condition + final metrics
    steps.csv         # one row per election (only if run_metrics_every_step)
    mean_margin.png   # whatever `summarize --plot` wrote
```

The spec lives inside the folder so the folder answers its own questions later: a
`runs.csv` you cannot tie to a spec is a table of numbers with no design behind
it. There are two ways to start an experiment, and both end up here:

```bash
mkdir experiments/202608091821_network_scan      # write the spec where it belongs
$EDITOR experiments/202608091821_network_scan/network_scan.toml
python -m polimods.jig run experiments/202608091821_network_scan/network_scan.toml

python -m polimods.jig run experiments/network_scan.toml   # or drop a loose spec:
                                             # a stamped folder is created for it
```

A spec already inside a stamped folder is run in place. A loose spec gets
`experiments/<stamp>_<name>/` and is copied into it. The stamp carries the minute
because several experiments a day is the normal case here; it is local time,
while the manifest's `created` field is the UTC record.

Re-running an experiment never overwrites finished results — the run goes to a
folder carrying its own stamp (and a `_2` suffix if the same minute is taken
too), and the new manifest records what it collided with. Use `--resume` to
continue into the existing folder instead.

`manifest.json` describes **all** model variables, not only the swept ones, each
tagged with the role it played:

```json
"party_adaptation": {
  "role": "swept",
  "sweep": { "first": 0.0, "step": 0.1, "last": 0.5 },
  "values": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
  "bounds": [0.0, 1.0],
  "netlogo_default": 0.25
},
"population":        { "role": "constant", "value": 500, "netlogo_default": 500 },
"identity_strength": { "role": "default",  "value": 0.6, "netlogo_default": 0.6 }
```

`role` is `swept`, `constant` (pinned by the spec), or `default` (untouched). The
manifest also records the git commit, base seed, run count, wall time, and
library versions — enough to reconstruct the experiment from the folder alone.

## Generic figures

`generic_analyses/` draws the same four figures for any experiment folder: where
the parties are against where the voters are, how the competition went, whether
either converged, and the first of those repeated across the sweep's conditions.

```bash
python -m generic_analyses experiments/202608081234_dynamics_demo
python -m generic_analyses <folder> --condition 5 --theme dark
```

It reads `steps.csv`, so the spec must set `run_metrics_every_step = true`; PNGs
are written into the experiment folder. See
[`generic_analyses/README.md`](generic_analyses/README.md).

## Included experiments

| Experiment | Runs | Question |
|---|---:|---|
| `experiments/202608071014_parity_sweep/` | 300 | Does losing-party adaptation generate parity, and does base pressure prevent it? |
| `experiments/202608071014_network_sweep/` | 250 | How do homophily and social influence interact in a two-camp electorate? |
| `experiments/202608071014_rule_ablation/` | 2560 | What does each of the eight production rules contribute? |
| `experiments/202608081234_dynamics_demo/` | 30 | What do the dynamics look like, election by election? |

The first two are ports of the BehaviorSpace experiments included in the
`.nlogo` files. The third is new: the NetLogo ships the production system but no
experiment that exercises it, because crossing eight switches by hand is not
something anyone does 256 times. The fourth is small and exists for its
per-election output, which is what `generic_analyses/` draws.

## Tests

```bash
pytest -q
```

The suite pins each formula against hand-computed values, tests every production
rule at its threshold, and checks whole-model behaviour in regimes where the
answer is known independently — a symmetric electorate cannot favour a party,
turnout with no sensitivity term cannot leave its baseline, and a model with
every stochastic channel closed cannot move at all.

# NetLogo

## Requirements

- [NetLogo 6.4.0](https://ccl.northwestern.edu/netlogo/)
- Model file: `adaptive_two_party_model_commented.nlogo`

The model may work in later NetLogo 6.x releases, but it was saved with NetLogo 6.4.0.

## Quick start

1. Open `adaptive_two_party_model_commented.nlogo` in NetLogo.
2. Click **SETUP** to create the electorate, parties, and optional social network.
3. Click **ONE ELECTION** to advance one election at a time, or **GO** to run continuously.
4. Watch the vote-share, party-position, margin, turnout, and ideology-distribution plots.
5. Use **EXPORT HISTORY (TSV)** to save election-level results.

For an initial controlled experiment, turn the social network off and set `identity-reinforcement`, `opinion-drift`, and `winner-base-adaptation` to zero. Compare a fixed-party condition (`party-adaptation = 0`) with several positive adaptation values.

## Central modeling distinction

Voters and parties have an **internal political state**. Their positions in the NetLogo world only display that state.

- A voter’s horizontal screen position represents its internal `ideology` value.
- A voter’s vertical position is arbitrary visual jitter.
- Party stars display `blue-position` and `red-position`.
- Social influence follows explicit network links.

Voting and party adaptation never use `xcor`, `ycor`, turtle distance, patch location, or spatial neighborhoods. The screen is therefore a graph of the model, not the model’s causal political space.

## Agents and state

The model contains:

- **Voters**, each with ideology, partisan identity, turnout probability, vote choice, and vote history.
- **Two parties**, Blue and Red, displayed as star-shaped turtles.
- **Undirected social links**, through which voter ideology may be influenced.

Political ideology and party positions lie on a one-dimensional scale from `-1` to `+1`. Blue is constrained to remain to the left of Red, with a minimum gap of `0.02`.

## Election cycle

Every call to `go` performs the following sequence:

1. Bring the social network into consistency with the current interface settings.
2. Compute each voter’s party preference.
3. Compute turnout probabilities and draw participation.
4. Count votes and determine the winner.
5. Adapt the losing party and, optionally, the winner.
6. Reinforce the partisan identity of participating voters.
7. Update ideology through peer influence and random drift.
8. Update summary statistics, plots, display positions, and history.
9. Advance the tick counter.

The order is theoretically meaningful: parties respond to the electorate that just voted, and voters change before the following election.

## Voter choice

In the non-rule-based decision model, each voter calculates a continuous `choice-score`:

```text
choice-score =
    |ideology - blue-position|
  - |ideology - red-position|
  + identity-strength * party-identity
  + election shock
```

Equivalently, for voter \(i\):

\[
C_i = |I_i-B|-|I_i-R|+sP_i+\epsilon_i
\]

where:

- \(I_i\) is the voter’s ideology;
- \(B\) and \(R\) are the Blue and Red party positions;
- \(P_i\) is the voter’s partisan identity, from `-1` to `+1`;
- \(s\) is `identity-strength`; and
- \(\epsilon_i\) is a normally distributed election shock with standard deviation `election-noise`.

The first term compares the voter’s distance from the two parties:

\[
|I_i-B|-|I_i-R|
\]

A voter who is closer to Red has a larger distance from Blue than from Red, so this term is positive. A voter who is closer to Blue has a negative value. Consequently:

- a negative `choice-score` favors Blue;
- a positive `choice-score` favors Red.

For example, suppose a voter has ideology `0.2`, while Blue is at `-0.5` and Red is at `0.5`. The policy-distance contribution is:

\[
|0.2-(-0.5)|-|0.2-0.5|=0.7-0.3=0.4
\]

Policy proximity therefore contributes `+0.4`, favoring Red. If the same voter has a mildly Blue partisan identity of `-0.3` and `identity-strength = 0.6`, identity contributes:

\[
0.6(-0.3)=-0.18
\]

Before election noise, the total score is:

\[
0.4-0.18=0.22
\]

The voter therefore intends to vote Red, although the voter’s Blue identity weakens that preference. The random election shock may occasionally reverse the result.

The intended party is selected from the sign of the score:

```netlogo
ifelse choice-score < 0
  [ set intended-choice -1 ]
  [ set intended-choice 1 ]
```

Blue is coded as `-1` and Red as `+1`. An exact zero is therefore assigned to Red, although exact zeros are rare when `election-noise` is positive.

Turnout is decided separately. The probability of voting is:

```text
base-turnout + turnout-sensitivity * abs(choice-score)
```

or:

\[
T_i = \operatorname{clip}\left(b+t|C_i|,0,1\right)
\]

where \(b\) is `base-turnout` and \(t\) is `turnout-sensitivity`. The result is clipped to the interval `[0, 1]`, and the model makes a random draw against that probability.

Thus, the sign of `choice-score` determines **which party** the voter prefers, while its absolute magnitude represents **strength of preference** and increases the probability of turnout. Strongly Blue and strongly Red voters are therefore both more likely to participate than nearly indifferent voters.

In summary, the non-rule-based model combines policy proximity, partisan identity, and an election-specific random influence into one numerical preference; chooses the party favored by the sign of that value; and then uses the strength of the preference to determine turnout probability.

## Party adaptation

### Losing party

The losing party combines two possible targets:

- **Electoral target:** the mean ideology of opposing voters whose absolute choice score is no greater than `persuadable-band`—voters the party narrowly failed to win.
- **Base target:** the mean ideology of voters who supported the losing party.

The combined target is:

```text
target =
  (1 - base-pressure) * electoral-target
  + base-pressure * base-target
```

The party then closes a fraction `party-adaptation` of the remaining distance to that target.

At `base-pressure = 0`, the loser responds entirely to narrowly lost opposing voters. At `base-pressure = 1`, it responds entirely to its current supporters.

### Winning party

The winning party may move toward the mean ideology of its own supporters. `winner-base-adaptation` controls the fraction of the remaining distance moved. At zero, only the losing party adapts.

Setting `adaptive-parties?` to off freezes both party positions after setup.

## Partisan identity

After casting a ballot, a voter’s `party-identity` moves toward the chosen party:

```text
new identity =
  (1 - identity-reinforcement) * old identity
  + identity-reinforcement * vote choice
```

Blue is coded as `-1` and Red as `+1`. This creates path dependence: repeated support for a party can make future support more likely even when ideology remains unchanged. Abstention produces no identity reinforcement and does not erase the voter’s previous non-abstaining vote.

## Social network and opinion change

When `social-network?` is on, the model constructs an undirected voter network with an approximate average degree set by `network-degree`.

`homophily` governs link acceptance:

- `0`: ideological similarity does not affect link formation.
- `1`: acceptance declines linearly with ideological distance.
- Intermediate values blend random connection and similarity-based connection.

The network persists between elections. After changing `network-degree` or `homophily`, click **REBUILD NETWORK** to replace the existing links.

After each election, each voter moves a fraction `social-influence` toward the mean ideology of linked neighbors, then receives normally distributed random movement with standard deviation `opinion-drift`.

Opinion updating is synchronous: all voters calculate `next-ideology` from the old state before any voter adopts its new value. This prevents NetLogo’s agent execution order from becoming an unintended causal mechanism.

## Interface parameters

### Electorate construction

| Parameter | Meaning | Default |
|---|---|---:|
| `electorate-shape` | One centered distribution (`single-peaked`) or two ideological camps (`two-camp`) | `single-peaked` |
| `population` | Number of voter agents | `500` |
| `ideology-spread` | Standard deviation within the ideological distribution or each camp | `0.25` |
| `electorate-polarization` | Absolute location of the two camp centers | `0.35` |
| `identity-noise` | Initial random mismatch between ideology and partisan identity | `0.35` |

`electorate-polarization` has no effect in the `single-peaked` condition.

### Party construction and adaptation

| Parameter | Meaning | Default |
|---|---|---:|
| `initial-party-gap` | Initial distance between Blue and Red | `1.0` |
| `adaptive-parties?` | Enables or disables post-election party movement | On |
| `party-adaptation` | Fraction of the distance the loser moves toward its target | `0.25` |
| `persuadable-band` | Maximum absolute choice score for a narrowly lost opposing voter | `0.25` |
| `base-pressure` | Weight assigned to current supporters in the loser’s target | `0.15` |
| `winner-base-adaptation` | Fraction of the distance the winner moves toward its supporters | `0.03` |

### Vote choice, identity, and turnout

| Parameter | Meaning | Default |
|---|---|---:|
| `identity-strength` | Weight of partisan identity in vote choice | `0.6` |
| `identity-reinforcement` | Rate at which voting strengthens partisan identity | `0.03` |
| `base-turnout` | Baseline probability of participation | `0.55` |
| `turnout-sensitivity` | Additional turnout associated with preference strength | `0.12` |
| `election-noise` | Standard deviation of election-specific vote shocks | `0.08` |

### Network and opinion change

| Parameter | Meaning | Default |
|---|---|---:|
| `social-network?` | Enables network construction and influence | Off |
| `network-degree` | Approximate average number of links per voter | `6` |
| `homophily` | Strength of ideological similarity in link formation | `0.7` |
| `social-influence` | Fraction of distance moved toward neighbors’ mean ideology | `0.08` |
| `opinion-drift` | Standard deviation of random ideological change | `0.01` |
| `show-links?` | Shows or hides links without changing their effects | Off |

## Controls

| Control | Action |
|---|---|
| **SETUP** | Creates a new electorate, resets parties and statistics, and optionally builds a network |
| **GO** | Runs elections continuously |
| **ONE ELECTION** | Runs exactly one complete election cycle |
| **REBUILD NETWORK** | Discards current links and builds a new network using current settings |
| **RESET PARTY POSITIONS** | Restores the initial party gap without recreating voters or links |
| **EXPORT HISTORY (TSV)** | Saves one tab-separated row per election |

## Outputs

The interface reports:

- Blue and Red vote share among ballots cast
- turnout as a percentage of all voters
- absolute election margin in percentage points
- running mean election margin
- number of changes in party control
- Blue and Red policy positions
- party gap
- vote switching among participating repeat voters

The plots show:

- vote shares over time, including a 50% parity line
- party positions over time
- election margin and turnout
- the current voter ideology distribution

### Export format

`EXPORT HISTORY (TSV)` writes the following columns:

```text
election
winner
blue-share
red-share
turnout
margin
blue-position
red-position
party-gap
mean-ideology
switch-rate
```

The file includes a header row and one row for every completed election.

## Included BehaviorSpace experiments

Open **Tools → BehaviorSpace** to run the included experiments.

### Parity sweep — adaptation × base pressure

- 10 repetitions per condition
- 100 elections per run
- `party-adaptation`: `0.0` through `0.5` in increments of `0.1`
- `base-pressure`: `0`, `0.25`, `0.5`, `0.75`, `1`
- social network disabled

Recorded outcomes include mean margin, control-change rate, party gap, party positions, and turnout.

### Network sweep — homophily × social influence

- 10 repetitions per condition
- 100 elections per run
- two-camp electorate
- `homophily`: `0`, `0.25`, `0.5`, `0.75`, `1`
- `social-influence`: `0`, `0.05`, `0.1`, `0.2`, `0.4`

Recorded outcomes include mean margin, control-change rate, party gap, mean voter ideology, and vote switching.

## Suggested experiments

### Does adaptation generate parity?

Disable social influence, identity reinforcement, opinion drift, and winner movement. Compare fixed parties with several levels of losing-party adaptation. Examine mean margin, control changes, and final party gap.

### Electoral responsiveness versus base pressure

Sweep `base-pressure` from `0` to `1`. Test whether pursuit of narrowly lost voters produces convergence while responsiveness to existing supporters preserves or increases separation.

### Partisan lock-in

Compare `identity-reinforcement = 0` with positive values. Examine whether early random outcomes reduce later switching and produce persistent electoral histories.

### Network homophily and polarization

Use a two-camp electorate and vary both `homophily` and `social-influence`. Rebuild the network for each structural condition and compare the ideology distribution with electoral margins.

### Turnout and apparent parity

Vary `turnout-sensitivity`. Close vote shares need not imply an evenly divided full electorate when participation depends on preference strength.

## Interpreting results

The model is not intended to prove why any particular real political system produces close elections. A defensible result should instead take the form:

> Under this explicit set of assumptions, mechanism X is sufficient—or insufficient—to generate pattern Y over repeated simulations.

Because setup, vote choice, turnout, link formation, and opinion drift are stochastic, conclusions should be based on repeated runs rather than a single visually interesting trajectory.

## Limitations

The model contains:

- one ideological dimension
- exactly two parties
- no primaries or third parties
- no districts or electoral institutions
- no incumbency, campaign spending, candidate quality, or economic state
- highly simplified party learning rules
- information available to parties that real organizations may not possess

These omissions define the scope of the experiment. Extensions are most informative when they introduce one new mechanism at a time while preserving a comparable baseline.

## Possible extensions

Potential additions include asymmetric party strategies, primary electorates, third parties, incumbency, issue salience, economic shocks, district-based elections, endogenous turnout campaigns, and comparison with historical two-party vote-share data.

## Code organization

The NetLogo source is organized into named procedures corresponding to the conceptual stages of the model:

- `setup`, `setup-parties`, and `setup-voters`
- `go` and `run-election`
- `adapt-parties`, `move-losing-party`, and `move-winning-party`
- `update-voter-states`
- `build-network`
- `update-summary-statistics` and `update-display`
- `record-history` and `export-history`

The source file is intentionally heavily commented so it can be read as a teaching text as well as executed as a model.

# Session summaries

`seshsums/` holds one file per working session, `YYYYMMDDHHMM_seshsum.md`,
recording what was built, what was decided and why, and the model behaviours that
would otherwise be rediscovered the hard way. Same stamp convention as the
experiment folders, and for the same reason: several a day, so the minute is part
of the name.
