from __future__ import annotations

import pytest

from conftest import RX_NODE, TX_NODE, make_file, row
from fieldlab import schema as S
from fieldlab.validate import validate_file, validate_text


def codes(result) -> set[str]:
    return {i.code for i in result.issues}


def error_codes(result) -> set[str]:
    return {i.code for i in result.errors}


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_a_well_formed_file_passes_cleanly(good_file):
    result = validate_text(good_file, "LOG_N1_7.csv")
    assert result.ok
    assert result.issues == []
    assert result.summary.rx_node == RX_NODE
    assert result.summary.boot_count == "7"
    assert result.summary.firmware == "2.5.4"
    assert result.summary.by_row_type[S.ROW_PKT] == 2


def test_direct_packets_are_counted_per_ordered_link(good_file):
    result = validate_text(good_file, "LOG_N1_7.csv")
    assert result.summary.direct_links == {(TX_NODE, RX_NODE): 2}
    assert result.summary.relayed_links == {}


def test_relayed_packets_are_kept_separate_from_direct_ones():
    text = make_file(
        row(S.ROW_BOOT),
        row(S.ROW_PKT, pkt_id=1, hop_start=3, hop_limit=3, hops_used=0),
        row(S.ROW_PKT, pkt_id=2, hop_start=3, hop_limit=1, hops_used=2),
    )
    result = validate_text(text)
    assert result.ok
    assert result.summary.direct_links == {(TX_NODE, RX_NODE): 1}
    assert result.summary.relayed_links == {(TX_NODE, RX_NODE): 1}


def test_flood_copies_of_one_packet_are_counted_once():
    same = dict(pkt_id=42, hop_start=3, hop_limit=3, hops_used=0)
    text = make_file(
        row(S.ROW_BOOT),
        row(S.ROW_PKT, **same),
        row(S.ROW_PKT, **same),
        row(S.ROW_PKT, **same),
    )
    result = validate_text(text)
    assert result.summary.direct_links == {(TX_NODE, RX_NODE): 1}
    assert result.summary.duplicate_rows == 2


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


def test_a_wrong_header_stops_everything():
    text = make_file(row(S.ROW_BOOT), header="time,rssi,snr")
    result = validate_text(text)
    assert error_codes(result) == {"HEADER"}


def test_reordered_columns_are_rejected():
    reordered = list(S.COLUMN_NAMES)
    reordered[1], reordered[2] = reordered[2], reordered[1]
    result = validate_text(make_file(row(S.ROW_BOOT), header=",".join(reordered)))
    assert "HEADER" in error_codes(result)


def test_a_file_with_only_a_header_is_an_error():
    result = validate_text(S.HEADER + "\n")
    assert "NO_ROWS" in error_codes(result)


def test_a_power_cut_mid_write_leaves_the_rest_of_the_file_usable():
    text = make_file(row(S.ROW_BOOT), row(S.ROW_PKT), trailing_newline=False)
    text += "\n3,9000,0,111"  # the node died partway through a row
    result = validate_text(text)
    assert result.ok
    assert "TRUNCATED" in codes(result)


def test_a_short_row_in_the_middle_of_a_file_is_an_error():
    text = make_file(row(S.ROW_BOOT), "3,9000,0,111", row(S.ROW_PKT))
    assert "COLUMN_COUNT" in error_codes(validate_text(text))


def test_a_replacement_character_that_was_really_in_the_file_is_not_a_fault(tmp_path, good_file):
    # U+FFFD decodes cleanly from valid UTF-8. Only bytes that are not text
    # at all mean a damaged card.
    path = tmp_path / "LOG_N1_7.csv"
    path.write_text(good_file.replace("rak-stock-3dbi", "rak-stock-3dbi�"), encoding="utf-8")
    result = validate_file(path)
    assert "NOT_TEXT" not in error_codes(result)


def test_bytes_that_are_not_text_at_all_are_reported(tmp_path, good_file):
    path = tmp_path / "LOG_N1_7.csv"
    path.write_bytes(good_file.encode() + b"\xff\xfe garbage\n")
    assert "NOT_TEXT" in error_codes(validate_file(path))


def test_an_unreadable_file_fails_without_raising(tmp_path):
    result = validate_file(tmp_path / "does-not-exist.csv")
    assert not result.ok
    assert "UNREADABLE" in error_codes(result)


def test_nul_bytes_mean_a_damaged_card():
    text = make_file(row(S.ROW_BOOT), row(S.ROW_PKT)).replace("BOOT", "BO\x00T")
    assert "CORRUPT_NUL" in error_codes(validate_text(text))


def test_missing_boot_row_is_an_error():
    assert "NO_BOOT" in error_codes(validate_text(make_file(row(S.ROW_PKT))))


