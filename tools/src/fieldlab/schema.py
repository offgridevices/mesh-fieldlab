"""The on-card CSV format.

This is the contract between the logger firmware and everything that reads
its output. The firmware writes what is described here; every tool reads it
through this module rather than hard-coding column names or ranges.

Changing a column, a range, or a required key means bumping SCHEMA_VERSION
and recording the change in docs/packet-logger-design.md. Old files stay
readable because every row carries the version it was written under.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SCHEMA_VERSION = 4

# Versions this tooling can read. A file claiming a version outside this set
# is an error rather than a warning: guessing at an unknown layout is how you
# get a plausible-looking analysis of misread columns.
#
# v3 stays readable on purpose. Bench captures taken under it are the only
# recordings that exist, and dropping support would orphan them to make a
# version constant tidier.
SUPPORTED_SCHEMA_VERSIONS = frozenset({3, 4})

# ---------------------------------------------------------------------------
# Row types
# ---------------------------------------------------------------------------

ROW_PKT = "PKT"
ROW_STATUS = "STATUS"
ROW_NODE = "NODE"
ROW_BOOT = "BOOT"

ROW_TYPES = (ROW_PKT, ROW_STATUS, ROW_NODE, ROW_BOOT)

FieldKind = Literal["int", "uint", "float", "enum", "extra"]


@dataclass(frozen=True)
class Column:
    """One column of the CSV, and what counts as a valid value in it."""

    name: str
    kind: FieldKind
    doc: str
    lo: float | None = None
    hi: float | None = None
    values: tuple[str, ...] = ()
    #: True for columns that only carry meaning on PKT rows. On every other
    #: row type these must be written as 0, so that a reader filtering on
    #: row_type never has to wonder whether a value is real.
    packet_only: bool = False


# Node numbers are Meshtastic's 32-bit unsigned identifiers, written in
# decimal. The CLI displays them as "!hex"; the firmware writes the number.
UINT32_MAX = 4294967295

# Hop fields are three bits wide on the air.
HOP_MAX = 7

# relay_node and next_hop are single bytes on the wire — the last byte of a
# node number, not the whole thing. They cannot identify a node on their own.
BYTE_MAX = 255

# LoRa decodes down to roughly -20 dB SNR. Anything far outside the plausible
# band means a misread column, not a remarkable radio.
SNR_MIN, SNR_MAX = -25.0, 20.0
RSSI_MIN = -150

# Seconds since the Unix epoch at 2020-01-01. An absolute timestamp below
# this is an unset or nonsense clock, not a real reading.
EPOCH_FLOOR = 1577836800

COLUMNS: tuple[Column, ...] = (
    Column("schema_ver", "uint", "Format version this row was written under", 0, 65535),
    Column("uptime_ms", "uint", "Milliseconds since boot; the authoritative relative clock", 0, UINT32_MAX),
    Column("dev_rx_time", "uint", "Device epoch seconds; 0 when the clock was never set", 0, UINT32_MAX),
    Column("rx_node", "uint", "The logging node; constant for the whole file", 1, UINT32_MAX),
    Column("tx_node", "uint", "Packet originator on PKT rows; subject node on NODE rows", 0, UINT32_MAX),
    # Added in v4. Without it a packet sent to one node and a packet sent to
    # the whole mesh are indistinguishable, and they cost the channel
    # differently — which is most of what the airtime question is about.
    Column("to_node", "uint", "Destination; BROADCAST_ADDR means the whole mesh", 0, UINT32_MAX, packet_only=True),
    Column("pkt_id", "uint", "Packet identifier; the dedupe key for flood copies", 0, UINT32_MAX, packet_only=True),
    Column("rx_rssi_dbm", "int", "Received signal strength; negative, closer to zero is stronger", RSSI_MIN, 0, packet_only=True),
    Column("rx_snr_db", "float", "Signal-to-noise ratio in dB", SNR_MIN, SNR_MAX, packet_only=True),
    Column("hop_limit", "uint", "Hops still remaining when this packet arrived", 0, HOP_MAX, packet_only=True),
    Column("hop_start", "uint", "Hops the packet was launched with", 0, HOP_MAX, packet_only=True),
    Column("hops_used", "uint", "hop_start - hop_limit; 0 means a direct reception", 0, HOP_MAX, packet_only=True),
    Column("relay_node", "uint", "Last byte of the relaying node's number, 0 if none", 0, BYTE_MAX, packet_only=True),
    Column("next_hop", "uint", "Last byte of the intended next hop, 0 if none", 0, BYTE_MAX, packet_only=True),
    Column("via_mqtt", "uint", "1 if the packet came in over the internet rather than the air", 0, 1, packet_only=True),
    Column("portnum", "uint", "Application port; only meaningful when decoded is 1", 0, UINT32_MAX, packet_only=True),
    # Added in v4. Until it existed, an undecodable packet was inferred from
    # portnum being 0 — but 0 is also UNKNOWN_APP, a portnum a decoded packet
    # can legitimately carry, so the two cases were not separable.
    Column("decoded", "uint", "1 if the payload could be decrypted and read", 0, 1, packet_only=True),
    Column("payload_size", "uint", "Payload bytes", 0, 256, packet_only=True),
    # Not always an index. The protocol reuses this field to carry a channel
    # *hash* whenever the payload is encrypted, and says so in mesh.proto:
    # "Very briefly, while sending and receiving deep inside the device Router
    # code, this field instead contains the 'channel hash' instead of the
    # index. This 'trick' is only used while the payload_variant is an
    # 'encrypted'." A logger sitting on a public mesh sees plenty of traffic it
    # holds no key for, so hashes are normal rather than exceptional — real
    # captures produced 10 and 170 within the first hour. Range-checking this
    # as an index rejects honest rows.
    Column("channel", "uint", "Channel index, or a channel hash on an undecoded packet", 0, BYTE_MAX, packet_only=True),
    Column("row_type", "enum", "Which kind of row this is", values=ROW_TYPES),
    Column("extra", "extra", "Key=value detail for non-packet rows; empty on PKT rows"),
)

#: Columns v4 introduced. Every other column kept its name, its meaning and
#: its position relative to the rest, which is what makes it safe to derive the
#: older layout by subtraction rather than maintaining two hand-written lists
#: that can drift apart.
ADDED_IN_V4 = frozenset({"to_node", "decoded"})

COLUMNS_BY_VERSION: dict[int, tuple[Column, ...]] = {
    3: tuple(c for c in COLUMNS if c.name not in ADDED_IN_V4),
    4: COLUMNS,
}


def columns_for(version: int) -> tuple[Column, ...]:
    """The column layout a file of this version was written under."""
    try:
        return COLUMNS_BY_VERSION[version]
    except KeyError:
        raise ValueError(f"no column layout is recorded for schema version {version}") from None


def column_names_for(version: int) -> tuple[str, ...]:
    return tuple(c.name for c in columns_for(version))


def packet_only_for(version: int) -> tuple[str, ...]:
    return tuple(c.name for c in columns_for(version) if c.packet_only)


def header_for(version: int) -> str:
    return ",".join(column_names_for(version))


def version_for_header(fields: list[str]) -> int | None:
    """Which schema version this header line is, or None if it matches none.

    The header is read before any row, so it is the only thing available to
    choose a layout by — and it has to be the thing that chooses, because
    reading a v3 file against v4 columns misaligns every value after tx_node
    while still producing a row that parses.
    """
    for version in sorted(COLUMNS_BY_VERSION, reverse=True):
        if fields == list(column_names_for(version)):
            return version
    return None


# The current version's tables, for callers that write rather than read.
COLUMN_NAMES: tuple[str, ...] = column_names_for(SCHEMA_VERSION)
COLUMN_INDEX: dict[str, int] = {name: i for i, name in enumerate(COLUMN_NAMES)}
BY_NAME: dict[str, Column] = {c.name: c for c in COLUMNS}
PACKET_ONLY: tuple[str, ...] = packet_only_for(SCHEMA_VERSION)

HEADER = header_for(SCHEMA_VERSION)


# ---------------------------------------------------------------------------
# The `extra` column
# ---------------------------------------------------------------------------
#
# Four kinds of row share one set of columns, because one open file on a
# microSD card is far more robust on a field node than four. The packet
# columns are fixed and typed; everything a BOOT, STATUS or NODE row needs to
# say goes in `extra` as `key=value` pairs joined by semicolons.
#
# Values may not contain a comma or a semicolon, so the field never needs
# quoting and any CSV reader handles it without special cases.

EXTRA_PAIR_SEP = ";"
EXTRA_KV_SEP = "="
EXTRA_FORBIDDEN = ",;"


#: A key whose value is the empty string. The firmware writes this when the
#: radio did not supply a reading — a node report that arrived with no
#: device-metrics block, which is ordinary for a neighbour heard once in
#: passing. It is deliberately not a sentinel number: every number a sentinel
#: could use is one some radio could legitimately report, and a NaN put through
#: printf reaches the card as "nan", which reads as neither a value nor an
#: absence.
ABSENT = ""


@dataclass(frozen=True)
class RowSpec:
    """What a non-packet row must carry in its `extra` column."""

    required: frozenset[str]
    optional: frozenset[str] = field(default_factory=frozenset)
    #: Bounds for keys whose value must be a number when it is present at all.
    #: Checked only on a non-empty value, so ABSENT stays legal everywhere.
    #: A utilisation of 500% is a firmware bug, and catching it on the card
    #: beats explaining an impossible plot a fortnight later.
    numeric: dict[str, tuple[float | None, float | None]] = field(default_factory=dict)


_SPECS_V3: dict[str, RowSpec] = {

    # Written once at startup: everything needed to interpret the rest of the
    # file without consulting a notebook.
    #
    # The st_* keys record what the boot self-test found. They are optional so
    # that files written before the display existed still read, but firmware
    # that runs the test should always write them: they are the only durable
    # record of what the screen said, and nobody remembers by the time the
    # card is read. st_heard counts neighbours heard during the boot listen.
    ROW_BOOT: RowSpec(
        required=frozenset({"fw", "preset", "boot", "lat", "lon", "alt", "ant"}),
        optional=frozenset(
            {
                "name", "region", "hops", "hw", "libver", "batt", "disp",
                "st_card", "st_write", "st_radio", "st_pos", "st_clock", "st_heard",
                # The filename is local time; tz and utcoff are what turn it
                # back into UTC without anyone having to remember which week
                # the clocks changed.
                "tz", "utcoff",
                # Seconds the boot spent held, waiting for the time before it
                # would log at all. Non-zero means the clock was late.
                "clkwait",
                # Seconds of session that had already elapsed when this file
                # was opened. Present only on a file that did not begin at
                # power-on: the node started with no usable card, or the card
                # was swapped, and it opened a new file mid-run rather than
                # waiting for somebody to power-cycle it.
                #
                # Its presence is a warning as much as a marker. Everything the
                # node heard before this instant was formed and thrown away,
                # and the STATUS rows that follow say how many rows that was.
                "resume",
            }
        ),
    ),
    # Written every 60 s: proof the node was alive and the card was working.
    #
    # `drops` counts rows the node formed while it had nowhere to put them —
    # the true size of a hole, which a gap in the timestamps can only hint at.
    # `recov` appears on the one row written the moment a fault cleared, and
    # names the blocks that came back: "card", "radio", "pos", "clock",
    # "heard", joined with "+" when several cleared at once.
    ROW_STATUS: RowSpec(
        required=frozenset({"rows", "sd_ok", "heap"}),
        optional=frozenset({"drops", "errs", "batt", "recov"}),
    ),
    # Periodic dump of what the radio believes about its neighbours.
    ROW_NODE: RowSpec(
        required=frozenset({"name", "lat", "lon", "batt", "last_heard"}),
        optional=frozenset({"alt", "snr", "hops"}),
    ),
    ROW_PKT: RowSpec(required=frozenset()),
}

# --- v4 ---------------------------------------------------------------------
#
# Three groups of key arrived together, deliberately, as one version bump.
#
# The radio settings on BOOT close a gap that made the file unable to explain
# its own measurements: a preset name alone is only binding while usepreset is
# 1, and every RSSI reading is relative to a transmit power that was recorded
# nowhere.
#
# The metrics on NODE are the point of the exercise. chan_util is what the
# radio believes the shared channel costs, which no amount of per-packet signal
# strength can be made to yield.
#
# `up` is reserved rather than written. The library drops uptime_seconds before
# user code reaches it, so writing it needs a change to the pinned fork; listing
# it as optional now means that change will not need a v5.

_BOOT_RADIO_SETTINGS = frozenset({"usepreset", "txpwr", "bw", "sf", "cr", "chan", "txon"})
_NODE_METRICS = frozenset({"chan_util", "air_tx", "volt", "pos_time"})

_SPECS_V4: dict[str, RowSpec] = {
    ROW_BOOT: RowSpec(
        required=_SPECS_V3[ROW_BOOT].required | _BOOT_RADIO_SETTINGS,
        optional=_SPECS_V3[ROW_BOOT].optional,
        numeric={
            "usepreset": (0, 1),
            "txon": (0, 1),
            # dBm at the connector. Meshtastic clamps to the region's legal
            # ceiling, so the bound here is only a sanity net.
            "txpwr": (-30, 40),
            "bw": (0, 2000),        # kHz
            "sf": (0, 12),          # 0 means the radio had not said yet
            "cr": (0, 8),           # the 4/N denominator
            "chan": (0, 200),       # frequency slot
        },
    ),
    ROW_STATUS: _SPECS_V3[ROW_STATUS],
    ROW_NODE: RowSpec(
        required=_SPECS_V3[ROW_NODE].required | _NODE_METRICS,
        optional=_SPECS_V3[ROW_NODE].optional | frozenset({"up"}),
        numeric={
            # Percentages, as the radio reports them.
            "chan_util": (0, 100),
            "air_tx": (0, 100),
            "volt": (0, 20),
        },
    ),
    ROW_PKT: _SPECS_V3[ROW_PKT],
}

EXTRA_SPECS_BY_VERSION: dict[int, dict[str, RowSpec]] = {3: _SPECS_V3, 4: _SPECS_V4}


def extra_specs_for(version: int) -> dict[str, RowSpec]:
    """What `extra` must carry, for a file of this version."""
    try:
        return EXTRA_SPECS_BY_VERSION[version]
    except KeyError:
        raise ValueError(f"no extra specification is recorded for schema version {version}") from None


#: The current version's specification, for callers that write rather than read.
EXTRA_SPECS: dict[str, RowSpec] = extra_specs_for(SCHEMA_VERSION)

#: STATUS rows are written every 60 s. A gap materially longer than that means
#: the logger stalled, so the run has a hole in it even if the rows parse.
STATUS_INTERVAL_MS = 60_000
STATUS_GAP_TOLERANCE_MS = 180_000

#: Log files are named LOG_<SHORTNAME>_<YYYYMMDD>_<HHMM>.csv, stamped in the
#: node's LOCAL time at the moment logging started. One file per power cycle,
#: so a session is always a whole file and no file grows without bound.
#:
#: The trailing -2, -3 form is the collision break for two boots inside the
#: same minute, which is how a brownout loop shows up.
#:
#: A logger that boots with no clock cannot date its file. It falls back to
#: LOG_<SHORTNAME>_<BOOTCOUNT>.csv and renames itself the moment the radio
#: supplies a time — so the boot-count form surviving in a delivered set means
#: that node never heard a single timestamped packet, and its rows can only be
#: placed relative to their own boot. Both forms are accepted here; `analyze`
#: reports which it found.
#:
#: Underscores are excluded from the short name on purpose: with one allowed,
#: LOG_N1_20260817_1432.csv could equally be read as short name "N1_20260817"
#: and boot count 1432, and the parse would be silently wrong.
FILENAME_PATTERN = (
    r"^LOG_(?P<shortname>[A-Za-z0-9-]{1,16})_"
    r"(?:(?P<date>\d{8})_(?P<time>\d{4})(?:-(?P<seq>\d))?|(?P<boot>\d{1,6}))"
    r"\.csv$"
)


def parse_extra(raw: str) -> dict[str, str]:
    """Split an `extra` field into its key/value pairs.

    Malformed input yields whatever could be read; the validator reports the
    problems separately rather than raising here.
    """
    out: dict[str, str] = {}
    if not raw:
        return out
    for pair in raw.split(EXTRA_PAIR_SEP):
        if not pair:
            continue
        key, sep, value = pair.partition(EXTRA_KV_SEP)
        if sep:
            out[key.strip()] = value.strip()
    return out


def format_extra(pairs: dict[str, str]) -> str:
    """Render key/value pairs for the `extra` column, in a stable order.

    Refuses to emit a separator inside a key or value: doing so would split
    the field somewhere the reader cannot detect, silently truncating a value
    and leaving a fragment behind.
    """
    for key, value in pairs.items():
        for text, what in ((key, "key"), (value, "value")):
            bad = [ch for ch in EXTRA_FORBIDDEN + EXTRA_KV_SEP if ch in text]
            if bad:
                raise ValueError(
                    f"{what} {text!r} contains {''.join(bad)!r}, which would break "
                    "the extra field apart"
                )
    return EXTRA_PAIR_SEP.join(f"{k}{EXTRA_KV_SEP}{pairs[k]}" for k in sorted(pairs))
