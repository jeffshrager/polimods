"""The experimental jig: spec expansion, seeding, output layout, and the manifest.

The expensive failure mode for a sweep runner is not crashing -- it is quietly
producing a plausible CSV that does not mean what the reader thinks it means.
So these tests concentrate on the guarantees that make results interpretable:
validation happens before execution, seeds are reproducible, an old folder is
never overwritten, and the manifest describes every variable rather than only the
swept ones.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path

import pytest

from polimods.jig import (
    ExperimentSpec,
    SpecError,
    dated_name,
    derive_seed,
    execute_run,
    read_manifest,
    resolve_output_dir,
    run_experiment,
    summarize,
)
from polimods.jig.cli import main as jig_main
from polimods.params import Params

REPO = Path(__file__).resolve().parents[1]
EXPERIMENTS = REPO / "experiments"


def shipped(name: str) -> Path:
    """The path of a shipped spec inside its stamped experiment folder.

    Globbed rather than hard-coded: re-running one of these creates a folder
    with a later stamp, and the newest is the one to read.
    """
    matches = sorted(EXPERIMENTS.glob(f"*_{name}/{name}.toml"))
    assert matches, f"no experiment folder holding {name}.toml"
    return matches[-1]


#: A pinned clock.  Folder names carry the minute, so a test that reconstructs
#: one after the run would fail whenever the run straddles a minute boundary.
NOW = datetime(2026, 8, 9, 18, 21)


def stamped(root: Path, name: str = "tiny", suffix: str = "", when=NOW) -> Path:
    """The folder a spec named ``name`` gets under ``root`` at ``when``."""
    return Path(root) / (dated_name(name, when) + suffix)


def written(root: Path, name: str = "tiny", suffix: str = "") -> Path:
    """The stamped folder a completed run actually wrote under ``root``."""
    pattern = re.compile(rf"\d{{12}}_{re.escape(name + suffix)}$")
    matches = [p for p in Path(root).iterdir() if p.is_dir() and pattern.match(p.name)]
    assert len(matches) == 1, f"expected one {name}{suffix} folder, found {matches}"
    return matches[0]


def tiny_spec(**overrides) -> ExperimentSpec:
    raw = {
        "name": "tiny",
        "repetitions": 2,
        "steps": 3,
        "metrics": ["mean_margin", "party_gap"],
        "constants": {"population": 100},
        "sweep": {"party_adaptation": [0.0, 0.5]},
    }
    raw.update(overrides)
    return ExperimentSpec.from_dict(raw)


# -- spec expansion -----------------------------------------------------------


def test_enumerated_sweep_expands_to_its_values():
    spec = tiny_spec()
    assert spec.sweeps[0].values == (0.0, 0.5)
    assert spec.condition_count == 2
    assert spec.total_runs == 4


def test_stepped_sweep_includes_the_last_value():
    """NetLogo's steppedValueSet is inclusive when 'last' lands on the grid."""
    spec = tiny_spec(sweep={"party_adaptation": {"first": 0.0, "step": 0.1, "last": 0.5}})
    assert spec.sweeps[0].values == (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)


def test_stepped_sweep_does_not_overshoot():
    spec = tiny_spec(sweep={"base_pressure": {"first": 0.0, "step": 0.3, "last": 1.0}})
    assert spec.sweeps[0].values == (0.0, 0.3, 0.6, 0.9)


def test_cartesian_product_covers_every_combination():
    spec = tiny_spec(
        sweep={"party_adaptation": [0.0, 0.5], "base_pressure": [0.0, 0.5, 1.0]}
    )
    conditions = spec.conditions()
    assert len(conditions) == 6
    assert spec.total_runs == 12
    assert {(c["party_adaptation"], c["base_pressure"]) for c in conditions} == {
        (a, b) for a in (0.0, 0.5) for b in (0.0, 0.5, 1.0)
    }


def test_boolean_sweeps_are_supported():
    spec = tiny_spec(sweep={"adaptive_parties": [True, False]})
    assert spec.sweeps[0].values == (True, False)


# -- validation before execution ----------------------------------------------


def test_out_of_range_sweep_value_is_rejected_up_front():
    """The whole experiment must fail before the first run, not part-way through."""
    with pytest.raises(SpecError, match="identity_strength"):
        tiny_spec(sweep={"identity_strength": [0.5, 2.5]})