def test_two_boot_rows_mean_two_runs_in_one_file():
    text = make_file(row(S.ROW_BOOT), row(S.ROW_BOOT, uptime_ms=200))
    assert "MULTIPLE_BOOT" in error_codes(validate_text(text))


def test_an_unfamiliar_filename_is_worth_flagging_but_not_fatal(good_file):
    result = validate_text(good_file, "whatever.csv")
    assert result.ok
    assert "FILENAME" in codes(result)


# ---------------------------------------------------------------------------
# Values that contradict themselves
# ---------------------------------------------------------------------------


def test_hop_arithmetic_must_agree():
    text = make_file(row(S.ROW_BOOT), row(S.ROW_PKT, hop_start=3, hop_limit=1, hops_used=0))
    assert "HOPS" in error_codes(validate_text(text))


def test_a_packet_cannot_gain_hops():
    text = make_file(row(S.ROW_BOOT), row(S.ROW_PKT, hop_start=1, hop_limit=3, hops_used=0))
    assert "HOPS" in error_codes(validate_text(text))


def test_a_node_cannot_receive_its_own_transmission():
    text = make_file(row(S.ROW_BOOT), row(S.ROW_PKT, tx_node=RX_NODE))
    assert "SELF_RECEPTION" in error_codes(validate_text(text))


def test_packets_arriving_over_the_internet_invalidate_the_measurement():
    text = make_file(row(S.ROW_BOOT), row(S.ROW_PKT, via_mqtt=1))
    assert "VIA_MQTT" in error_codes(validate_text(text))


def test_zero_rssi_marks_a_locally_originated_row():
    result = validate_text(make_file(row(S.ROW_BOOT), row(S.ROW_PKT, rx_rssi_dbm=0)))
    assert result.ok
    assert "RSSI_ZERO" in codes(result)


@pytest.mark.parametrize("value", ["1", "-200", "abc", ""])
def test_impossible_rssi_values_are_rejected(value):
    text = make_file(row(S.ROW_BOOT), row(S.ROW_PKT, rx_rssi_dbm=value))
    assert error_codes(validate_text(text)) & {"RANGE", "NOT_A_NUMBER"}


@pytest.mark.parametrize("value", ["-40.0", "99.9"])
def test_impossible_snr_values_are_rejected(value):
    text = make_file(row(S.ROW_BOOT), row(S.ROW_PKT, rx_snr_db=value))
    assert "RANGE" in error_codes(validate_text(text))


@pytest.mark.parametrize("value", ["nan", "NaN", "inf", "-inf", "Infinity"])
def test_non_finite_signal_values_are_rejected(value):
    # These parse as floats and compare false against every bound, so without
    # an explicit check they would pass validation and poison a median.
    text = make_file(row(S.ROW_BOOT), row(S.ROW_PKT, rx_snr_db=value))
    assert "NOT_A_NUMBER" in error_codes(validate_text(text))


def test_one_file_belongs_to_one_node():
    text = make_file(row(S.ROW_BOOT), row(S.ROW_PKT, rx_node=999999))
    assert "RX_NODE_CHANGED" in error_codes(validate_text(text))


def test_time_cannot_run_backwards_within_a_file():
    text = make_file(row(S.ROW_BOOT, uptime_ms=5000), row(S.ROW_PKT, uptime_ms=1000))
    assert "UPTIME_WENT_BACKWARDS" in error_codes(validate_text(text))


def test_an_unknown_schema_version_is_refused_rather_than_guessed_at():
    text = make_file(row(S.ROW_BOOT, schema_ver=99), row(S.ROW_PKT, schema_ver=99))
    result = validate_text(text)
    assert "SCHEMA_VERSION" in error_codes(result)


def test_a_device_clock_before_2020_is_wrong_not_merely_unset():
    text = make_file(row(S.ROW_BOOT), row(S.ROW_PKT, dev_rx_time=12345))
    assert "CLOCK" in error_codes(validate_text(text))


def test_a_run_without_absolute_time_is_flagged():
    # dev_rx_time defaults to 0 in the row helper: a node whose clock was
    # never set can still be analysed, but only relative to its own boot.
    result = validate_text(make_file(row(S.ROW_BOOT), row(S.ROW_PKT)))
    assert result.ok
    assert "NO_ABSOLUTE_TIME" in codes(result)


# ---------------------------------------------------------------------------
# Non-packet rows
# ---------------------------------------------------------------------------


def test_a_boot_row_missing_its_detail_is_an_error():
    text = make_file(row(S.ROW_BOOT, extra=S.format_extra({"fw": "2.5.4"})), row(S.ROW_PKT))
    result = validate_text(text)
    assert "EXTRA_MISSING" in error_codes(result)


