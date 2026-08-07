# Porting notes: NetLogo to Python

The Python package in `polimods/` is a translation of
`adaptive_two_party_model_production_rules.nlogo`, which is the superset of the
four NetLogo files in this repository: it contains the original weighted-choice
voter model *and* the eight-rule production system, selected by one switch.

The `_commented` NetLogo files differ from their plain counterparts only in
comments — the code sections are otherwise identical — so there is one Python
model rather than four.

## Procedure mapping

| NetLogo | Python | Notes |
|---|---|---|
| `setup` | `Model.setup` | Called from `Model.__init__` |
| `setup-background`, `setup-parties` | — | Display only; not ported |
| `setup-voters` | `Model.setup_voters` | |
| `go` | `Model.step` | `Model.run(n)` calls it `n` times |
| `run-election` | `Model.run_election` | |
| `run-weighted-choice-model` | `Model.run_weighted_choice_model` | |
| `run-production-system` | `rules.run_production_system` | |
| `adapt-parties` | `Model.adapt_parties` | |
| `move-losing-party` | `Model.move_losing_party` | |
| `move-winning-party` | `Model.move_winning_party` | |
| `enforce-party-order` | `Model.enforce_party_order` | |
| `update-voter-states` | `Model.update_voter_states` | |
| `update-summary-statistics` | `Model.update_summary_statistics` | |
| `update-display` | — | Display only; not ported |
| `build-network` | `network.build_network` | |
| `record-history` | `Model.record_history` | |
| `export-history` | `History.export_tsv` | Same columns, rounding, and number format |
| `reset-party-positions` | `Model.reset_party_positions` | |
| `clamp-value` | `model.clamp_value` | `np.clip` |
| BehaviorSpace | `polimods.jig` | See the README |

Interface sliders, switches, and the chooser become fields of
`polimods.params.Params`, with hyphens and trailing `?` converted to Python
naming (`party-adaptation` → `party_adaptation`, `social-network?` →
`social_network`). Slider minima, maxima, and step sizes are transcribed into
`params.BOUNDS` and enforced by `Params.validate()`, so the Python model cannot
be handed a value the NetLogo interface could not have produced.

## Deliberate deviations

### 1. Different random number generator

NetLogo uses a Mersenne Twister; the port uses numpy's PCG64 via
`np.random.default_rng`. Vectorization also means draws are consumed in a
different order — one array of 500 normals rather than 500 scalar draws
interleaved with other work.

**Consequence:** a Python run and a NetLogo run with the same seed are not
bit-identical, and never can be. Reproducibility is per-seed *within* Python:
the same `Params` and seed always give the same result, and `jig` derives every
run's seed deterministically from `(base_seed, condition_index, repetition)`.

This port has not been validated against a live NetLogo run. Correctness rests
on unit tests against hand-computed values (`tests/test_model.py`,
`tests/test_rules.py`) and on property tests in regimes where the answer is known
independently of either implementation (`tests/test_properties.py`).

### 2. No display layer

`xcor`, `ycor`, `display-y`, turtle colors and shapes, patch colors, link
visibility, plots, and monitors are not ported. The README is explicit that the
screen is a graph of the model rather than its causal space: voting and party
adaptation read `ideology`, `party_identity`, `blue_position`, and
`red_position`, never geometry. Dropping the display therefore removes nothing
the model uses.

`show-links?` is likewise absent: it changes only whether links are drawn.

### 3. `production_system` defaults to off

The production-rules NetLogo interface ships with `production-system?` switched
**on**. `Params()` defaults it to **off**, so a bare `Model(Params())` reproduces
`adaptive_two_party_model.nlogo` — the model the README documents and the one
both shipped BehaviorSpace experiments actually use.

Use `Params.production_rules_defaults()` for the production-rules interface
defaults. All eight `rule_*` switches default to on either way, matching NetLogo.

### 4. Vectorized voters

Voters are numpy arrays rather than turtles. This is safe because every
voter-level computation in the NetLogo is independent of execution order:
`run-election` reads only each voter's own state, and `update-voter-states`
computes `next-ideology` for everyone before anyone adopts it — NetLogo makes
that synchrony explicit precisely so agent ordering cannot become a hidden
mechanism.

The one order-dependent procedure, `build-network`, stays sequential. Its
rejection sampling checks "are these two already linked?" against a set that
grows during the loop, so batching the proposals would change the model rather
than just speed it up. Random draws are pulled in chunks, which changes nothing
distributionally.

## Behaviours worth knowing about

These are faithful to the NetLogo. They are recorded here because each one
surprises people reading results.

### Integer choice scores meet a fractional persuadable band

Under the production system, `choice_score` is a count of reasons
(`red_reasons - blue_reasons`), so it takes integer values — except for
tie-broken voters, who receive exactly ±0.001.

`move_losing_party` selects persuadable opponents with
`abs(choice_score) <= persuadable_band`, whose default is 0.25. With integer
scores, **no** ordinary voter can satisfy that test: the only voters inside the
band are the ones whose reasons tied. So under the production system with default
settings, the losing party's electoral target is computed from tie-broken voters
alone, or falls back to the mean of the entire electorate when there are none.

This is what the NetLogo does. If you want the persuadable band to select a
meaningful group under the production system, raise it above 1.

### `party_adaptation = 0` is not a no-movement control

`move_losing_party` scales by `party_adaptation`, but `move_winning_party` scales
by `winner_base_adaptation`, which defaults to 0.03. With `party_adaptation = 0`
and everything else at its default, the parties still converge — the winner keeps
drifting toward its own supporters, who sit between the party and the centre.
Over 100 elections that alone closes the gap from 1.00 to roughly 0.68.

For a genuinely frozen baseline, set `adaptive_parties = False`, or zero both
`party_adaptation` and `winner_base_adaptation`.

### A score of exactly zero votes Red

`ifelse choice-score < 0 [ -1 ] [ 1 ]` sends only strictly negative scores to
Blue. With continuous election noise this almost never matters; with
`election_noise = 0` and a perfectly centred voter it does.

### Abstention does not erase partisan history

Identity reinforcement and `last_vote` update only for voters who cast a ballot.
A voter who abstains keeps the `last_vote` from whenever they last participated,
which is what the habit rule and the switch-rate denominator both read.

### `control_change_rate` divides by ticks, not elections

`update-summary-statistics` runs before `tick`, so after *n* elections the rate
is `100 * changes / (n - 1)`. Likewise `mean_margin` divides by `ticks + 1`,
making it the true mean over all *n* completed elections.

### Homophily sorts weakly in a single-peaked electorate

Link acceptance is `(1 - homophily) + homophily * (1 - |Ia - Ib| / 2)`. With
ideologies clustered near the centre, `|Ia - Ib|` is small and the filter has
little to work with: ideological assortativity rises only from about 0.00 to 0.09
as homophily goes from 0 to 1. In a two-camp electorate the same code takes it
from 0.00 to about 0.39. The mechanism is fine; its leverage depends on the
electorate. This is why `experiments/network_sweep.toml` uses `two-camp`, as the
original BehaviorSpace experiment does.

## Metric names

BehaviorSpace reporters map to `Model.METRICS` with hyphens replaced by
underscores: `mean-margin` → `mean_margin`, `control-change-rate` →
`control_change_rate`, `mean-voter-ideology` → `mean_voter_ideology`, and so on.
Two metrics have no NetLogo monitor: `mean_degree` and `link_count`, which report
the realized social network.
