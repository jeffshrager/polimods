# generic_analyses

Figures that work on **any** experiment this repository produces. Nothing here
knows what a particular sweep was asking; point it at an experiment folder and it
draws the same four pictures.

```bash
python -m generic_analyses experiments/202608081234_dynamics_demo
python -m generic_analyses <folder> --list              # what conditions are in there
python -m generic_analyses <folder> --condition 5       # one setting
python -m generic_analyses <folder> --all               # every setting
python -m generic_analyses <folder> --theme dark
```

PNGs are written into the experiment folder, next to the spec and manifest that
produced them, so a folder stays the whole record of one experiment. They are
gitignored, like `steps.csv`: both are regenerable from the spec.

## What it draws

| Figure | Question |
|---|---|
| `political_space.png` | Where are the parties, on the electorate they are competing for? |
| `competition.png` | How did the contest go — shares, margin, turnout, switching? |
| `convergence.png` | Did the parties converge, and did the voters? |
| `space_by_condition.png` | The first figure, once per condition, on shared axes |

Lines are means over a condition's repetitions. Runs are never pooled across
conditions: a curve averaged over two parameter settings describes neither.

## It needs per-election output

The dynamics come from `steps.csv`, which the jig writes only when the spec sets

```toml
run_metrics_every_step = true
```

The three original sweeps do not set it — their questions only needed where each
run ended up. `experiments/202608081234_dynamics_demo/` exists to have dynamics
to draw. Pointing this tool at a folder without `steps.csv` tells you exactly
that, and how to get one.

## What was added to the model for these

`ElectionRecord` used to carry the electorate's *mean* ideology, which is nearly
useless here: both electorate shapes are symmetric, so the mean sits near zero
however far the voters have moved. The per-election record now also carries
`ideology_sd`, `ideology_p10/p50/p90`, `blue_voter_ideology`,
`red_voter_ideology` and `mean_identity` — spread, shape, and the centre of each
party's actual coalition. The NetLogo TSV export is untouched and still
byte-compatible.

## Colour

Two hues, because the model has two parties and they are named Blue and Red;
everything else on the chart is ink, because it is context rather than identity.
Both palettes were validated on all pairs against the surface they are drawn on,
in light and dark mode — see the note at the top of `theme.py` for the numbers.