def test_a_node_deployed_without_its_coordinate_is_caught():
    extra = S.format_extra(
        {"fw": "2.5.4", "preset": "LONG_FAST", "boot": "1", "lat": "0", "lon": "0",
         "alt": "0", "ant": "stock"}
    )
    text = make_file(row(S.ROW_BOOT, extra=extra), row(S.ROW_PKT))
    assert "BOOT_POSITION" in error_codes(validate_text(text))


def _boot_with(**extra) -> str:
    pairs = {
        "fw": "2.5.4", "preset": "LONG_FAST", "boot": "1",
        "lat": "39.8283", "lon": "-98.5795", "alt": "0", "ant": "stock",
    }
    pairs.update({k: str(v) for k, v in extra.items()})
    return row(S.ROW_BOOT, extra=S.format_extra(pairs))


@pytest.mark.parametrize("key", ["st_card", "st_write", "st_radio", "st_pos"])
def test_a_failed_startup_check_is_reported_from_the_file(key):
    # The screen said so at the time; weeks later the file has to say it too.
    text = make_file(_boot_with(**{key: 0}), row(S.ROW_PKT))
    assert "SELFTEST" in error_codes(validate_text(text))


def test_a_clock_that_was_never_set_is_a_warning_not_a_failure():
    result = validate_text(make_file(_boot_with(st_clock=0), row(S.ROW_PKT)))
    assert result.ok
    assert "SELFTEST" in codes(result)


def test_hearing_nothing_at_startup_is_flagged():
    result = validate_text(make_file(_boot_with(st_heard=0), row(S.ROW_PKT)))
    assert result.ok
    assert "SELFTEST" in codes(result)


def test_passing_startup_checks_say_nothing():
    text = make_file(
        _boot_with(st_card=1, st_write=1, st_radio=1, st_pos=1, st_clock=1, st_heard=3),
        row(S.ROW_PKT, dev_rx_time=1786000000),
    )
    assert "SELFTEST" not in codes(validate_text(text))


def test_files_written_before_the_startup_check_existed_still_read():
    result = validate_text(make_file(_boot_with(), row(S.ROW_PKT)))
    assert result.ok
    assert "EXTRA_MISSING" not in error_codes(result)


def test_a_reported_card_failure_is_an_error():
    extra = S.format_extra({"rows": "10", "sd_ok": "0", "heap": "1000"})
    text = make_file(row(S.ROW_BOOT), row(S.ROW_STATUS, uptime_ms=60000, extra=extra))
    assert "SD_FAILED" in error_codes(validate_text(text))


def test_a_long_silence_between_heartbeats_means_a_hole_in_the_run():
    text = make_file(
        row(S.ROW_BOOT),
        row(S.ROW_STATUS, uptime_ms=60000),
        row(S.ROW_STATUS, uptime_ms=400000),
    )
    assert "STATUS_GAP" in codes(validate_text(text))


def test_a_node_row_must_say_which_node_it_describes():
    text = make_file(row(S.ROW_BOOT), row(S.ROW_NODE, tx_node=0))
    assert "NODE_SUBJECT" in error_codes(validate_text(text))


def test_packet_columns_must_be_blank_outside_packet_rows():
    text = make_file(row(S.ROW_BOOT), row(S.ROW_STATUS, uptime_ms=60000, rx_snr_db="4.0"))
    result = validate_text(text)
    assert result.ok
    assert "NONZERO_PACKET_FIELD" in codes(result)


def test_a_separator_inside_a_value_is_caught_rather_than_read_as_truncated():
    # What firmware writing an unescaped separator would produce.
    text = make_file(
        row(S.ROW_BOOT),
        row(S.ROW_STATUS, uptime_ms=60000, extra="heap=1;2;rows=10;sd_ok=1"),
    )
    assert "EXTRA_MALFORMED" in error_codes(validate_text(text))


def test_the_writer_refuses_to_emit_a_separator_in_the_first_place():
    for bad in ({"heap": "1;2"}, {"note": "a,b"}, {"k=v": "1"}):
        with pytest.raises(ValueError):
            S.format_extra(bad)


# ---------------------------------------------------------------------------
# Run quality
# ---------------------------------------------------------------------------


def test_a_link_with_too_few_packets_for_a_median_is_flagged(good_file):
    result = validate_text(good_file, min_packets=100)
    assert result.ok
    assert "THIN_LINK" in codes(result)


def test_no_thin_link_warning_when_the_threshold_is_not_asked_for(good_file):
    assert "THIN_LINK" not in codes(validate_text(good_file))


def test_a_node_that_heard_nothing_is_worth_knowing_about():
    result = validate_text(make_file(row(S.ROW_BOOT)))
    assert result.ok
    assert "NO_PACKETS" in codes(result)