def test_unknown_parameter_is_rejected():
    with pytest.raises(SpecError, match="unknown parameter"):
        tiny_spec(sweep={"partisanship": [1, 2]})


def test_unknown_constant_is_rejected():
    with pytest.raises(SpecError, match="unknown parameter"):
        tiny_spec(constants={"voter_count": 500})


def test_unknown_metric_is_rejected():
    with pytest.raises(SpecError, match="unknown metric"):
        tiny_spec(metrics=["mean_margin", "vibes"])


def test_a_variable_cannot_be_both_constant_and_swept():
    with pytest.raises(SpecError, match="both"):
        tiny_spec(
            constants={"party_adaptation": 0.25}, sweep={"party_adaptation": [0.0, 0.5]}
        )


def test_unknown_top_level_key_is_rejected():
    with pytest.raises(SpecError, match="unknown top-level key"):
        ExperimentSpec.from_dict({"name": "x", "reps": 3, "sweep": {"homophily": [0.0]}})


def test_a_spec_without_a_sweep_is_rejected():
    with pytest.raises(SpecError, match="no \\[sweep\\]"):
        ExperimentSpec.from_dict({"name": "x", "constants": {"population": 100}})


def test_missing_spec_file_is_a_clean_error():
    with pytest.raises(SpecError, match="no such experiment spec"):
        ExperimentSpec.from_file("experiments/does_not_exist.toml")


# -- seeding ------------------------------------------------------------------


def test_seeds_are_deterministic_and_distinct():
    assert derive_seed(7, 0, 0) == derive_seed(7, 0, 0)
    assert derive_seed(7, 0, 0) != derive_seed(7, 0, 1)
    assert derive_seed(7, 0, 0) != derive_seed(7, 1, 0)
    assert derive_seed(7, 0, 0) != derive_seed(8, 0, 0)


def test_seeds_do_not_shift_when_conditions_are_added():
    """A seed depends on (base, condition, repetition), not on position in the list.

    So extending a sweep leaves the existing conditions bit-identical, and a
    re-run is a genuine replication rather than a fresh sample.
    """
    small = tiny_spec()
    larger = tiny_spec(sweep={"party_adaptation": [0.0, 0.5, 0.75]})
    assert [r.seed for r in small.runs()] == [r.seed for r in larger.runs()][:4]


def test_a_single_run_is_reproducible_from_its_seed_alone():
    spec = tiny_spec()
    run = spec.runs()[2]
    first, _ = execute_run(run, spec.steps, spec.metrics, False)
    second, _ = execute_run(run, spec.steps, spec.metrics, False)
    assert first == second


# -- output layout ------------------------------------------------------------


def test_results_go_in_a_folder_stamped_and_named_for_the_experiment(tmp_path):
    spec = tiny_spec()
    directory, renamed = resolve_output_dir(spec, root=tmp_path, now=NOW)
    assert directory == tmp_path / "202608091821_tiny"
    assert renamed is None


def test_a_spec_inside_a_stamped_folder_is_run_in_place(tmp_path):
    """The whole point of the layout: spec and output in the same folder."""
    directory = tmp_path / "202608091821_network_scan"
    directory.mkdir()
    spec_path = directory / "network_scan.toml"
    spec_path.write_text(
        'name = "network_scan"\nmetrics = ["mean_margin"]\n'
        "[sweep]\nhomophily = [0.0, 0.5]\n"
    )
    spec = ExperimentSpec.from_file(spec_path)

    resolved, renamed = resolve_output_dir(spec)
    assert resolved == directory
    assert renamed is None


def test_a_loose_spec_gets_a_stamped_folder_and_is_copied_into_it(tmp_path):
    spec_path = tmp_path / "tiny.toml"
    spec_path.write_text(
        'name = "tiny"\nrepetitions = 1\nsteps = 2\nmetrics = ["mean_margin"]\n'
        "[constants]\npopulation = 100\n[sweep]\nparty_adaptation = [0.0, 0.5]\n"
    )
    run_experiment(ExperimentSpec.from_file(spec_path), jobs=1, progress=False)

    directory = written(tmp_path)
    assert (directory / "tiny.toml").read_text() == spec_path.read_text()
    assert (directory / "runs.csv").exists()
    assert read_manifest(directory)["spec_file"].endswith("tiny.toml")


