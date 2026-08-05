# Adaptive Two-Party Competition with Voter Productions

A NetLogo model of repeated electoral competition between two adaptive political parties. The model now supports two alternative voter decision architectures:

1. an original continuous weighted-choice equation; and
2. an explicit production system in which every voter executes the same switchable IF-THEN rules.

The model asks:

> Can two adaptive parties generate persistent electoral parity, and how does that outcome change when voters are represented as rule-following agents rather than as weighted utility calculations?

Each tick represents one election. Voters choose a party and decide whether to participate; parties respond to the result; partisan identity and voter ideology may then change before the next election.

## Files

- `adaptive_two_party_model_production_rules.nlogo` — streamlined working model.
- `adaptive_two_party_model_production_rules_commented.nlogo` — heavily commented teaching and development version with identical Interface settings and behavior.

Both files are saved in NetLogo 6.4.0 format.

## Requirements

- [NetLogo 6.4.0](https://ccl.northwestern.edu/netlogo/)

Later NetLogo 6.x releases may also work, but have not been verified here.

## Quick start

1. Open either model file in NetLogo.
2. Click **SETUP**.
3. Leave `production-system?` on to use the rule-based voters, or turn it off to use the original weighted equation.
4. Click **ONE ELECTION** to advance once, or **GO** to run continuously.
5. Turn individual `rule-...?` switches on or off to perform rule-ablation experiments.
6. Inspect a voter after an election to view its reason counts and `rule-trace`.
7. Use **EXPORT HISTORY (TSV)** to save election-level outcomes.

## Central modeling distinction

Voters and parties have an **internal political state**. Their positions in the NetLogo world only display that state.

- A voter’s horizontal screen position represents its internal `ideology`.
- A voter’s vertical position is arbitrary visual jitter.
- Party stars display `blue-position` and `red-position`.
- Social effects follow explicit network links.

Voting, rule firing, and party adaptation never use `xcor`, `ycor`, turtle distance, patch location, or spatial neighborhoods. The screen is a graph of the model, not its causal political space.

## Agents and state

The model contains:

- **Voters**, each with ideology, partisan identity, vote history, turnout state, and production-system working memory.
- **Two parties**, Blue and Red, displayed as star-shaped turtles.
- **Undirected social links**, through which previous votes can trigger a neighbor rule and ideologies can converge.

Ideology and party positions lie on a one-dimensional scale from `-1` to `+1`. Blue is constrained to remain to the left of Red, with a minimum gap of `0.02`.

### Voter working memory

During each production-system election, every voter resets and fills:

| Variable | Meaning |
|---|---|
| `blue-reasons` | Number of fired productions favoring Blue |
| `red-reasons` | Number of fired productions favoring Red |
| `turnout-reasons` | Number of fired productions encouraging participation |
| `abstention-reasons` | Number of fired productions discouraging participation |
| `intended-choice` | Party selected before the turnout draw (`-1` or `+1`) |
| `rule-trace` | Readable record of productions that fired |

A trace might look like:

```text
policy->Blue; identity->Blue; strong-identity->turnout;
```

## Election cycle

Every call to `go`:

1. reconciles the social network with the current switches;
2. runs either the production system or weighted voter model;
3. counts votes and determines the winner;
4. adapts the losing party and optionally the winner;
5. reinforces partisan identity among voters;
6. updates ideology through peers and random drift;
7. updates statistics, plots, display positions, and history; and
8. advances the tick counter.

The order is theoretically meaningful: parties respond to the electorate that just voted, and voters change before the following election.

## Selecting the voter architecture

### Production system

Turn `production-system?` on. Each voter executes the same enabled rules. The rules are independent `if` statements rather than an exclusive `ifelse` chain, so several can fire simultaneously.

Rules add discrete reasons. They do not contribute continuously weighted values. After all rules fire:

```text
choice-score = red-reasons - blue-reasons
```

- A negative result produces an intended Blue vote.
- A positive result produces an intended Red vote.
- An exact tie is resolved stochastically and stored as `-0.001` or `+0.001`.

Turnout is:

```text
base-turnout
+ turnout-sensitivity * (turnout-reasons - abstention-reasons)
```

The result is clipped to `[0, 1]`, after which turnout is drawn probabilistically.

### Original weighted model

Turn `production-system?` off. Party preference is then computed as:

```text
|ideology - blue-position|
- |ideology - red-position|
+ identity-strength * party-identity
+ election noise
```

Negative values favor Blue and positive values favor Red. Turnout rises continuously with the absolute magnitude of this score.

The rest of the model—party adaptation, identity reinforcement, opinion updating, plots, and export—is shared between the two architectures.

## Preliminary production rules

The thresholds are currently constants grouped near the top of `run-production-system`. The rule switches are on by default.

| Switch | IF condition | THEN action | Threshold |
|---|---|---|---:|
| `rule-policy?` | One party is substantially closer than the other | Add one party reason | Policy advantage exceeds `0.15` in magnitude |
| `rule-identity?` | Effective partisan identity is sufficiently strong | Add one party reason | Effective identity reaches `±0.25` |
| `rule-habit?` | The voter has a previous non-abstaining vote | Add one reason for the previously chosen party | None |
| `rule-neighbors?` | A clear majority of active linked neighbors previously chose one party | Add one party reason | At least `60%` |
| `rule-engagement?` | Policy preference or effective identity is strong | Add a turnout reason for each activated condition | Policy `0.35`; identity `0.60` |
| `rule-indifference?` | The parties are nearly equally attractive on policy | Add one abstention reason | Difference no greater than `0.15` |
| `rule-alienation?` | Even the closer party is far away | Add one abstention reason | Nearest distance at least `0.55` |
| `rule-cross-pressure?` | Policy and identity clearly favor opposite parties | Add one abstention reason | Uses policy and identity thresholds above |

### Identity strength in the production model

`identity-strength` is retained in both architectures, but its role differs:

- In the weighted model it continuously scales identity’s contribution to `choice-score`.
- In the production system it scales `party-identity` before threshold comparison, determining whether identity productions activate.

### Independent cross-pressure rule

`rule-cross-pressure?` evaluates the underlying policy and identity directions directly. It can therefore fire even when `rule-policy?` or `rule-identity?` is off. Turning those party-choice rules off removes their reasons; it does not make the voter incapable of being cross-pressured.

### Neighbor rule versus opinion influence

The model contains two distinct social mechanisms:

- `rule-neighbors?` uses linked neighbors’ **previous votes** to add a current party reason.
- `social-influence` moves the voter’s **ideology** toward linked neighbors’ mean ideology after the election.

Enabling both means the network affects voting directly and also changes the state on which future voting depends.

## Important interaction with party adaptation

The losing party identifies “persuadable” opposing voters with:

```text
abs(choice-score) <= persuadable-band
```

The meaning differs across voter architectures:

- Under the weighted model, `choice-score` is continuous, so `persuadable-band` selects a conventional interval of weak preferences around zero.
- Under the production system, `choice-score` is normally an integer reason-count difference. With the default `persuadable-band = 0.25`, a one-reason advantage is outside the band; essentially only exact reason ties, stored as `±0.001`, count as persuadable.

Set `persuadable-band` to at least `1` to include voters whose decision was made by a one-reason margin. This is not merely a scaling detail: it changes which voters the losing party treats as electorally reachable.

## Party adaptation

### Losing party

The losing party combines two targets:

- **Electoral target:** mean ideology of opposing voters satisfying the persuadable criterion.
- **Base target:** mean ideology of voters who supported the losing party.

```text
target =
  (1 - base-pressure) * electoral-target
  + base-pressure * base-target
```

The loser closes a fraction `party-adaptation` of the distance to this target.

At `base-pressure = 0`, it responds entirely to persuadable opponents. At `base-pressure = 1`, it responds entirely to its current supporters.

### Winning party

The winner may move toward the mean ideology of its supporters. `winner-base-adaptation` controls the fraction of the remaining distance moved. At zero, only the loser adapts.

Turning `adaptive-parties?` off freezes party positions after setup.

## Partisan identity

After voting, `party-identity` moves toward the chosen party:

```text
new identity =
  (1 - identity-reinforcement) * old identity
  + identity-reinforcement * vote choice
```

Blue is `-1`; Red is `+1`. Repeated voting can therefore create path dependence. Abstention causes no reinforcement and does not erase the voter’s previous non-abstaining vote.

## Social network and opinion change

When `social-network?` is on, the model constructs an undirected network with approximate mean degree `network-degree`.

`homophily` governs link acceptance:

- `0`: ideological similarity has no effect;
- `1`: acceptance declines linearly with ideological distance;
- intermediate values blend random connection and similarity-based connection.

The network persists between elections. After changing `network-degree` or `homophily`, click **REBUILD NETWORK**.

After each election, each voter moves a fraction `social-influence` toward linked neighbors’ mean ideology and receives normal random movement with standard deviation `opinion-drift`.

Opinion updating is synchronous: all voters calculate `next-ideology` from the old state before any voter adopts a new value.

## Interface parameters

### Electorate construction

| Parameter | Meaning | Default |
|---|---|---:|
| `electorate-shape` | One centered distribution or two ideological camps | `single-peaked` |
| `population` | Number of voter agents | `500` |
| `ideology-spread` | Standard deviation within the electorate or each camp | `0.25` |
| `electorate-polarization` | Absolute position of the two camp centers | `0.35` |
| `identity-noise` | Initial random mismatch between ideology and partisan identity | `0.35` |

### Decision architecture and rules

| Parameter | Meaning | Default |
|---|---|---:|
| `production-system?` | Selects production rules rather than the weighted equation | On |
| `rule-policy?` | Enables policy-proximity reasons | On |
| `rule-identity?` | Enables partisan-identity reasons | On |
| `rule-habit?` | Enables previous-vote reasons | On |
| `rule-neighbors?` | Enables linked-neighbor majority reasons | On |
| `rule-engagement?` | Enables strong-preference turnout reasons | On |
| `rule-indifference?` | Enables near-equality abstention reasons | On |
| `rule-alienation?` | Enables distance-from-both abstention reasons | On |
| `rule-cross-pressure?` | Enables policy/identity conflict abstention | On |

With all production rules off, party choice is a stochastic tie-break and turnout remains `base-turnout`.

### Party construction and adaptation

| Parameter | Meaning | Default |
|---|---|---:|
| `initial-party-gap` | Initial distance between Blue and Red | `1.0` |
| `adaptive-parties?` | Enables post-election party movement | On |
| `party-adaptation` | Fraction of the distance the loser moves toward its target | `0.25` |
| `persuadable-band` | Maximum absolute `choice-score` for a narrowly lost opposing voter | `0.25` |
| `base-pressure` | Weight assigned to current supporters in the loser’s target | `0.15` |
| `winner-base-adaptation` | Fraction of the distance the winner moves toward supporters | `0.03` |

### Identity, turnout, and noise

| Parameter | Meaning | Default |
|---|---|---:|
| `identity-strength` | Identity weight or threshold scaling, depending on architecture | `0.6` |
| `identity-reinforcement` | Rate at which voting strengthens partisan identity | `0.03` |
| `base-turnout` | Baseline participation probability | `0.55` |
| `turnout-sensitivity` | Continuous preference effect or per-reason turnout step | `0.12` |
| `election-noise` | Weighted-model shock and production tie-break source | `0.08` |

### Network and opinion change

| Parameter | Meaning | Default |
|---|---|---:|
| `social-network?` | Enables network construction and influence | Off |
| `network-degree` | Approximate average number of links per voter | `6` |
| `homophily` | Strength of ideological similarity in link formation | `0.7` |
| `social-influence` | Fraction moved toward neighbors’ mean ideology | `0.08` |
| `opinion-drift` | Standard deviation of random ideological change | `0.01` |
| `show-links?` | Shows or hides links without changing effects | Off |

## Controls

| Control | Action |
|---|---|
| **SETUP** | Creates a new electorate, resets parties and statistics, and optionally builds a network |
| **GO** | Runs elections continuously |
| **ONE ELECTION** | Runs one complete election cycle |
| **REBUILD NETWORK** | Replaces links using current network settings |
| **RESET PARTY POSITIONS** | Restores the initial gap without recreating voters or links |
| **EXPORT HISTORY (TSV)** | Saves one tab-separated row per election |

## Outputs

The Interface reports:

- Blue and Red vote share among ballots cast;
- turnout as a percentage of all voters;
- absolute election margin;
- running mean margin;
- changes in party control;
- Blue and Red policy positions;
- party gap; and
- switching among participating repeat voters.

Plots show vote share, party positions, election margin and turnout, and the current ideology distribution.

### Export format

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

## Included BehaviorSpace experiments

Two experiments are included under **Tools → BehaviorSpace**:

- **Parity sweep — adaptation × base pressure**
- **Network sweep — homophily × social influence**

Both explicitly set `production-system?` to false, preserving comparability with the original weighted-model experiments. New production-system experiments should add the master switch and desired rule-switch conditions explicitly.

## Suggested production-system experiments

### Rule ablation

Run an all-rules baseline, then turn off one rule at a time. Compare vote share, turnout, switching, party-control changes, party gap, and mean margin.

Particularly informative contrasts are:

- policy versus identity;
- habit on versus off over long runs;
- indifference versus alienation;
- cross-pressure with and without identity reinforcement; and
- neighbor voting influence with and without ideological social influence.

### Architecture comparison

Use identical random seeds and parameters where possible, switching only `production-system?`. Remember that `persuadable-band` is not directly scale-equivalent across architectures.

### Rule interactions

The rules are additive and nonexclusive. Test combinations rather than interpreting single-rule effects as independent. For example, habit and identity reinforcement can create a feedback loop, while neighbor voting and social influence can create two simultaneous network pathways.

## Important limitations

- The rules and thresholds are preliminary theoretical propositions, not fitted empirical estimates.
- Every voter has the same productions; heterogeneity comes only from state and network position.
- Party conflict resolution is a reason count, so all fired party reasons currently have equal strength.
- Turnout effects occur in equal steps of `turnout-sensitivity`.
- Tie-breaking remains stochastic.
- The ideological space is one-dimensional.
- The model has two parties, no incumbency, no districts, no primaries, and no changing external political environment.
- Party adaptation uses actual voters and reason-score margins rather than strategic expectations or polling.

The model is intended to test whether a small set of mechanisms can generate qualitative patterns, not to predict a particular election.

## Extending the model

Natural next steps include exposing rule thresholds as sliders, assigning heterogeneous rule sets or priorities to voters, allowing rules to learn or change, adding rule-specific strengths, separating campaign and long-term social influence, revising the persuadable definition for reason-based voters, or fitting aggregate outcomes to historical election series.
