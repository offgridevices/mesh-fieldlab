"""Helpers for building log files in tests.

These build rows the way the firmware is specified to build them, so a test
that changes shape here is a signal that the contract moved.
"""

from __future__ import annotations

import pytest

from fieldlab import schema as S

RX_NODE = 1111111111
TX_NODE = 2222222222

#: The radio settings a v4 BOOT row is required to carry. Kept here rather
#: than repeated in each test module, because a test file that builds its own
#: BOOT row and forgets one of these fails for a reason that has nothing to do
#: with what it is testing.
BOOT_RADIO_DEFAULTS = {
    "usepreset": "1",
    "txpwr": "30",
    "bw": "250",
    "sf": "11",
    "cr": "5",
    "chan": "20",
    "txon": "1",
}

BOOT_EXTRA = S.format_extra(
    {
        "fw": "2.5.4",
        "preset": "LONG_FAST",
        "boot": "7",
        "lat": "39.8283",
        "lon": "-98.5795",
        "alt": "42",
        "ant": "rak-stock-3dbi",
        # v4: what the preset name stands for. Required, because a file that
        # names a preset without these cannot say what the radio was doing.
        **BOOT_RADIO_DEFAULTS,
    }
)

#: The same BOOT row as a v3 logger wrote it: no radio settings block, because
#: nothing recorded one until v4.
BOOT_EXTRA_V3 = S.format_extra(
    {
        "fw": "2.5.4",
        "preset": "LONG_FAST",
        "boot": "7",
        "lat": "39.8283",
        "lon": "-98.5795",
        "alt": "42",
        "ant": "rak-stock-3dbi",
    }
)

STATUS_EXTRA = S.format_extra({"rows": "10", "sd_ok": "1", "heap": "180000"})

NODE_EXTRA = S.format_extra(
    {
        "name": "N2",
        "lat": "39.8290",
        "lon": "-98.5780",
        "batt": "88",
        "last_heard": "1786000000",
        # v4: what the radio said the shared channel was costing.
        "chan_util": "9.5",
        "air_tx": "2.4",
        "volt": "4.01",
        "pos_time": "1786000000",
    }
)

#: A v3 NODE row: no channel figures, because nothing carried them yet.
NODE_EXTRA_V3 = S.format_extra(
    {"name": "N2", "lat": "39.8290", "lon": "-98.5780", "batt": "88", "last_heard": "1786000000"}
)

#: The same row with no metrics block, which is what a neighbour heard once in
#: passing looks like. Absence is an empty value, never a zero — a channel
#: genuinely at 0% and a radio that did not answer must stay distinguishable.
NODE_EXTRA_NO_METRICS = S.format_extra(
    {
        "name": "N2",
        "lat": "39.8290",
        "lon": "-98.5780",
        "batt": "88",
        "last_heard": "1786000000",
        "chan_util": S.ABSENT,
        "air_tx": S.ABSENT,
        "volt": S.ABSENT,
        "pos_time": "1786000000",
    }
)


def row(row_type: str = S.ROW_PKT, *, version: int = S.SCHEMA_VERSION, **overrides: object) -> str:
    """One CSV line, valid by default, with any field overridden.

    `version` builds the row under an older layout, so the back-compatibility
    guarantee can be tested with a file that is genuinely old rather than a
    new one with fields removed.
    """
    names = S.column_names_for(version)
    values = {name: "0" for name in names}
    values.update(
        schema_ver=str(version),
        uptime_ms="1000",
        dev_rx_time="0",
        rx_node=str(RX_NODE),
        row_type=row_type,
        extra="",
    )

    if row_type == S.ROW_PKT:
        values.update(
            tx_node=str(TX_NODE),
            pkt_id="305419896",
            rx_rssi_dbm="-84",
            rx_snr_db="6.5",
            hop_limit="3",
            hop_start="3",
            hops_used="0",
            payload_size="12",
            portnum="1",
            to_node="4294967295",
            decoded="1",
        )
    elif row_type == S.ROW_BOOT:
        values["extra"] = BOOT_EXTRA if version >= 4 else BOOT_EXTRA_V3
    elif row_type == S.ROW_STATUS:
        values["extra"] = STATUS_EXTRA
    elif row_type == S.ROW_NODE:
        values.update(
            tx_node=str(TX_NODE),
            extra=NODE_EXTRA if version >= 4 else NODE_EXTRA_V3,
        )

    for key, value in overrides.items():
        if key in values:
            values[key] = str(value)
    return ",".join(values[name] for name in names)


def make_file(
    *rows: str,
    header: str | None = None,
    trailing_newline: bool = True,
    version: int = S.SCHEMA_VERSION,
) -> str:
    if header is None:
        header = S.header_for(version)
    body = "\n".join([header, *rows])
    return body + "\n" if trailing_newline else body


# A plausible absolute clock, as the Meshtastic CLI would have pushed it to
# the device before deployment.
T0 = 1786000000


@pytest.fixture
def good_file() -> str:
    return make_file(
        row(S.ROW_BOOT, uptime_ms=100, dev_rx_time=T0),
        row(S.ROW_PKT, uptime_ms=5000, dev_rx_time=T0 + 5, pkt_id=1001),
        row(S.ROW_STATUS, uptime_ms=60000, dev_rx_time=T0 + 60),
        row(S.ROW_PKT, uptime_ms=65000, dev_rx_time=T0 + 65, pkt_id=1002),
        row(S.ROW_STATUS, uptime_ms=120000, dev_rx_time=T0 + 120),
        row(S.ROW_NODE, uptime_ms=125000, dev_rx_time=T0 + 125),
    )
