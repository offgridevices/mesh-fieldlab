"""Turn a folder of cards into per-link measurements.

Four nodes produce six pairs, and each pair is two directed links, because
radio paths are not symmetric. This reduces a session to those twelve numbers
and the confidence you can place in each.

Three decisions do most of the work, and getting any of them wrong produces a
result that looks reasonable and means nothing:

**Only direct receptions measure a path.** A packet that was relayed tells you
about the last hop, not about the pair of nodes at its ends. Everything with a
hop count above zero is set aside for routing questions.

**Flood copies must be removed first.** The same packet arrives at the same
node several times by different routes. Counting them would inflate every
number in proportion to how well the mesh was working, which is exactly the
wrong bias.

**Medians, not means.** Signal strength is skewed and a single multipath null
drags an average somewhere no reading ever was.

Signal strength answers whether a link exists. It cannot answer what the link
cost, because a channel that is quiet and a channel that is saturated produce
the same RSSI. That question is answered by the radio's own channel
utilisation, carried on NODE rows from v4 onward and summarised here.

Like the checker, this depends on nothing outside the standard library, so it
runs on whatever laptop is in the field.
"""

from __future__ import annotations

import csv
import io
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median, quantiles

from fieldlab import schema as S
from fieldlab.validate import validate_file

EARTH_RADIUS_M = 6371008.8


@dataclass(frozen=True)
class Reception:
    """One packet arriving at one node."""

    rx_node: int
    tx_node: int
    pkt_id: int
    hops_used: int
    rssi: int
    snr: float
    uptime_ms: int

    @property
    def direct(self) -> bool:
        return self.hops_used == 0


@dataclass
class ChannelLoad:
    """What one node's radio said the shared channel was costing.

    Reported by the radio itself, so it counts every transmission it can hear —
    including the traffic of anyone else on the frequency, which no per-packet
    record of our own mesh could ever see.
    """

    node: int
    #: Percent of wall-clock time the channel was busy, as sampled per report.
    utilisation: list[float] = field(default_factory=list)
    #: Percent of the last hour this node spent transmitting.
    air_tx: list[float] = field(default_factory=list)
    #: Reports that arrived with no metrics block at all.
    reports: int = 0
    absent: int = 0

    def _mid(self, values: list[float]) -> float | None:
        return median(values) if values else None

    @property
    def median_utilisation(self) -> float | None:
        return self._mid(self.utilisation)

    @property
    def peak_utilisation(self) -> float | None:
        return max(self.utilisation) if self.utilisation else None

    @property
    def median_air_tx(self) -> float | None:
        return self._mid(self.air_tx)


@dataclass
class NodeInfo:
    """What a node's BOOT row said about itself."""

    node: int
    name: str = ""
    lat: float = 0.0
    lon: float = 0.0
    alt: int = 0
    preset: str = ""
    region: str = ""
    hops: str = ""
    boot: str = ""
    antenna: str = ""
    source: str = ""
    #: v4 onward. Empty on a v3 file, which recorded only the preset name.
    #: `use_preset` is the one that decides whether `preset` means anything:
    #: with it "0" the radio was on the explicit sf/bw/cr below instead.
    use_preset: str = ""
    tx_power: str = ""
    bandwidth: str = ""
    spread_factor: str = ""
    coding_rate: str = ""
    channel_num: str = ""

    @property
    def has_position(self) -> bool:
        return not (self.lat == 0.0 and self.lon == 0.0)


@dataclass
class LinkStats:
    """One directed link: what tx looked like from where rx was standing."""

    tx: int
    rx: int
    packets: int
    rssi_median: float
    rssi_p10: float
    rssi_p90: float
    snr_median: float
    snr_p10: float
    snr_p90: float
    relayed_packets: int = 0
    #: Of the packets this sender got to *anyone*, the share that reached this
    #: receiver directly. Not an absolute delivery rate — nothing in these
    #: files records what was transmitted, only what arrived somewhere.
    heard_fraction: float | None = None
    distance_m: float | None = None
    elevation_diff_m: int | None = None


