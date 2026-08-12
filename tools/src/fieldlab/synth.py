"""Generate plausible log files without a radio.

There is no hardware yet, and the analysis tooling still has to be written and
tested against something. This produces files that obey the schema and look
roughly like a real session: a few nodes, mostly direct receptions, some
relayed, flood copies of the same packet, a status heartbeat.

The numbers are made up. This is scaffolding for developing the tools, never
a substitute for a measurement.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from fieldlab import schema as S


@dataclass
class SynthConfig:
    rx_node: int = 1001
    peers: tuple[int, ...] = (1002, 1003, 1004)
    short_name: str = "N1"
    boot_count: int = 1
    duration_s: int = 3600
    interval_s: int = 20
    #: Fraction of packets that arrived over a direct RF path.
    direct_fraction: float = 0.75
    #: Fraction of packets that also show up as a duplicate flood copy.
    duplicate_fraction: float = 0.15
    start_epoch: int = 1786000000
    set_clock: bool = True
    # The geographic centre of the contiguous United States: a field in Kansas,
    # and an obvious enough placeholder that no sample file can be mistaken for
    # a record of a real test site.
    lat: float = 39.8283
    lon: float = -98.5795
    alt_m: int = 42
    antenna: str = "rak-stock-3dbi"
    firmware: str = "2.5.4"
    preset: str = "LONG_FAST"
    seed: int = 7


def _row(**values: object) -> str:
    row = {name: "0" for name in S.COLUMN_NAMES}
    row["schema_ver"] = str(S.SCHEMA_VERSION)
    row["extra"] = ""
    row.update({k: str(v) for k, v in values.items()})
    return ",".join(row[name] for name in S.COLUMN_NAMES)


def synth_log(config: SynthConfig | None = None) -> str:
    """Return the full text of one synthetic log file."""
    c = config or SynthConfig()
    if c.interval_s < 1:
        raise ValueError("interval_s must be at least one second")
    if c.duration_s < c.interval_s:
        raise ValueError("duration_s is shorter than one packet interval")
    if len(c.peers) < 1:
        raise ValueError("a node needs at least one peer to hear")
    rng = random.Random(c.seed)

    def clock(second: int) -> int:
        return c.start_epoch + second if c.set_clock else 0

    lines = [
        S.HEADER,
        _row(
            uptime_ms=120,
            dev_rx_time=clock(0),
            rx_node=c.rx_node,
            row_type=S.ROW_BOOT,
            extra=S.format_extra(
                {
                    "fw": c.firmware,
                    "preset": c.preset,
                    "boot": str(c.boot_count),
                    "lat": f"{c.lat:.6f}",
                    "lon": f"{c.lon:.6f}",
                    "alt": str(c.alt_m),
                    "ant": c.antenna,
                    "name": c.short_name,
                }
            ),
        ),
    ]

    # Each peer sits at its own distance, so its median signal differs — which
    # is the thing the analysis is supposed to recover.
    base_rssi = {peer: rng.randint(-110, -72) for peer in c.peers}
    packets_written = 0
    next_status = 60
    pkt_id = rng.randint(100_000, 900_000)

    for second in range(c.interval_s, c.duration_s + 1, c.interval_s):
        while second >= next_status:
            lines.append(
                _row(
                    uptime_ms=next_status * 1000,
                    dev_rx_time=clock(next_status),
                    rx_node=c.rx_node,
                    row_type=S.ROW_STATUS,
                    extra=S.format_extra(
                        {"rows": str(packets_written), "sd_ok": "1", "heap": "182400"}
                    ),
                )
            )
            next_status += 60

        tx = rng.choice(c.peers)
        pkt_id += 1
        hops = 0 if rng.random() < c.direct_fraction else rng.choice([1, 2])
        rssi = int(base_rssi[tx] + rng.gauss(0, 4) - 6 * hops)
        snr = max(S.SNR_MIN + 1, min(S.SNR_MAX - 1, rng.gauss(7 - 4 * hops, 3)))

        copies = 2 if (hops and rng.random() < c.duplicate_fraction) else 1
        for copy in range(copies):
            lines.append(
                _row(
                    uptime_ms=second * 1000 + copy * 40,
                    dev_rx_time=clock(second),
                    rx_node=c.rx_node,
                    tx_node=tx,
                    pkt_id=pkt_id,
                    rx_rssi_dbm=max(S.RSSI_MIN + 1, min(-20, rssi)),
                    rx_snr_db=f"{snr:.2f}",
                    hop_limit=3 - hops,
                    hop_start=3,
                    hops_used=hops,
                    relay_node=rng.randint(1, 255) if hops else 0,
                    portnum=1,
                    payload_size=rng.randint(8, 40),
                    channel=0,
                    row_type=S.ROW_PKT,
                )
            )
            packets_written += 1

    return "\n".join(lines) + "\n"


def filename_for(config: SynthConfig) -> str:
    return f"LOG_{config.short_name}_{config.boot_count}.csv"