def test_rerunning_an_experiment_never_clobbers_finished_results(tmp_path):
    spec = tiny_spec()
    done = stamped(tmp_path)
    done.mkdir(parents=True)
    (done / "runs.csv").write_text("run_id\n")

    directory, renamed = resolve_output_dir(spec, root=tmp_path, now=NOW)
    assert directory == stamped(tmp_path, suffix="_2")
    assert renamed == str(done)

    stamped(tmp_path, suffix="_2").mkdir()
    directory, _ = resolve_output_dir(spec, root=tmp_path, now=NOW)
    assert directory == stamped(tmp_path, suffix="_3")


def test_rerunning_a_finished_experiment_gets_a_new_stamp_not_a_suffix(tmp_path):
    """Several experiments a day is the normal case, so the minute is the key: a
    re-run of this morning's sweep is this afternoon's folder, not `_2`."""
    morning = tmp_path / "202608090930_tiny"
    morning.mkdir(parents=True)
    spec_path = morning / "tiny.toml"
    spec_path.write_text(
        'name = "tiny"\nmetrics = ["mean_margin"]\n[sweep]\nhomophily = [0.0, 0.5]\n'
    )
    (morning / "runs.csv").write_text("run_id\n")
    spec = ExperimentSpec.from_file(spec_path)

    directory, renamed = resolve_output_dir(spec, now=NOW)
    assert directory == tmp_path / "202608091821_tiny"
    assert renamed == str(morning)


def test_an_empty_folder_is_not_treated_as_a_previous_run(tmp_path):
    """A folder the user made to hold the spec has nothing to lose."""
    spec = tiny_spec()
    stamped(tmp_path).mkdir(parents=True)

    directory, renamed = resolve_output_dir(spec, root=tmp_path, now=NOW)
    assert directory == stamped(tmp_path)
    assert renamed is None


def test_resume_reuses_the_existing_folder(tmp_path):
    spec = tiny_spec()
    existing = stamped(tmp_path)
    existing.mkdir(parents=True)
    (existing / "runs.csv").write_text("run_id\n")

    directory, renamed = resolve_output_dir(spec, root=tmp_path, resume=True, now=NOW)
    assert directory == existing
    assert renamed is None


def test_resume_finds_a_folder_stamped_earlier(tmp_path):
    """A sweep interrupted this morning is continued, not restarted alongside."""
    spec = tiny_spec()
    earlier = tmp_path / "202608090930_tiny"
    earlier.mkdir(parents=True)
    (earlier / "runs.csv").write_text("run_id\n")

    directory, renamed = resolve_output_dir(spec, root=tmp_path, resume=True, now=NOW)
    assert directory == earlier
    assert renamed is None


