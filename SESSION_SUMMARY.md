# Session summary — 2026-08-07

A record of what was built, what was decided, and what was found, so the next
person into this repository does not have to reconstruct it from the diff.

## The task

Convert the NetLogo model to Python, build an experimental jig to run
experiments, and push the result. Partway through, the direction changed: stop
matching NetLogo, and generalize the model.

## What was here at the start

Four NetLogo files, a README documenting the model as a teaching text, and two
PDFs. Commit `26cd8a3`. Running an experiment meant opening NetLogo and driving
BehaviorSpace through its GUI.

The four `.nlogo` files are two models times two editions: a base model and a
production-rules variant, each with a heavily commented teaching edition. The
commented editions differ from their plain counterparts **only in comments** —
verified by diffing the code sections — so there were two models to port, not
four, and `adaptive_two_party_model_production_rules.nlogo` is the superset of
both.

## Decisions taken

| Decision | Choice | Why |
|---|---|---|
| Port structure | One unified model | The production-rules `.nlogo` already contains both voter models behind one switch; mirroring that gives one codebase, not two |
| Dependencies | numpy throughout | Sweeps are the point, and vectorized voters run a 100-election model in ~10 ms |
| Git workflow | Straight to `main` | Matches the repo's existing flat history |
| Validation | No NetLogo comparison | NetLogo is not installed here; correctness rests on unit tests and known-answer property tests instead |
| Results layout | `results/<experiment>/manifest.json` | Requested mid-flight; a results folder should describe itself |
| General model | Supersede, don't replace | The NetLogo-faithful model stays frozen as a reference; the general model carries no obligation to reproduce it |

## What was built

**`polimods/`** — the model. One `Model` class with a method per NetLogo
procedure, so the two sources read side by side. `Params` carries the interface
slider ranges and rejects values the NetLogo interface could not have produced.
`production_system=False` gives the weighted-choice equation; `True` gives the
eight IF-THEN rules. The display layer is not ported — the README is explicit
that the screen is a graph of the model rather than its causal space.

Vectorizing voters is safe because every voter-level computation in the NetLogo
is order-independent, and opinion updating is explicitly synchronous. The one
order-dependent procedure, `build_network`, stays sequential: its rejection
sampling tests membership against a set that grows during the loop, so batching
the proposals would change the model rather than just speed it up.

**`polimods/jig/`** — the experimental jig, replacing BehaviorSpace. TOML specs
using BehaviorSpace's vocabulary, expanded and validated against the slider
ranges *before* the first run, so a typo fails immediately rather than 200 runs
in. Runs fan out across processes. Seeds derive from
`(base_seed, condition_index, repetition)`, so a single run reproduces in
isolation and adding conditions to a spec does not reshuffle the seeds of the
conditions already there. Re-running never clobbers an old folder — it
auto-suffixes and records the collision.

**`experiments/`** — both included BehaviorSpace experiments ported exactly,
plus a new 256-condition full factorial over the eight production rules. The
NetLogo ships the production system but no experiment that exercises it.

**`tests/`** — 143 tests: each formula against hand-computed values, every
production rule at its threshold, network construction, and whole-model
behaviour in regimes where the answer is known independently.

**`docs/PORTING.md`** — the procedure-by-procedure mapping, the deviations, and
the faithful-but-surprising behaviours listed below.

## Findings

### From the experiments — 3110 runs, 6.8 s on 12 processes

**`parity_sweep`** reproduces the model's central claim. With
`party_adaptation = 0` the party gap holds at 0.68, the mean margin is 17–20
points, and control changes almost never (0.7–3.6%): one party simply wins. Any
adaptation collapses the gap to 0.11–0.41, the margin to about 3 points, and
control changes to 40–50% — near coin-flip parity. `base_pressure` raises the gap
monotonically at every adaptation level, which is the direction the README
predicts: chasing narrowly-lost voters converges, retreating to the base
preserves separation.

