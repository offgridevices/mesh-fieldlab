"""The pin map is a contract, and after the hardware split nothing else checks it.

`firmware/src/config.h` says "See docs/packet-logger-design.md §5.2. Changing
these means changing that table too." Nothing enforced that, and the board it
refers to now lives in a separate repository
(`offgridevices/offgrid-hardware`), so a reviewer can no longer see both sides
of the agreement in one diff.

Nothing fails at build time when these drift. The symptom is a logger reading
the wrong pin in a field with no network and no second chance at the day, so
the disagreement is worth catching here instead.

This checks the two sides that live in this repository against each other. It
cannot see the board itself; that is what the carrier's `netlist.csv` is for,
and the values below are the ones it was designed to.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DESIGN_DOC = REPO / "docs" / "packet-logger-design.md"
FIRMWARE_CONFIG = REPO / "firmware" / "src" / "config.h"

# macro in config.h -> (expected pin, a phrase identifying its row in §5.2)
#
# The phrases are deliberately the part of each row that describes the
# physical connection rather than the pin, so that renaming a pin on one side
# fails instead of quietly matching.
PINS = {
    "RADIO_RX_PIN": ("D7", "J7 pin 2"),
    "RADIO_TX_PIN": ("D6", "J7 pin 1"),
    "SD_CS_PIN": ("D3", "| CS |"),
    "BUTTON_PIN": ("D0", "Momentary button"),
}


def _pin_macro(text: str, name: str) -> str:
    """The value of a `#define <name> <pin>`, with any trailing comment cut."""
    match = re.search(rf"^#define\s+{name}\s+(.+)$", text, re.M)
    if not match:
        raise AssertionError(f"{name} is not defined in {FIRMWARE_CONFIG.name}")
    value = match.group(1)
    value = re.split(r"//|/\*", value)[0]
    return value.strip()


@pytest.fixture(scope="module")
def firmware() -> str:
    return FIRMWARE_CONFIG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def wiring() -> str:
    """Section 5.2 of the design document, up to the next section."""
    doc = DESIGN_DOC.read_text(encoding="utf-8")
    start = doc.index("### 5.2 Wiring")
    end = doc.index("### 5.3", start)
    return doc[start:end]


@pytest.mark.parametrize("macro", sorted(PINS))
def test_firmware_pin_matches_design_doc(macro: str, firmware: str, wiring: str) -> None:
    expected, row_marker = PINS[macro]

    actual = _pin_macro(firmware, macro)
    assert actual == expected, (
        f"{macro} is {actual} in config.h but this test expects {expected}. "
        f"If the wiring genuinely changed, update the table in "
        f"{DESIGN_DOC.name} §5.2, the carrier board in offgrid-hardware, and "
        f"this test together."
    )

    rows = [ln for ln in wiring.splitlines() if row_marker in ln]
    assert rows, f"§5.2 has no row containing {row_marker!r} any more"
    assert any(re.search(rf"\b{expected}\b", ln) for ln in rows), (
        f"§5.2 row {row_marker!r} no longer mentions {expected}, but "
        f"config.h still defines {macro} as {expected}."
    )


def test_no_firmware_pin_is_undocumented(firmware: str) -> None:
    """Every `*_PIN` macro must be one this test knows how to check.

    A new pin added to config.h without a row in §5.2 is exactly the drift
    this file exists to stop, so adding one has to fail until it is written
    down on both sides.
    """
    defined = set(re.findall(r"^#define\s+([A-Z0-9_]*_PIN)\b", firmware, re.M))
    assert defined == set(PINS), (
        f"config.h defines {sorted(defined - set(PINS))} which this test does "
        f"not check, or is missing {sorted(set(PINS) - defined)}. Document the "
        f"pin in {DESIGN_DOC.name} §5.2 and add it to PINS above."
    )