def test_run_writes_runs_csv_and_manifest(tmp_path):
    spec = tiny_spec()
    run_experiment(spec, jobs=1, root=tmp_path, progress=False)
    directory = written(tmp_path)

    with open(directory / "runs.csv", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 4
    assert set(rows[0]) == {
        "run_id",
        "condition_index",
        "repetition",
        "seed",
        "party_adaptation",
        "mean_margin",
        "party_gap",
    }
    assert (directory / "manifest.json").exists()
    assert not (directory / "steps.csv").exists()


def test_per_election_output_is_written_when_requested(tmp_path):
    spec = tiny_spec(run_metrics_every_step=True)
    run_experiment(spec, jobs=1, root=tmp_path, progress=False)

    with open(written(tmp_path) / "steps.csv", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 4 * 3  # 4 runs x 3 elections
    assert rows[0]["election"] == "1"
    assert "blue_share" in rows[0]


# -- the manifest -------------------------------------------------------------


def test_manifest_describes_every_variable_not_just_the_swept_ones(tmp_path):
    run_experiment(tiny_spec(), jobs=1, root=tmp_path, progress=False)
    manifest = read_manifest(written(tmp_path))

    variables = manifest["variables"]
    assert set(variables) == set(Params.field_names())

    swept = variables["party_adaptation"]
    assert swept["role"] == "swept"
    assert swept["values"] == [0.0, 0.5]
    assert swept["n"] == 2
    assert swept["sweep"] == {"enumerated": [0.0, 0.5]}
    assert swept["bounds"] == [0.0, 1.0]
    assert swept["netlogo_default"] == 0.25

    pinned = variables["population"]
    assert pinned["role"] == "constant"
    assert pinned["value"] == 100
    assert pinned["netlogo_default"] == 500

    untouched = variables["identity_strength"]
    assert untouched["role"] == "default"
    assert untouched["value"] == 0.6


def test_manifest_records_stepped_sweep_ranges(tmp_path):
    spec = tiny_spec(sweep={"party_adaptation": {"first": 0.0, "step": 0.1, "last": 0.3}})
    run_experiment(spec, jobs=1, root=tmp_path, progress=False)
    manifest = read_manifest(written(tmp_path))

    assert manifest["variables"]["party_adaptation"]["sweep"] == {
        "first": 0.0,
        "step": 0.1,
        "last": 0.3,
    }


def test_manifest_records_provenance_and_completion(tmp_path):
    run_experiment(tiny_spec(), jobs=1, root=tmp_path, progress=False)
    manifest = read_manifest(written(tmp_path))

    assert manifest["status"] == "complete"
    assert manifest["runs_completed"] == manifest["total_runs"] == 4
    assert manifest["conditions"] == 2
    assert manifest["base_seed"] == 20260807
    assert manifest["wall_seconds"] is not None
    assert manifest["environment"]["numpy"]
    assert manifest["metrics"] == ["mean_margin", "party_gap"]
    assert manifest["sweep_variables"] == ["party_adaptation"]


def test_manifest_notes_the_folder_it_collided_with(tmp_path):
    """Two runs in the same minute: the second says which folder it stepped around."""
    run_experiment(tiny_spec(), jobs=1, root=tmp_path, progress=False, now=NOW)
    run_experiment(tiny_spec(), jobs=1, root=tmp_path, progress=False, now=NOW)

    second = read_manifest(stamped(tmp_path, suffix="_2"))
    assert second["renamed_from"] == str(stamped(tmp_path))


def test_manifest_is_valid_json_on_disk(tmp_path):
    run_experiment(tiny_spec(), jobs=1, root=tmp_path, progress=False)
    text = (written(tmp_path) / "manifest.json").read_text()
    assert json.loads(text)["experiment"] == "tiny"


# -- resume -------------------------------------------------------------------


def test_resume_skips_runs_already_recorded(tmp_path):
    spec = tiny_spec()
    run_experiment(spec, jobs=1, root=tmp_path, progress=False)
    run_experiment(spec, jobs=1, root=tmp_path, resume=True, progress=False)

    with open(written(tmp_path) / "runs.csv", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 4  # not 8
    assert len({row["run_id"] for row in rows}) == 4


def test_resume_completes_a_truncated_sweep(tmp_path):
    spec = tiny_spec()
    run_experiment(spec, jobs=1, root=tmp_path, progress=False)
    runs_path = written(tmp_path) / "runs.csv"

    lines = runs_path.read_text().splitlines()
    runs_path.write_text("\n".join(lines[:3]) + "\n")  # header + 2 runs

    run_experiment(spec, jobs=1, root=tmp_path, resume=True, progress=False)

    with open(runs_path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert sorted(int(row["run_id"]) for row in rows) == [0, 1, 2, 3]


# -- reproducibility across whole sweeps --------------------------------------


def test_the_same_spec_produces_the_same_csv(tmp_path):
    run_experiment(tiny_spec(), jobs=1, root=tmp_path / "a", progress=False)
    run_experiment(tiny_spec(), jobs=1, root=tmp_path / "b", progress=False)

    assert (written(tmp_path / "a") / "runs.csv").read_text() == (
        written(tmp_path / "b") / "runs.csv"
    ).read_text()


def test_parallel_and_serial_execution_agree(tmp_path):
    """Results must not depend on how many processes ran them."""
    run_experiment(tiny_spec(), jobs=1, root=tmp_path / "serial", progress=False)
    run_experiment(tiny_spec(), jobs=2, root=tmp_path / "parallel", progress=False)

    assert (written(tmp_path / "serial") / "runs.csv").read_text() == (
        written(tmp_path / "parallel") / "runs.csv"
    ).read_text()


def test_a_different_base_seed_changes_the_results(tmp_path):
    run_experiment(tiny_spec(), jobs=1, root=tmp_path / "a", progress=False)
    run_experiment(
        tiny_spec(base_seed=1), jobs=1, root=tmp_path / "b", progress=False
    )

    assert (written(tmp_path / "a") / "runs.csv").read_text() != (
        written(tmp_path / "b") / "runs.csv"
    ).read_text()


# -- summarizing --------------------------------------------------------------


def test_summarize_groups_by_the_swept_variables(tmp_path):
    spec = tiny_spec(repetitions=4)
    run_experiment(spec, jobs=1, root=tmp_path, progress=False)

    summary = summarize(written(tmp_path))

    assert summary.by == ("party_adaptation",)
    assert summary.conditions == [(0.0,), (0.5,)]
    assert summary.total_runs == 8
    assert summary.value((0.0,), "party_gap").n == 4
    assert summary.value((0.0,), "party_gap").sd >= 0.0


def test_summarize_accepts_an_explicit_grouping(tmp_path):
    run_experiment(tiny_spec(), jobs=1, root=tmp_path, progress=False)
    summary = summarize(written(tmp_path), by=["condition_index"])
    assert summary.by == ("condition_index",)


def test_summarize_rejects_an_unknown_column(tmp_path):
    run_experiment(tiny_spec(), jobs=1, root=tmp_path, progress=False)
    with pytest.raises(ValueError, match="not in runs.csv"):
        summarize(written(tmp_path), by=["nonsense"])


# -- the shipped experiment specs ---------------------------------------------


@pytest.mark.parametrize(
    "name,conditions,runs",
    [
        ("parity_sweep", 30, 300),
        ("network_sweep", 25, 250),
        ("rule_ablation", 256, 2560),
    ],
)
def test_shipped_specs_parse_and_expand(name, conditions, runs):
    spec = ExperimentSpec.from_file(shipped(name))
    assert spec.condition_count == conditions
    assert spec.total_runs == runs
    assert spec.steps == 100


def test_parity_sweep_matches_the_behaviorspace_experiment():
    """Same grid as 'Parity sweep - adaptation x base pressure' in the .nlogo."""
    spec = ExperimentSpec.from_file(shipped("parity_sweep"))
    values = {sweep.name: sweep.values for sweep in spec.sweeps}

    assert values["party_adaptation"] == (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)
    assert values["base_pressure"] == (0.0, 0.25, 0.5, 0.75, 1.0)
    assert spec.repetitions == 10
    assert spec.constants["social_network"] is False
    assert spec.constants["population"] == 500


def test_network_sweep_matches_the_behaviorspace_experiment():
    spec = ExperimentSpec.from_file(shipped("network_sweep"))
    values = {sweep.name: sweep.values for sweep in spec.sweeps}

    assert values["homophily"] == (0.0, 0.25, 0.5, 0.75, 1.0)
    assert values["social_influence"] == (0.0, 0.05, 0.1, 0.2, 0.4)
    assert spec.constants["electorate_shape"] == "two-camp"
    assert spec.constants["social_network"] is True


def test_rule_ablation_crosses_all_eight_rules():
    spec = ExperimentSpec.from_file(shipped("rule_ablation"))
    assert len(spec.sweeps) == 8
    assert all(sweep.values == (True, False) for sweep in spec.sweeps)
    assert spec.constants["production_system"] is True
    assert spec.constants["social_network"] is True  # else rule_neighbors is inert


# -- the command line ---------------------------------------------------------


def test_dry_run_reports_the_grid_without_writing_anything(tmp_path, capsys):
    code = jig_main(
        [
            "run",
            str(shipped("parity_sweep")),
            "--dry-run",
            "--root",
            str(tmp_path),
        ]
    )
    output = capsys.readouterr().out

    assert code == 0
    assert "total runs      300" in output
    assert "party_adaptation" in output
    assert not any(tmp_path.iterdir())


def test_cli_reports_a_bad_spec_without_a_traceback(tmp_path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text('name = "bad"\n[sweep]\nidentity_strength = [9.0]\n')

    code = jig_main(["run", str(bad), "--root", str(tmp_path)])

    assert code == 2
    assert "identity_strength" in capsys.readouterr().err


def test_cli_summarize_prints_a_table(tmp_path, capsys):
    run_experiment(tiny_spec(), jobs=1, root=tmp_path, progress=False)
    code = jig_main(["summarize", str(written(tmp_path))])
    output = capsys.readouterr().out

    assert code == 0
    assert "party_adaptation" in output
    assert "mean_margin" in output
