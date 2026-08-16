from __future__ import annotations

import re
from pathlib import Path

import pytest

from fieldlab import schema as S

REPO = Path(__file__).resolve().parents[2]
DESIGN_DOC = REPO / "docs" / "packet-logger-design.md"
FIRMWARE_SCHEMA = REPO / "firmware" / "src" / "log_schema.h"


def _c_macro(text: str, name: str) -> str:
    """Return a C macro's value, joining its line continuations."""
    match = re.search(rf"^#define\s+{name}\b(.*)$", text, re.M)
    if not match:
        return ""
    lines = [match.group(1)]
    pos = match.end()
    while lines[-1].rstrip().endswith("\\"):
        end = text.find("\n", pos + 1)
        if end == -1:
            break
        lines.append(text[pos:end])
        pos = end
    return "".join(lines)


def test_column_names_are_unique():
    assert len(set(S.COLUMN_NAMES)) == len(S.COLUMN_NAMES)


def test_header_is_the_columns_in_order():
    assert S.HEADER.split(",") == list(S.COLUMN_NAMES)


def test_row_type_is_the_second_to_last_column():
    # The firmware appends `extra` after `row_type`; anything reading the
    # format positionally depends on that staying true.
    assert S.COLUMN_NAMES[-2:] == ("row_type", "extra")


def test_every_row_type_has_a_spec():
    assert set(S.EXTRA_SPECS) == set(S.ROW_TYPES)


def test_packet_rows_require_nothing_extra():
    assert S.EXTRA_SPECS[S.ROW_PKT].required == frozenset()


def test_required_and_optional_extra_keys_do_not_overlap():
    for row_type, spec in S.EXTRA_SPECS.items():
        assert not (spec.required & spec.optional), row_type


def test_extra_round_trips():
    pairs = {"fw": "2.5.4", "preset": "LONG_FAST", "boot": "7"}
    assert S.parse_extra(S.format_extra(pairs)) == pairs


def test_extra_of_an_empty_field_is_empty():
    assert S.parse_extra("") == {}


def test_extra_is_written_in_a_stable_order():
    pairs = {"z": "1", "a": "2", "m": "3"}
    assert S.format_extra(pairs) == "a=2;m=3;z=1"


def test_current_version_is_supported():
    assert S.SCHEMA_VERSION in S.SUPPORTED_SCHEMA_VERSIONS


def test_the_design_document_describes_the_same_columns_as_the_code():
    """The doc is the contract people read; this module is the one tools read.

    They have to say the same thing, so a column added in one place and
    forgotten in the other fails here rather than in the field.
    """
    if not DESIGN_DOC.exists():
        pytest.skip("design document not present")

    match = re.search(r"^schema_ver,.*?row_type,extra$", DESIGN_DOC.read_text(), re.S | re.M)
    assert match, "no header block found in the design document"
    documented = match.group(0).replace("\n", "")
    assert documented == S.HEADER


def test_the_firmware_writes_the_columns_this_module_expects():
    """The firmware and this module are the two halves of one contract.

    They are written in different languages and cannot share a definition, so
    a column added on one side would otherwise silently go missing on the
    other — and the first symptom would be a field day of unreadable files.
    """
    if not FIRMWARE_SCHEMA.exists():
        pytest.skip("firmware not present")

    text = FIRMWARE_SCHEMA.read_text()
    written = "".join(re.findall(r'"([^"]*)"', _c_macro(text, "LOG_HEADER")))
    assert written == S.HEADER


def test_the_firmware_writes_the_schema_version_this_module_expects():
    if not FIRMWARE_SCHEMA.exists():
        pytest.skip("firmware not present")

    value = _c_macro(FIRMWARE_SCHEMA.read_text(), "LOG_SCHEMA_VERSION").strip()
    assert int(value) == S.SCHEMA_VERSION


def test_the_firmware_and_this_module_agree_on_the_row_type_names():
    if not FIRMWARE_SCHEMA.exists():
        pytest.skip("firmware not present")

    text = FIRMWARE_SCHEMA.read_text()
    for macro, expected in (
        ("ROW_PKT", S.ROW_PKT),
        ("ROW_STATUS", S.ROW_STATUS),
        ("ROW_NODE", S.ROW_NODE),
        ("ROW_BOOT", S.ROW_BOOT),
    ):
        assert _c_macro(text, macro).strip().strip('"') == expected, macro


def test_every_extra_key_the_firmware_writes_is_one_this_module_knows():
    """Catches the other half of the contract: the key/value detail.

    An unrecognised key is only a warning at read time, so without this a
    firmware change could quietly make every file in a session complain — and
    the first anyone would know is a wall of warnings after a field day.
    """
    sources = [
        REPO / "firmware" / "src" / "selftest.cpp",
        REPO / "firmware" / "src" / "logfile.cpp",
    ]
    if not all(p.exists() for p in sources):
        pytest.skip("firmware not present")

    known = set()
    for spec in S.EXTRA_SPECS.values():
        known |= spec.required | spec.optional

    written = set()
    for path in sources:
        for literal in re.findall(r'"((?:[^"\\]|\\.)*)"', path.read_text()):
            written |= set(re.findall(r"\b([a-z][a-z0-9_]*)=", literal))

    assert written, "found no key=value pairs in the firmware; the scan is broken"
    assert written <= known, f"firmware writes keys the schema does not know: {sorted(written - known)}"


def test_packet_only_columns_are_the_ones_that_describe_a_reception():
    assert "rx_snr_db" in S.PACKET_ONLY
    assert "rx_rssi_dbm" in S.PACKET_ONLY
    # tx_node is not packet-only: NODE rows use it to name their subject.
    assert "tx_node" not in S.PACKET_ONLY
    assert "rx_node" not in S.PACKET_ONLY
