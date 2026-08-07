"""The single-run command line interface."""

from __future__ import annotations

import pytest

from polimods.cli import main


def test_runs_and_prints_the_history(capsys):
    assert main(["--steps", "5", "--seed", "1", "--population", "100"]) == 0
    output = capsys.readouterr()

    lines = output.out.strip().splitlines()
    assert lines[0].startswith("election\twinner")
    assert len(lines) == 6  # header + 5 elections
    assert "mean margin" in output.err


def test_exports_a_tsv(tmp_path, capsys):
    path = tmp_path / "history.tsv"
    assert main(["--steps", "4", "--seed", "1", "--export", str(path), "--quiet"]) == 0

    lines = path.read_text().splitlines()
    assert len(lines) == 5
    assert len(lines[0].split("\t")) == 11
    assert "Saved 4 elections" in capsys.readouterr().err


def test_quiet_suppresses_the_table(capsys):
    main(["--steps", "3", "--seed", "1", "--quiet"])
    assert capsys.readouterr().out == ""


def test_boolean_flags_have_negations(capsys):
    """argparse's BooleanOptionalAction gives every switch a --no- form."""
    assert main(["--steps", "2", "--no-adaptive-parties", "--quiet"]) == 0
    assert main(["--steps", "2", "--social-network", "--quiet"]) == 0


def test_production_system_can_be_driven_from_the_command_line(capsys):
    assert main(["--steps", "3", "--production-system", "--no-rule-habit", "--quiet"]) == 0


def test_out_of_range_value_is_a_usage_error():
    with pytest.raises(SystemExit) as excinfo:
        main(["--identity-strength", "5.0"])
    assert excinfo.value.code == 2


def test_invalid_electorate_shape_is_a_usage_error():
    with pytest.raises(SystemExit):
        main(["--electorate-shape", "three-camp"])


def test_same_seed_gives_the_same_output(capsys):
    main(["--steps", "5", "--seed", "42", "--population", "100"])
    first = capsys.readouterr().out
    main(["--steps", "5", "--seed", "42", "--population", "100"])
    assert capsys.readouterr().out == first
