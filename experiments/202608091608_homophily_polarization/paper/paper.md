# Homophily's Bite Depends on Electorate Shape: Manufacturing versus Sharpening Polarization in a Two-Party Model

*Draft. Experiment: `experiments/202608091608_homophily_polarization/`.*

## Abstract

A prior sweep in this project (`network_sweep`) showed that social influence
collapses ideological separation between two pre-existing camps, and that
homophily — the tendency to link with the ideologically similar — slows that
collapse. But `network_sweep` only ever ran a two-camp electorate, so it could
not separate two different claims: that homophily *deepens* a split that
already exists, versus that homophily can *create* a split where none did. This
experiment crosses `electorate_shape` (`single-peaked` vs `two-camp`) with
`homophily` and `social_influence` — 500 runs, 50 conditions, 10 repetitions
each — to test both at once. The result is one-sided: social influence, not
homophily, does almost all of the work of separating or collapsing the two
parties' coalitions, and homophily's own effect, where it is visible at all, is
three to four times larger in the two-camp electorate than in the single-peaked
one. Homophily sharpens; it does not, in this model and this parameter range,
manufacture.

## 1. Motivation

The question is Potential Experiment 6 from the project README: *"Homophily's
bite depends on electorate shape."* The shipped `network_sweep` experiment
(`experiments/202608071014_network_sweep/`) found that any nonzero
`social_influence` collapses ideological spread in a two-camp electorate from
about 0.44 to the 0.05–0.06 range within roughly 40 elections, and that
`homophily` slows this collapse — but only in the range 0.05–0.062 at
`social_influence = 0.05`, a fairly narrow band. That experiment was run
entirely inside a two-camp electorate, so "homophily slows collapse" is the
only claim it can support. It says nothing about whether homophily, given a
population that starts in one hump rather than two, could pull that hump apart
into camps on its own.

That is a different mechanism than "camps resist merging." A homophilous
network in a single-peaked electorate has nothing bimodal to protect; if it
still produces separated coalitions, the separation has to come from the
network dynamics themselves — a self-reinforcing sorting process, not
resistance to convergence. Distinguishing the two matters for how the model's
finding should be read: "homophily preserves existing polarization" and
"homophily generates polarization from a neutral starting point" support very
different real-world claims.

## 2. Model and design

Model: `polimods/`, `production_system = False` (continuous choice-score voter
model), `adaptive_parties = True`, `social_network = True`, `network_degree =
6`, `population = 500`. All other parameters at their NetLogo defaults. Full
parameter provenance is in `manifest.json`.

Sweep (`homophily_polarization.toml`):

| Variable | Values |
|---|---|
| `electorate_shape` | `single-peaked`, `two-camp` |
| `homophily` | 0.0, 0.25, 0.5, 0.75, 1.0 |
| `social_influence` | 0.0, 0.05, 0.1, 0.2, 0.4 |

50 conditions × 10 repetitions = 500 runs, 100 elections each, `base_seed =
20260809`. `social_influence = 0` is included deliberately as a negative
control: with no persuasion, the network can change shape but has no channel
to move anyone, so any effect of `homophily` at `social_influence = 0` would
indicate a bug, not a finding.

## 3. Metrics

`ideology_sd` — the spread of the whole electorate at the final election — is
the metric `network_sweep` used, but it cannot distinguish the two hypotheses
here. A unimodal electorate that stays unimodal and a bimodal electorate whose
two camps have moved close together can land on the same spread; conversely, a
single-peaked electorate that has split into two nearby camps would show only
a modest rise in `ideology_sd`, easy to miss.

`coalition_gap = red_voter_ideology - blue_voter_ideology` at the final
election is the sharper instrument: it is the distance between where each
party's *actual supporters* sit, not the electorate's overall dispersion. A
homophily-driven rise in `coalition_gap` inside `single-peaked` is direct
evidence of manufactured separation — voters are sorting into two
ideologically distinct partisan camps that were not there at setup.

Both metrics are computed per run from the final row of `steps.csv` (written
because the spec sets `run_metrics_every_step = true`) and averaged over each
condition's 10 repetitions. See
`../analyses/manufacture_vs_sharpen.py` for the exact computation and
`../analyses/condition_summary.csv` for the full table.

## 4. Results

### 4.1 The negative control holds

At `social_influence = 0`, `coalition_gap` is flat across the full `homophily`
range in both shapes: 0.363 → 0.365 in `single-peaked` (+0.6%), 0.728 → 0.730
in `two-camp` (+0.3%). Homophily with no influence channel does nothing, as
expected — the sweep is measuring what it claims to.

### 4.2 Social influence dominates; homophily modulates

Turning `social_influence` on from 0 to 0.05 collapses `coalition_gap` by
roughly 20–28× in both electorate shapes (0.363 → 0.015 single-peaked; 0.728 →
0.027 two-camp). Whatever homophily does, it is a second-order effect next to
this.

### 4.3 Where homophily's effect is visible, it is 3–4× stronger in two-camp