@dataclass
class Session:
    nodes: dict[int, NodeInfo] = field(default_factory=dict)
    receptions: list[Reception] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    #: (path, why) for files that were not usable
    skipped: list[tuple[str, str]] = field(default_factory=list)
    duplicates_dropped: int = 0
    channel: dict[int, ChannelLoad] = field(default_factory=dict)

    def config_mismatches(self) -> list[str]:
        """Nodes configured differently cannot be compared, however clean the data."""
        problems = []
        checks = (
            ("preset", "preset"), ("region", "region"), ("hop limit", "hops"),
            # v4. Two nodes can agree on a preset name and still be on
            # different radios: with use_preset off the name is a leftover, and
            # transmit power is never implied by a preset at all. A link matrix
            # built across a 10 dB power difference looks asymmetric for a
            # reason that has nothing to do with terrain.
            ("transmit power", "tx_power"), ("bandwidth", "bandwidth"),
            ("spreading factor", "spread_factor"), ("coding rate", "coding_rate"),
            ("frequency slot", "channel_num"), ("use-preset flag", "use_preset"),
        )
        for label, attr in checks:
            values = {getattr(n, attr) for n in self.nodes.values() if getattr(n, attr)}
            if len(values) > 1:
                listed = ", ".join(sorted(values))
                problems.append(
                    f"nodes disagree on {label}: {listed}. Readings across them are not comparable"
                )
        return problems


def haversine_m(a: NodeInfo, b: NodeInfo) -> float | None:
    """Great-circle distance in metres, or None if either position is missing."""
    if not (a.has_position and b.has_position):
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (a.lat, a.lon, b.lat, b.lon))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def _percentiles(values: list[float]) -> tuple[float, float, float]:
    """Median, 10th and 90th. Below ten samples the tails are the extremes."""
    mid = median(values)
    if len(values) < 10:
        return mid, min(values), max(values)
    deciles = quantiles(values, n=10)
    return mid, deciles[0], deciles[8]


def load_file(path: Path | str, session: Session, *, force: bool = False) -> None:
    """Read one log into the session, refusing files the checker rejected."""
    path = Path(path)
    result = validate_file(path)
    if result.errors and not force:
        first = result.errors[0]
        session.skipped.append((str(path), f"{first.code}: {first.message}"))
        return

    session.files.append(str(path))
    seen: set[tuple[int, int, int, int]] = set()

    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if header is None:
            return

        # Read the file under the layout its own header declares. A v3 file
        # read against v4 names would misalign every column after tx_node and
        # still produce rows that parse, which is the quietest way to get a
        # wrong answer out of a right file.
        names = S.column_names_for(S.version_for_header([f.strip() for f in header]) or S.SCHEMA_VERSION)

        for raw in reader:
            if len(raw) != len(names):
                continue  # the checker has already reported this
            row = dict(zip(names, (v.strip() for v in raw)))

            if row["row_type"] == S.ROW_BOOT:
                _read_boot(row, session, str(path))
            elif row["row_type"] == S.ROW_PKT:
                _read_packet(row, session, seen)
            elif row["row_type"] == S.ROW_NODE:
                _read_node(row, session)


def _read_boot(row: dict[str, str], session: Session, source: str) -> None:
    extra = S.parse_extra(row["extra"])
    try:
        node = int(row["rx_node"])
    except ValueError:
        return

    def number(key: str, default: float = 0.0) -> float:
        try:
            return float(extra.get(key, default))
        except ValueError:
            return default

    session.nodes[node] = NodeInfo(
        node=node,
        name=extra.get("name", ""),
        lat=number("lat"),
        lon=number("lon"),
        alt=int(number("alt")),
        preset=extra.get("preset", ""),
        region=extra.get("region", ""),
        hops=extra.get("hops", ""),
        boot=extra.get("boot", ""),
        antenna=extra.get("ant", ""),
        source=source,
        use_preset=extra.get("usepreset", ""),
        tx_power=extra.get("txpwr", ""),
        bandwidth=extra.get("bw", ""),
        spread_factor=extra.get("sf", ""),
        coding_rate=extra.get("cr", ""),
        channel_num=extra.get("chan", ""),
    )


def _read_node(row: dict[str, str], session: Session) -> None:
    """Take the channel figures off one node report.

    Recorded against the node that *reported* them, not the node the row
    describes. Utilisation is a property of a place — what one radio could hear
    where it stood — so attributing a neighbour's copy of the number to that
    neighbour would count the same measurement several times over and average
    away the differences between positions, which are the whole point.
    """
    try:
        reporter = int(row["rx_node"])
    except ValueError:
        return

    extra = S.parse_extra(row["extra"])
    load = session.channel.get(reporter)
    if load is None:
        load = session.channel[reporter] = ChannelLoad(node=reporter)

    # Only the reporter's own row carries its own radio's figures; the rows it
    # writes about its neighbours repeat what those neighbours last advertised,
    # which is a different measurement taken somewhere else.
    if row["tx_node"] != row["rx_node"]:
        return

    load.reports += 1
    got = False
    for key, target in (("chan_util", load.utilisation), ("air_tx", load.air_tx)):
        raw = extra.get(key, S.ABSENT)
        if raw == S.ABSENT:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if math.isfinite(value):
            target.append(value)
            got = True
    if not got:
        load.absent += 1


