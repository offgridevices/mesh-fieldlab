from __future__ import annotations

import json

import pytest

from conftest import RX_NODE, make_file, row
from fieldlab import schema as S
from fieldlab.cli import EXIT_OK, EXIT_PROBLEMS, EXIT_USAGE, main, synth_main


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return path


def test_a_good_file_exits_zero(tmp_path, good_file, capsys):
    path = write(tmp_path, "LOG_N1_7.csv", good_file)
    assert main([str(path)]) == EXIT_OK
    assert "OK" in capsys.readouterr().out


def test_a_bad_file_exits_nonzero(tmp_path, capsys):
    # A node cannot receive its own transmission over the air, so this really
    # is a broken row rather than a polluted one.
    text = make_file(row(S.ROW_BOOT), row(S.ROW_PKT, tx_node=RX_NODE))
    path = write(tmp_path, "LOG_N1_7.csv", text)
    assert main([str(path)]) == EXIT_PROBLEMS
    assert "SELF_RECEPTION" in capsys.readouterr().out


def test_strict_turns_warnings_into_failure(tmp_path, good_file):
    path = write(tmp_path, "LOG_N1_7.csv", good_file)
    assert main([str(path)]) == EXIT_OK
    assert main([str(path), "--strict", "--min-packets", "100"]) == EXIT_PROBLEMS


def test_a_directory_checks_every_file_in_it(tmp_path, good_file, capsys):
    write(tmp_path, "LOG_N1_1.csv", good_file)
    write(tmp_path, "LOG_N2_1.csv", good_file)
    assert main([str(tmp_path)]) == EXIT_OK
    assert "2/2 files usable" in capsys.readouterr().out


def test_json_output_is_machine_readable(tmp_path, good_file, capsys):
    path = write(tmp_path, "LOG_N1_7.csv", good_file)
    main([str(path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["ok"] is True
    assert payload[0]["boot_count"] == "7"
    assert payload[0]["row_types"]["PKT"] == 2


def test_schema_flag_prints_the_header_the_firmware_must_write(capsys):
    assert main(["--schema", "unused"]) == EXIT_OK
    assert capsys.readouterr().out.strip() == S.HEADER


def test_a_path_with_no_csv_files_is_a_usage_error(tmp_path, capsys):
    assert main([str(tmp_path)]) == EXIT_USAGE


def test_one_dead_card_does_not_hide_the_verdict_on_the_others(tmp_path, good_file, capsys):
    write(tmp_path, "LOG_N1_1.csv", good_file)
    write(tmp_path, "LOG_N2_1.csv", good_file)
    (tmp_path / "LOG_N3_1.csv").mkdir()  # unreadable where a file was expected

    assert main([str(tmp_path)]) == EXIT_PROBLEMS
    out = capsys.readouterr().out
    assert "UNREADABLE" in out
    assert "2/3 files usable" in out


def test_a_missing_file_is_reported_rather_than_crashing(tmp_path, capsys):
    assert main([str(tmp_path / "nope.csv")]) == EXIT_PROBLEMS
    assert "UNREADABLE" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [
        ["--nodes", "1"],
        ["--interval", "0"],
        ["--interval", "-5"],
        ["--minutes", "0"],
        ["--minutes", "1", "--interval", "600"],
    ],
)
def test_nonsense_generator_settings_are_refused(tmp_path, argv, capsys):
    assert synth_main([str(tmp_path), *argv]) == EXIT_USAGE
    assert not list(tmp_path.glob("*.csv"))


def test_quiet_hides_warnings(tmp_path, good_file, capsys):
    path = write(tmp_path, "unnamed.csv", good_file)
    main([str(path), "--quiet"])
    out = capsys.readouterr().out
    assert "FILENAME" not in out
    assert "warnings hidden" in out