At `social_influence = 0.05` — the one influence level weak enough that the
collapse hasn't already swamped the signal — `coalition_gap` rises with
`homophily` in both shapes, but not by the same amount:

| electorate_shape | coalition_gap @ homophily=0 | coalition_gap @ homophily=1 | relative growth |
|---|---:|---:|---:|
| single-peaked | 0.0148 | 0.0182 | +23% |
| two-camp | 0.0265 | 0.0460 | +73% |

`ideology_sd` at the same influence level shows the same pattern: +6.5% in
single-peaked (0.0411 → 0.0438) versus +23% in two-camp (0.0490 → 0.0603).

Pooling across all five `social_influence` levels (`numpy.polyfit`, see
`../analyses/findings.md`), the slope of `coalition_gap` on `homophily` is
+0.0008 in `single-peaked` versus +0.0083 in `two-camp` — a 10× difference —
and the slope of `ideology_sd` is +0.0022 versus +0.0087, a 4× difference.

At `social_influence >= 0.1`, `coalition_gap` has already collapsed to
0.002–0.01 in both shapes, and the run-to-run standard deviation
(`../analyses/condition_summary.csv`, `coalition_gap_sd`) is frequently as
large as the mean itself. Any residual homophily effect at these influence
levels is not distinguishable from noise with 10 repetitions; the finding
above rests on `social_influence = 0.05`, the one setting where the signal is
still visible above the floor.

Full per-condition figures: `../ideology_sd.png`, `../coalition_gap.png`.
Representative dynamics for the clearest single condition pair —
`homophily = 1.0`, `social_influence = 0.05`, one per shape — are
`../political_space_c21.png` (single-peaked) and `../political_space_c46.png`
(two-camp): both show the two parties converging on the electorate's median by
around election 20–30, with the losing party's own coalition centre (dashed
line) trailing behind rather than leading the collapse.

## 5. Discussion

The manufacture hypothesis — that homophily alone can sort a single-peaked
electorate into two ideologically distinct partisan camps — is not supported
in this parameter range. Where an effect of homophily is visible at all, it
runs three to four times weaker in `single-peaked` than in `two-camp`. The
honest reading is closer to `network_sweep`'s original framing than to a new
mechanism: homophily's role is to slow the *merging* of coalitions under
social influence, and it does more of that slowing when there is a
pre-existing bimodal structure for it to protect. Given a genuinely neutral
starting distribution, it has much less to work with, and the electorate
converges to a shared centre almost regardless of who is linked to whom.

This refines rather than contradicts the earlier finding
(`seshsums/202608071041_seshsum.md`): "homophily consistently slows [social
influence's] collapse" turns out to depend on there being a collapse worth
slowing. It is a sharpening/preserving mechanism, not a polarization-generating
one, at least at `network_degree = 6` and the model's default coupling
strengths.

## 6. Limitations

- **One influence level carries the finding.** The clearest signal is at
  `social_influence = 0.05`; at every other nonzero level, `coalition_gap` has
  already collapsed to near-zero in both shapes and the homophily effect is
  within noise. A finer grid between 0 and 0.1 would tell us whether the
  manufacture/sharpen gap widens, narrows, or holds as influence increases
  from zero — this sweep cannot.
- **One network density.** `network_degree = 6` throughout. Sparser or denser
  networks could change how much homophily has to work with before influence
  averages it out.
- **100 elections.** Per Potential Experiment 10 in the README, slow-moving
  channels (identity reinforcement, opinion drift) may not have settled by
  election 100. `run_metrics_every_step` was enabled here, so a longer rerun
  at the same conditions is a direct extension, not a redesign.
- **Two electorate shapes, one polarization level.** `electorate_polarization`
  is fixed at its default (0.35) for `two-camp`; how far apart the initial
  camps start was not varied, and could change how much homophily has to
  protect.
- **10 repetitions per condition.** Sufficient for the mean effects reported,
  but the noise floor discussed in §4.3 means small effects at high influence
  should not be trusted without more repetitions.

## 7. Reproducibility

```
git commit   9ecf204
spec         experiments/202608091608_homophily_polarization/homophily_polarization.toml
base_seed    20260809
runs         500 (50 conditions x 10 repetitions), 100 elections each
wall time    1.46s (12 processes)
```

```bash
python -m polimods.jig run experiments/202608091608_homophily_polarization/homophily_polarization.toml
python -m generic_analyses experiments/202608091608_homophily_polarization --all
python experiments/202608091608_homophily_polarization/analyses/manufacture_vs_sharpen.py
```

`runs.csv` and `steps.csv` are committed with this experiment; PNGs are
regenerable from them and are not.

## 8. Conclusion

Crossing `electorate_shape` into the homophily × social-influence sweep
answers the question `network_sweep` could not ask: homophily does not, on
this evidence, manufacture polarization from a neutral electorate. It
modestly slows the convergence social influence otherwise drives toward, and
it does substantially more of that work when the electorate already has two
camps to protect. The mechanism is real but asymmetric — a brake on merging,
not an engine of sorting.
