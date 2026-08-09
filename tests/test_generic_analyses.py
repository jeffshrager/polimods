"""The generic figures: what they read, and what they refuse to invent.

A plotting bug is quiet -- a wrong line still looks like a line -- so these tests
pin the reading and averaging, which is where a figure can start describing
something that never happened.  The drawing itself is checked only for producing
a file, since a PNG's contents are not something a test can read for meaning.
"""

from __future__ import annotations

import csv
import json

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

from generic_analyses import MissingSteps, get_theme, load  # noqa: E402
from generic_analyses.__main__ import main as plot_main  # noqa: E402
from generic_analyses.figures import space_by_condition, write_all  # noqa: E402

STEP_COLUMNS = [
    "run_id",
    "election",
    "winner",
    "blue_share",
    "red_share",
    "turnout_rate",
    "margin",
    "blue_position",
    "red_position",
    "party_gap",
    "mean_ideology",
    "switch_rate",
    "ideology_sd",
    "ideology_p10",
    "ideology_p50",
    "ideology_p90",
    "blue_voter_ideology",
    "red_voter_ideology",
    "mean_identity",
]


def make_experiment(directory, conditions=2, runs_per_condition=2, elections=4, cells=None):
    """A folder shaped exactly like one the jig writes."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "experiment": "fake",
                "description": "a fixture",
                "sweep_variables": ["party_adaptation"],
            }
        )
    )

    runs, steps = [], []
    run_id = 0
    for condition in range(conditions):
        for repetition in range(runs_per_condition):
            runs.append(
                {
                    "run_id": run_id,
                    "condition_index": condition,
                    "repetition": repetition,
                    "seed": run_id,
                    "party_adaptation": 0.25 * condition,
                }
            )
            for election in range(1, elections + 1):
                row = {name: 0.0 for name in STEP_COLUMNS}
                row.update(
                    run_id=run_id,
                    election=election,
                    winner="Blue",
                    blue_position=-0.5 + 0.1 * election,
                    red_position=0.5 - 0.1 * election,
                    ideology_p10=-0.4,
                    ideology_p50=0.0,
                    ideology_p90=0.4,
                    # The value under test: run 0 gets 1, run 1 gets 3, mean 2.
                    ideology_sd=1.0 + 2.0 * repetition,
                )
                row.update((cells or {}).get(run_id, {}))
                steps.append(row)
            run_id += 1

    _write(directory / "runs.csv", runs)
    _write(directory / "steps.csv", steps)
    return directory


def _write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


# -- reading an experiment folder ---------------------------------------------


def test_a_folder_without_per_election_output_says_how_to_get_it(tmp_path):
    """The failure a user actually hits, since steps.csv is opt-in and uncommitted."""
    directory = make_experiment(tmp_path / "exp")
    (directory / "steps.csv").unlink()
    (directory / "sweep.toml").write_text('name = "fake"\n')

    with pytest.raises(MissingSteps, match="run_metrics_every_step"):
        load(directory)


def test_runs_are_grouped_by_condition_not_pooled(tmp_path):
    directory = make_experiment(tmp_path / "exp", conditions=3, runs_per_condition=4)
    experiment = load(directory)

    assert [c.index for c in experiment.conditions] == [0, 1, 2]
    assert all(c.runs == 4 for c in experiment.conditions)
    assert experiment.conditions[1].settings == {"party_adaptation": 0.25}
    assert experiment.conditions[1].label == "party_adaptation = 0.25"


def test_each_election_is_averaged_across_the_repetitions(tmp_path):
    directory = make_experiment(tmp_path / "exp", conditions=1, runs_per_condition=2)
    condition = load(directory).conditions[0]

    assert np.allclose(condition["ideology_sd"], 2.0)  # mean of 1 and 3
    assert list(condition.elections) == [1, 2, 3, 4]


def test_a_run_with_no_voters_for_a_party_does_not_drag_the_mean_to_zero(tmp_path):
    """A party that drew no votes records NaN, and NaN must stay out of the mean."""
    directory = make_experiment(
        tmp_path / "exp",
        conditions=1,
        runs_per_condition=2,
        cells={0: {"blue_voter_ideology": float("nan")}, 1: {"blue_voter_ideology": -0.4}},
    )
    condition = load(directory).conditions[0]

    assert np.allclose(condition["blue_voter_ideology"], -0.4)


def test_asking_for_a_column_that_is_not_recorded_names_the_ones_that_are(tmp_path):
    condition = load(make_experiment(tmp_path / "exp")).conditions[0]

    with pytest.raises(KeyError, match="blue_position"):
        condition["mean_wealth"]


# -- drawing ------------------------------------------------------------------


def test_every_figure_writes_a_file(tmp_path):
    experiment = load(make_experiment(tmp_path / "exp"))
    out = tmp_path / "figures"

    written = write_all(experiment, experiment.conditions[0], get_theme("light"), out)

    assert {p.name for p in written} == {
        "political_space.png",
        "competition.png",
        "convergence.png",
    }
    assert all(p.stat().st_size > 0 for p in written)


def test_figures_draw_from_an_older_experiment_without_the_added_columns(tmp_path):
    """steps.csv written before the distribution fields existed still plots."""
    directory = make_experiment(tmp_path / "exp")
    rows = list(csv.DictReader(open(directory / "steps.csv", newline="")))
    for row in rows:
        for column in ("ideology_p10", "ideology_p50", "ideology_p90", "ideology_sd"):
            del row[column]
    _write(directory / "steps.csv", rows)

    experiment = load(directory)
    written = write_all(experiment, experiment.conditions[0], get_theme("dark"), tmp_path / "f")
    assert len(written) == 3


def test_the_facet_figure_covers_every_condition(tmp_path):
    experiment = load(make_experiment(tmp_path / "exp", conditions=4))
    figure = space_by_condition(experiment, get_theme("light"))

    drawn = [ax for ax in figure.axes if ax.get_visible()]
    assert len(drawn) == 4


def test_unknown_theme_is_a_clean_error():
    with pytest.raises(ValueError, match="unknown theme"):
        get_theme("neon")


# -- the command line ---------------------------------------------------------


def test_cli_lists_the_conditions(tmp_path, capsys):
    directory = make_experiment(tmp_path / "exp", conditions=2)

    assert plot_main([str(directory), "--list"]) == 0
    output = capsys.readouterr().out
    assert "2 condition(s)" in output
    assert "party_adaptation = 0.25" in output


def test_cli_writes_into_the_experiment_folder_by_default(tmp_path, capsys):
    directory = make_experiment(tmp_path / "exp", conditions=2)

    assert plot_main([str(directory)]) == 0
    assert (directory / "political_space.png").exists()
    assert (directory / "space_by_condition.png").exists()
    assert "plotting condition 0 of 2" in capsys.readouterr().out


def test_cli_reports_a_missing_steps_file_without_a_traceback(tmp_path, capsys):
    directory = make_experiment(tmp_path / "exp")
    (directory / "steps.csv").unlink()

    assert plot_main([str(directory)]) == 2
    assert "run_metrics_every_step" in capsys.readouterr().err
