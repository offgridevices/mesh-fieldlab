"""Helpers for building log files in tests.

These build rows the way the firmware is specified to build them, so a test
that changes shape here is a signal that the contract moved.
"""

from __future__ import annotations

import pytest

from fieldlab import schema as S

RX_NODE = 1111111111
TX_NODE = 2222222222

BOOT_EXTRA = S.format_extra(
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
    {"name": "N2", "lat": "39.8290", "lon": "-98.5780", "batt": "88", "last_heard": "1786000000"}
)


def row(row_type: str = S.ROW_PKT, **overrides: object) -> str:
    """One CSV line, valid by default, with any field overridden."""
    values = {name: "0" for name in S.COLUMN_NAMES}
    values.update(
        schema_ver=str(S.SCHEMA_VERSION),
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
        )
    elif row_type == S.ROW_BOOT:
        values["extra"] = BOOT_EXTRA
    elif row_type == S.ROW_STATUS:
        values["extra"] = STATUS_EXTRA
    elif row_type == S.ROW_NODE:
        values.update(tx_node=str(TX_NODE), extra=NODE_EXTRA)

    for key, value in overrides.items():
        values[key] = str(value)
    return ",".join(values[name] for name in S.COLUMN_NAMES)


def make_file(*rows: str, header: str | None = None, trailing_newline: bool = True) -> str:
    body = "\n".join([header if header is not None else S.HEADER, *rows])
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