def _read_packet(row: dict[str, str], session: Session, seen: set) -> None:
    try:
        rx = int(row["rx_node"])
        tx = int(row["tx_node"])
        pkt_id = int(row["pkt_id"])
        hops = int(row["hops_used"])
        rssi = int(row["rx_rssi_dbm"])
        snr = float(row["rx_snr_db"])
        uptime = int(row["uptime_ms"])
    except ValueError:
        return

    # rssi of exactly zero marks a locally originated row rather than a
    # reception, and a node cannot measure a path to itself.
    if rssi == 0 or tx == 0 or tx == rx:
        return

    # A packet id of zero cannot be deduplicated, so every copy is kept and
    # the count is knowingly generous rather than silently wrong.
    if pkt_id != 0:
        key = (rx, tx, pkt_id, hops)
        if key in seen:
            session.duplicates_dropped += 1
            return
        seen.add(key)

    session.receptions.append(
        Reception(rx_node=rx, tx_node=tx, pkt_id=pkt_id, hops_used=hops,
                  rssi=rssi, snr=snr, uptime_ms=uptime)
    )


def load_directory(path: Path | str, *, force: bool = False) -> Session:
    session = Session()
    for csv_path in sorted(Path(path).glob("*.csv")):
        load_file(csv_path, session, force=force)
    return session


def link_stats(session: Session) -> list[LinkStats]:
    """Per directed link, from direct receptions only."""
    direct: dict[tuple[int, int], list[Reception]] = defaultdict(list)
    relayed: dict[tuple[int, int], int] = defaultdict(int)

    # Denominator for heard_fraction: every packet this sender got to anyone.
    reached_anyone: dict[int, set[int]] = defaultdict(set)

    for r in session.receptions:
        if r.direct:
            direct[(r.tx_node, r.rx_node)].append(r)
        else:
            relayed[(r.tx_node, r.rx_node)] += 1
        if r.pkt_id:
            reached_anyone[r.tx_node].add(r.pkt_id)

    out: list[LinkStats] = []
    for (tx, rx), rows in direct.items():
        rssi_mid, rssi_lo, rssi_hi = _percentiles([float(r.rssi) for r in rows])
        snr_mid, snr_lo, snr_hi = _percentiles([r.snr for r in rows])

        sent = len(reached_anyone.get(tx, ()))
        heard_here = len({r.pkt_id for r in rows if r.pkt_id})
        fraction = (heard_here / sent) if sent else None

        a, b = session.nodes.get(tx), session.nodes.get(rx)
        distance = haversine_m(a, b) if a and b else None
        elevation = (b.alt - a.alt) if a and b else None

        out.append(LinkStats(
            tx=tx, rx=rx, packets=len(rows),
            rssi_median=rssi_mid, rssi_p10=rssi_lo, rssi_p90=rssi_hi,
            snr_median=snr_mid, snr_p10=snr_lo, snr_p90=snr_hi,
            relayed_packets=relayed.get((tx, rx), 0),
            heard_fraction=fraction,
            distance_m=distance,
            elevation_diff_m=elevation,
        ))

    out.sort(key=lambda s: (s.tx, s.rx))
    return out


def asymmetry(links: list[LinkStats]) -> list[tuple[int, int, float, float]]:
    """(a, b, difference in dB, worse direction's median) for each pair.

    Real links are often several dB apart in the two directions. A design that
    assumes symmetry will be wrong about half of them.
    """
    by_pair = {(s.tx, s.rx): s for s in links}
    out = []
    for (tx, rx), forward in by_pair.items():
        if tx >= rx:
            continue
        back = by_pair.get((rx, tx))
        if back is None:
            continue
        diff = abs(forward.rssi_median - back.rssi_median)
        out.append((tx, rx, diff, min(forward.rssi_median, back.rssi_median)))
    out.sort(key=lambda t: -t[2])
    return out
