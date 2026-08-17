"""Generate a plausible session without a radio.

There is no hardware yet, and the analysis has to be written and tested
against something. This models one shared mesh rather than four independent
nodes: every transmission is a single event with one packet id, and each other
node either hears it directly, hears a relayed copy, or misses it — which is
what makes cross-file behaviour (deduplication, delivery share, asymmetry)
testable at all.

Signal strength falls off with distance and is perturbed per packet, so links
are asymmetric and the medians differ by pair. Those are the properties the
analysis is supposed to recover.

The numbers are invented. This is scaffolding for developing the tools, never
a substitute for a measurement.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from fieldlab import schema as S

#: Roughly what an open field looks like on LONG_FAST: a strong reading close
#: in, falling off with distance. The exponent is deliberately steeper than
#: free space, because antennas a metre off the ground lose far more than the
#: textbook figure — and a model that is too kind produces a session where
#: every link is comfortable, which would exercise nothing.
#:
#: Calibrated to be plausible, not accurate. Replace with measurements.
RSSI_AT_100M = -55.0
PATH_LOSS_PER_DECADE = 35.0

#: Below this a packet is not decoded. Real sensitivity is lower, but noise
#: and interference make this the practical floor.
RSSI_FLOOR = -118.0


@dataclass
class MeshConfig:
    node_count: int = 4
    duration_s: int = 3600
    interval_s: int = 20
    start_epoch: int = 1786000000
    set_clock: bool = True
    seed: int = 7
    boot_count: int = 1
    firmware: str = "0.1.0"
    preset: str = "LONG_FAST"
    region: str = "US"
    hop_limit: int = 3
    antenna: str = "rak-stock-3dbi"
    #: Fraction of direct receptions that also arrive a second time by another
    #: route — the flood copies the analysis has to remove.
    duplicate_fraction: float = 0.12

    #: Centre of the invented field: the geographic centre of the contiguous
    #: United States, an obvious enough placeholder that no sample file can be
    #: mistaken for a record of a real test site.
    origin_lat: float = 39.8283
    origin_lon: float = -98.5795

    def node_id(self, index: int) -> int:
        return 1001 + index

    def short_name(self, index: int) -> str:
        return f"N{index + 1}"

    def position(self, index: int) -> tuple[float, float, int]:
        """Spread the nodes unevenly. A neat grid teaches you nothing."""
        offsets = [(0.0, 0.0), (0.0090, 0.0043), (0.0031, 0.0165), (-0.0064, 0.0208)]
        dlat, dlon = offsets[index % len(offsets)]
        # Nodes further out sit a little higher, so elevation differences exist.
        return self.origin_lat + dlat, self.origin_lon + dlon, 40 + index * 3


@dataclass
class _Node:
    index: int
    node_id: int
    name: str
    lat: float
    lon: float
    alt: int
    lines: list[str] = field(default_factory=list)
    rows: int = 0


def _metres(a: _Node, b: _Node) -> float:
    """Flat-earth approximation, which is ample over a field."""
    mean_lat = math.radians((a.lat + b.lat) / 2)
    dx = (b.lon - a.lon) * 111_320 * math.cos(mean_lat)
    dy = (b.lat - a.lat) * 110_574
    return math.hypot(dx, dy)


def _base_rssi(distance_m: float, bias_db: float) -> float:
    d = max(distance_m, 1.0)
    return RSSI_AT_100M - PATH_LOSS_PER_DECADE * math.log10(d / 100.0) + bias_db


def _row(**values: object) -> str:
    row = {name: "0" for name in S.COLUMN_NAMES}
    row["schema_ver"] = str(S.SCHEMA_VERSION)
    row["extra"] = ""
    row.update({k: str(v) for k, v in values.items()})
    return ",".join(row[name] for name in S.COLUMN_NAMES)


def synth_session(config: MeshConfig | None = None) -> dict[str, str]:
    """Return {filename: file text} for every node in one session."""
    c = config or MeshConfig()
    if c.node_count < 2:
        raise ValueError("a mesh needs at least two nodes")
    if c.interval_s < 1:
        raise ValueError("interval_s must be at least one second")
    if c.duration_s < c.interval_s:
        raise ValueError("duration_s is shorter than one packet interval")

    rng = random.Random(c.seed)

    nodes: list[_Node] = []
    for i in range(c.node_count):
        lat, lon, alt = c.position(i)
        nodes.append(_Node(i, c.node_id(i), c.short_name(i), lat, lon, alt))

    # A per-direction offset is what makes A->B and B->A differ. Real links are
    # often several dB apart, and anything assuming otherwise is wrong about
    # half of them.
    bias = {
        (a.node_id, b.node_id): rng.uniform(-6.0, 6.0)
        for a in nodes for b in nodes if a is not b
    }

    def clock(second: int) -> int:
        return c.start_epoch + second if c.set_clock else 0

    for n in nodes:
        n.lines.append(S.HEADER)
        n.lines.append(_row(
            uptime_ms=120, dev_rx_time=clock(0), rx_node=n.node_id, row_type=S.ROW_BOOT,
            extra=S.format_extra({
                "fw": c.firmware, "preset": c.preset, "region": c.region,
                "hops": str(c.hop_limit), "boot": str(c.boot_count),
                "lat": f"{n.lat:.6f}", "lon": f"{n.lon:.6f}", "alt": str(n.alt),
                "ant": c.antenna, "name": n.name,
                "st_card": "1", "st_write": "1", "st_radio": "1",
                "st_pos": "1", "st_clock": "1" if c.set_clock else "0",
                "st_heard": str(c.node_count - 1), "disp": "1", "batt": "92",
            }),
        ))

    def emit(node: _Node, second: int, sender: _Node, pkt_id: int,
             rssi: float, snr: float, hops: int, offset_ms: int = 0) -> None:
        node.lines.append(_row(
            uptime_ms=second * 1000 + offset_ms,
            dev_rx_time=clock(second),
            rx_node=node.node_id,
            tx_node=sender.node_id,
            pkt_id=pkt_id,
            rx_rssi_dbm=int(round(max(RSSI_FLOOR - 5, min(-20.0, rssi)))),
            rx_snr_db=f"{snr:.2f}",
            hop_limit=c.hop_limit - hops,
            hop_start=c.hop_limit,
            hops_used=hops,
            relay_node=rng.randint(1, 255) if hops else 0,
            portnum=1,
            payload_size=rng.randint(8, 40),
            channel=0,
            row_type=S.ROW_PKT,
        ))
        node.rows += 1

    next_status = 60
    pkt_id = rng.randint(100_000, 400_000)

    for second in range(c.interval_s, c.duration_s + 1, c.interval_s):
        while second >= next_status:
            for n in nodes:
                n.lines.append(_row(
                    uptime_ms=next_status * 1000, dev_rx_time=clock(next_status),
                    rx_node=n.node_id, row_type=S.ROW_STATUS,
                    extra=S.format_extra(
                        {"rows": str(n.rows), "sd_ok": "1", "heap": "182400"}
                    ),
                ))
            next_status += 60

        # One transmission, one packet id, seen by whoever can hear it.
        sender = nodes[(second // c.interval_s) % len(nodes)]
        pkt_id += 1

        heard_directly: list[_Node] = []
        for receiver in nodes:
            if receiver is sender:
                continue
            rssi = _base_rssi(_metres(sender, receiver),
                              bias[(sender.node_id, receiver.node_id)])
            rssi += rng.gauss(0, 3.5)
            if rssi < RSSI_FLOOR:
                continue

            snr = max(S.SNR_MIN + 2, min(S.SNR_MAX - 2, (rssi + 120) / 4 + rng.gauss(0, 1.5)))
            emit(receiver, second, sender, pkt_id, rssi, snr, hops=0)
            heard_directly.append(receiver)

            # A second copy of the same packet by another route: the flood
            # duplicate the analysis has to drop before counting anything.
            if rng.random() < c.duplicate_fraction:
                emit(receiver, second, sender, pkt_id, rssi, snr, hops=0, offset_ms=60)

        # Anyone who missed it may still get a relayed copy, if somebody who
        # did hear it is close enough to them.
        for receiver in nodes:
            if receiver is sender or receiver in heard_directly:
                continue
            for relay in heard_directly:
                rssi = _base_rssi(_metres(relay, receiver),
                                  bias[(relay.node_id, receiver.node_id)]) + rng.gauss(0, 3.5)
                if rssi >= RSSI_FLOOR:
                    snr = max(S.SNR_MIN + 2, min(S.SNR_MAX - 2, (rssi + 120) / 4))
                    emit(receiver, second, sender, pkt_id, rssi, snr, hops=1, offset_ms=120)
                    break

    # A node with no clock cannot date its file, so it falls back to the boot
    # counter — the same two names the real logger produces.
    #
    # The real logger stamps this in ITS local time. Synth stamps UTC, so one
    # seed gives the same filenames on every machine; a test that changed
    # answer with the developer's timezone would be worse than no test.
    if c.set_clock:
        stamp = time.strftime("%Y%m%d_%H%M", time.gmtime(c.start_epoch))
        return {
            f"LOG_{n.name}_{stamp}.csv": "\n".join(n.lines) + "\n"
            for n in nodes
        }
    return {
        f"LOG_{n.name}_{c.boot_count}.csv": "\n".join(n.lines) + "\n"
        for n in nodes
    }