**`network_sweep`** initially came out completely flat, which turned out to be a
metric problem rather than a mechanism problem. Social influence works
dramatically — it collapses ideology spread from 0.44 to 0.05 — but none of the
metrics the original BehaviorSpace recorded can see it: both electorate shapes
are symmetric, so `mean_voter_ideology` sits near zero whatever happens, and
`switch_rate` is a final-election snapshot that has already locked to zero by
roughly election 40. Adding `ideology_sd` made the sweep legible: any social
influence collapses the two camps, and homophily consistently slows that
collapse (0.050 → 0.062 at influence 0.05).

**`rule_ablation`** gives clean main effects. `rule_neighbors` is the standout:
enabling it takes the mean margin from 4.7 to **33.9** points — social conformity
manufactures landslides. `rule_habit` drives vote switching from 18.6% to 0.003%.
`rule_indifference` is the turnout lever, 55.2% → 43.5%. Three rules are inert
in this configuration — engagement, alienation, and cross-pressure — for a
legible reason: all three test policy distance or identity against thresholds
that converged parties and a socially-collapsed electorate never reach.

### Behaviours worth knowing before reading any result

These are faithful to the NetLogo. Each is recorded in `docs/PORTING.md` because
each one surprises people.

- **`party_adaptation = 0` is not a no-movement control.** `move_losing_party`
  scales by `party_adaptation`, but `move_winning_party` scales by
  `winner_base_adaptation`, which defaults to 0.03. The winner keeps drifting
  toward its own supporters — who sit between the party and the centre — closing
  the gap from 1.00 to 0.68 over 100 elections on its own. This surfaced as a
  failing property test whose *expectation* was wrong, not whose code was.
- **Integer choice scores meet a fractional persuadable band.** Under the
  production system `choice_score` is a count of reasons, so it is an integer —
  except for tie-broken voters, who get exactly ±0.001. `move_losing_party`
  selects persuadables with `abs(choice_score) <= persuadable_band`, default
  0.25. No ordinary voter can satisfy that. The losing party's electoral target
  is therefore computed from tie-broken voters alone, or falls back to the whole
  electorate.
- **Homophily sorts weakly in a single-peaked electorate.** Acceptance is
  `1 - |ΔI| / 2`; when ideologies cluster near the centre there is little
  distance to work with, and assortativity rises only 0.00 → 0.09 across the full
  homophily range. In a two-camp electorate the same code gives 0.00 → 0.39. The
  mechanism is fine; its leverage depends on the electorate.
- **A choice score of exactly zero votes Red**, and **abstention does not erase
  partisan history** — abstainers keep the `last_vote` from whenever they last
  participated.
- **`control_change_rate` divides by ticks, not elections**, because NetLogo
  computes it before incrementing the tick counter.

### On the port itself

Python and NetLogo runs can never be bit-identical: different generators, and
vectorization consumes draws in a different order. Reproducibility is per-seed
within Python. This port was not validated against a live NetLogo run.

## Commits

- `1fe9762` — Python port and experimental jig
- `711e087` — results from the three shipped experiments

## Where it stands

Done and pushed. The general model is in progress and **not yet committed**:
`polimods/general/` currently holds `space.py`, `state.py`, `rules.py`,
`decision.py`, and `institutions.py`. It is incomplete — party strategies with
entry and exit, the config and model loop, generalized metrics, dotted-path
sweep support in the jig, tests, and documentation are all still outstanding —
so it is deliberately held back from `main` rather than pushed half-finished.

### The general model being built

Four axes were requested, all at once:

- **N parties** — an arbitrary party set with entry, exit, and per-party
  strategies, replacing hard-coded Blue and Red.
- **Multi-dimensional ideology** — positions become vectors, distance becomes a
  salience-weighted norm, and two voters at the same point can rank the same
  parties differently because they weigh issues differently.
- **Pluggable decision rules** — a rule is one independent reason, returning a
  utility surface and/or a turnout term. Combination is a separate concern, so
  the same rule set can be read as a weighted sum, as a count of discrete
  reasons, or as a random-utility logit.
- **Electoral institutions** — popular vote, first-past-the-post with districts,
  proportional representation with a threshold and a choice of divisor
  sequences, and a two-round runoff; plus districting schemes including a
  minimal gerrymander.

The jig is largely model-agnostic already — it sweeps a parameter object and
records whatever a model exposes as metrics — but it needs dotted-path support
before it can drive a nested config.
