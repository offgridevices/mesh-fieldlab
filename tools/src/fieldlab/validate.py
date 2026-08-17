"""Check a logger CSV against the schema.

The point of this checker is to answer one question on the tailgate, before
anyone drives home: *is this file worth analysing?* It separates two kinds of
problem.

An **error** means the file cannot be trusted — a wrong header, an impossible
value, a hop count that contradicts itself, packets arriving over the
internet instead of the air. Analysis of a file with errors produces numbers
that look fine and mean nothing.

A **warning** means the file is readable but something is worth knowing — a
truncated last line from a brownout, a gap where the logger went quiet, a
link with too few packets to take a median from.
"""

from __future__ import annotations

import csv
import io
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from fieldlab import schema as S

ERROR = "error"
WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    level: str
    code: str
    message: str
    line: int | None = None

    def __str__(self) -> str:
        where = f"line {self.line}" if self.line is not None else "file"
        return f"{self.level.upper():7} {where:>10}  [{self.code}] {self.message}"


@dataclass
class Summary:
    """What the file contains, once it has been read."""

    path: str
    rows: int = 0
    by_row_type: Counter = field(default_factory=Counter)
    rx_node: int | None = None
    boot_count: str | None = None
    firmware: str | None = None
    preset: str | None = None
    schema_versions: set[int] = field(default_factory=set)
    first_uptime_ms: int | None = None
    last_uptime_ms: int | None = None
    clock_was_set: bool = False
    #: (tx_node, rx_node) -> count of deduplicated direct packets
    direct_links: Counter = field(default_factory=Counter)
    #: (tx_node, rx_node) -> count of deduplicated relayed packets
    relayed_links: Counter = field(default_factory=Counter)
    duplicate_rows: int = 0

    @property
    def duration_s(self) -> float:
        if self.first_uptime_ms is None or self.last_uptime_ms is None:
            return 0.0
        return (self.last_uptime_ms - self.first_uptime_ms) / 1000.0


@dataclass
class Result:
    summary: Summary
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors


class _Checker:
    def __init__(self, path: Path, text: str, min_packets: int = 0):
        self.path = path
        self.text = text
        self.min_packets = min_packets
        self.result = Result(summary=Summary(path=str(path)))
        self.issues = self.result.issues
        self.summary = self.result.summary
        self._seen_packets: set[tuple[int, int, int]] = set()
        self._last_uptime = -1
        self._last_dev_time = 0
        self._last_status_uptime: int | None = None

    # -- issue helpers ----------------------------------------------------

    def err(self, code: str, message: str, line: int | None = None) -> None:
        self.issues.append(Issue(ERROR, code, message, line))

    def warn(self, code: str, message: str, line: int | None = None) -> None:
        self.issues.append(Issue(WARNING, code, message, line))

    # -- entry point ------------------------------------------------------

    def run(self) -> Result:
        self._check_filename()
        if not self._check_bytes():
            return self.result

        lines = self.text.splitlines()
        if not lines:
            self.err("EMPTY", "file is empty")
            return self.result

        if not self._check_header(lines[0]):
            return self.result

        ends_cleanly = self.text.endswith(("\n", "\r\n", "\r"))
        rows = list(csv.reader(io.StringIO("\n".join(lines[1:]))))
        if not rows:
            self.err("NO_ROWS", "header present but no data rows; the node logged nothing")
            return self.result

        for offset, row in enumerate(rows):
            lineno = offset + 2  # 1-based, and the header is line 1
            is_last = offset == len(rows) - 1
            self._check_row(row, lineno, is_last=is_last, ends_cleanly=ends_cleanly)

        self._check_file_level()
        return self.result

    # -- whole-file checks ------------------------------------------------

    def _check_filename(self) -> None:
        m = re.match(S.FILENAME_PATTERN, self.path.name)
        if not m:
            self.warn(
                "FILENAME",
                f"{self.path.name!r} is not LOG_<SHORTNAME>_<YYYYMMDD>_<HHMM>.csv, "
                "nor the LOG_<SHORTNAME>_<BOOTCOUNT>.csv fallback; the stamp in the "
                "name is what keeps one power cycle to one file",
            )
            return

        # The fallback name is not a formatting nit. It is the only outward
        # sign that this node ran its whole session without ever learning the
        # time, which decides whether its rows can be lined up against another
        # node's at all.
        if m.group("boot") is not None:
            self.warn(
                "FILENAME_NO_CLOCK",
                f"{self.path.name!r} is the no-clock fallback name: this node never "
                "heard a packet carrying the time, so its rows can only be read "
                "relative to their own boot, not against another node's",
            )

    def _check_bytes(self) -> bool:
        if "\x00" in self.text:
            self.err(
                "CORRUPT_NUL",
                "file contains NUL bytes, which is what a card write interrupted "
                "by a power cut looks like",
            )
            return False
        return True

    def _check_header(self, header_line: str) -> bool:
        got = next(csv.reader([header_line]), [])
        got = [f.strip() for f in got]
        if got == list(S.COLUMN_NAMES):
            return True

        missing = [c for c in S.COLUMN_NAMES if c not in got]
        unexpected = [c for c in got if c not in S.COLUMN_NAMES]
        detail = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if unexpected:
            detail.append(f"unexpected {', '.join(unexpected)}")
        if not detail:
            detail.append("columns are in the wrong order")
        self.err("HEADER", f"header does not match schema {S.SCHEMA_VERSION}: {'; '.join(detail)}")
        return False

    # -- per-row checks ---------------------------------------------------

    def _check_row(self, row: list[str], lineno: int, *, is_last: bool, ends_cleanly: bool) -> None:
        if not row or (len(row) == 1 and not row[0].strip()):
            return  # blank line

        expected = len(S.COLUMN_NAMES)
        if len(row) != expected:
            if is_last and not ends_cleanly and len(row) < expected:
                self.warn(
                    "TRUNCATED",
                    f"last row has {len(row)} of {expected} columns and the file does not "
                    "end in a newline; the node most likely lost power mid-write. "
                    "Drop this row and keep the rest",
                    lineno,
                )
            else:
                self.err(
                    "COLUMN_COUNT",
                    f"row has {len(row)} columns, expected {expected}",
                    lineno,
                )
            return

        values = dict(zip(S.COLUMN_NAMES, (v.strip() for v in row)))

        row_type = values["row_type"]
        if row_type not in S.ROW_TYPES:
            self.err("ROW_TYPE", f"unknown row_type {row_type!r}", lineno)
            return

        nums = self._parse_numbers(values, lineno)
        if nums is None:
            return

        self.summary.rows += 1
        self.summary.by_row_type[row_type] += 1

        self._check_common(values, nums, lineno, row_type)
        if row_type == S.ROW_PKT:
            self._check_packet(values, nums, lineno)
        else:
            self._check_non_packet(values, nums, lineno, row_type)

    def _parse_numbers(self, values: dict[str, str], lineno: int) -> dict[str, float] | None:
        """Parse every numeric column, reporting each bad one before giving up."""
        out: dict[str, float] = {}
        ok = True
        for col in S.COLUMNS:
            if col.kind in ("enum", "extra"):
                continue
            raw = values[col.name]
            try:
                num = float(raw) if col.kind == "float" else int(raw, 10)
            except ValueError:
                self.err("NOT_A_NUMBER", f"{col.name}={raw!r} is not a number", lineno)
                ok = False
                continue
            # "nan" and "inf" parse happily as floats, and NaN compares false
            # against every bound, so without this a garbage reading would sail
            # through the range checks and poison a median further downstream.
            if col.kind == "float" and not math.isfinite(num):
                self.err(
                    "NOT_A_NUMBER",
                    f"{col.name}={raw!r} is not a finite number",
                    lineno,
                )
                ok = False
                continue
            if col.lo is not None and num < col.lo:
                self.err("RANGE", f"{col.name}={raw} is below the minimum {col.lo:g}", lineno)
                ok = False
            if col.hi is not None and num > col.hi:
                self.err("RANGE", f"{col.name}={raw} is above the maximum {col.hi:g}", lineno)
                ok = False
            out[col.name] = num
        return out if ok else None

    def _check_common(self, values: dict[str, str], nums: dict[str, float], lineno: int, row_type: str) -> None:
        ver = int(nums["schema_ver"])
        self.summary.schema_versions.add(ver)
        if ver not in S.SUPPORTED_SCHEMA_VERSIONS:
            self.err(
                "SCHEMA_VERSION",
                f"schema_ver={ver} is not one this tooling knows how to read "
                f"(supported: {sorted(S.SUPPORTED_SCHEMA_VERSIONS)})",
                lineno,
            )

        rx_node = int(nums["rx_node"])
        if self.summary.rx_node is None:
            self.summary.rx_node = rx_node
        elif rx_node != self.summary.rx_node:
            self.err(
                "RX_NODE_CHANGED",
                f"rx_node={rx_node} but this file started as {self.summary.rx_node}; "
                "one file belongs to one node",
                lineno,
            )

        uptime = int(nums["uptime_ms"])
        if uptime < self._last_uptime:
            self.err(
                "UPTIME_WENT_BACKWARDS",
                f"uptime_ms={uptime} is earlier than the previous row's {self._last_uptime}; "
                "a reboot must start a new file",
                lineno,
            )
        self._last_uptime = max(self._last_uptime, uptime)
        if self.summary.first_uptime_ms is None:
            self.summary.first_uptime_ms = uptime
        self.summary.last_uptime_ms = uptime

        dev_time = int(nums["dev_rx_time"])
        if dev_time:
            self.summary.clock_was_set = True
            if dev_time < S.EPOCH_FLOOR:
                self.err(
                    "CLOCK",
                    f"dev_rx_time={dev_time} predates 2020; the clock is wrong, not merely unset",
                    lineno,
                )
            elif dev_time < self._last_dev_time:
                self.warn(
                    "CLOCK_JUMP",
                    f"dev_rx_time={dev_time} is earlier than the previous row's "
                    f"{self._last_dev_time}; the mesh corrected the clock mid-run",
                    lineno,
                )
            self._last_dev_time = max(self._last_dev_time, dev_time)

    def _check_packet(self, values: dict[str, str], nums: dict[str, float], lineno: int) -> None:
        tx = int(nums["tx_node"])
        rx = int(nums["rx_node"])
        if tx == 0:
            self.err("TX_NODE", "tx_node=0 on a packet row; every packet has an originator", lineno)
        if tx == rx:
            self.err(
                "SELF_RECEPTION",
                f"tx_node equals rx_node ({tx}); a node cannot receive its own transmission "
                "over the air, so this row is locally originated",
                lineno,
            )
        if int(nums["pkt_id"]) == 0:
            self.warn("PKT_ID", "pkt_id=0; this row cannot be deduplicated against flood copies", lineno)

        if int(nums["via_mqtt"]) != 0:
            self.err(
                "VIA_MQTT",
                "packet arrived over MQTT rather than the air; an internet gateway is "
                "polluting the run and this row measures nothing about the radio path",
                lineno,
            )

        rssi = int(nums["rx_rssi_dbm"])
        if rssi == 0:
            self.warn(
                "RSSI_ZERO",
                "rx_rssi_dbm=0 means locally originated rather than received; filter this row out",
                lineno,
            )

        hop_start = int(nums["hop_start"])
        hop_limit = int(nums["hop_limit"])
        hops_used = int(nums["hops_used"])
        if hop_limit > hop_start:
            self.err(
                "HOPS",
                f"hop_limit={hop_limit} exceeds hop_start={hop_start}; a packet cannot gain hops",
                lineno,
            )
        elif hops_used != hop_start - hop_limit:
            self.err(
                "HOPS",
                f"hops_used={hops_used} but hop_start - hop_limit = {hop_start - hop_limit}",
                lineno,
            )

        if values["extra"]:
            self.warn("PKT_EXTRA", "extra is not empty on a packet row", lineno)

        key = (tx, int(nums["pkt_id"]), hops_used)
        if key in self._seen_packets:
            self.summary.duplicate_rows += 1
        else:
            self._seen_packets.add(key)
            bucket = self.summary.direct_links if hops_used == 0 else self.summary.relayed_links
            bucket[(tx, rx)] += 1

    def _check_non_packet(self, values: dict[str, str], nums: dict[str, float], lineno: int, row_type: str) -> None:
        for name in S.PACKET_ONLY:
            # tx_node carries the subject node on NODE rows; everywhere else
            # the packet columns must be zeroed so nothing reads as real.
            if int(nums[name]) != 0:
                self.warn(
                    "NONZERO_PACKET_FIELD",
                    f"{name}={values[name]} on a {row_type} row; packet columns must be 0 "
                    "outside packet rows",
                    lineno,
                )

        if row_type != S.ROW_NODE and int(nums["tx_node"]) != 0:
            self.warn(
                "NONZERO_PACKET_FIELD",
                f"tx_node={values['tx_node']} on a {row_type} row; expected 0",
                lineno,
            )
        if row_type == S.ROW_NODE and int(nums["tx_node"]) == 0:
            self.err("NODE_SUBJECT", "NODE row does not say which node it describes (tx_node=0)", lineno)

        raw_extra = values["extra"]
        pairs = S.parse_extra(raw_extra)
        spec = S.EXTRA_SPECS[row_type]

        # A fragment with no "=" means a separator ended up inside a value and
        # split it. The half before the separator was silently truncated, so
        # this has to be caught here rather than inferred from a missing key.
        fragments = [p for p in raw_extra.split(S.EXTRA_PAIR_SEP) if p and S.EXTRA_KV_SEP not in p]
        if fragments:
            self.err(
                "EXTRA_MALFORMED",
                f"extra contains {', '.join(repr(f) for f in fragments)} with no key; "
                "a separator inside a value has split the field and truncated it",
                lineno,
            )

        missing = sorted(spec.required - pairs.keys())
        if missing:
            self.err(
                "EXTRA_MISSING",
                f"{row_type} row is missing {', '.join(missing)} in extra",
                lineno,
            )
        unknown = sorted(pairs.keys() - spec.required - spec.optional)
        if unknown:
            self.warn(
                "EXTRA_UNKNOWN",
                f"{row_type} row has unrecognised keys in extra: {', '.join(unknown)}",
                lineno,
            )
        for k, v in pairs.items():
            if any(ch in v for ch in S.EXTRA_FORBIDDEN):
                self.err(
                    "EXTRA_SEPARATOR",
                    f"value of {k!r} contains a comma or semicolon, which breaks the field apart",
                    lineno,
                )

        if row_type == S.ROW_BOOT:
            self.summary.boot_count = pairs.get("boot")
            self.summary.firmware = pairs.get("fw")
            self.summary.preset = pairs.get("preset")
            self._check_boot_position(pairs, lineno)
            self._check_boot_selftest(pairs, lineno)
        elif row_type == S.ROW_STATUS:
            self._check_status(pairs, int(nums["uptime_ms"]), lineno)

    def _check_boot_position(self, pairs: dict[str, str], lineno: int) -> None:
        try:
            lat = float(pairs.get("lat", "nan"))
            lon = float(pairs.get("lon", "nan"))
        except ValueError:
            self.err("BOOT_POSITION", "lat/lon in the BOOT row are not numbers", lineno)
            return
        if lat != lat or lon != lon:  # NaN
            return
        if lat == 0.0 and lon == 0.0:
            self.err(
                "BOOT_POSITION",
                "fixed position is 0,0 — the node was deployed without its coordinate set, "
                "so nothing in this file can be tied to a location",
                lineno,
            )
        elif not (-90 <= lat <= 90 and -180 <= lon <= 180):
            self.err("BOOT_POSITION", f"lat/lon out of range: {lat}, {lon}", lineno)

    def _check_boot_selftest(self, pairs: dict[str, str], lineno: int) -> None:
        """Surface what the node already knew was wrong when it started.

        The self-test result is on screen for thirty seconds and then gone.
        Re-reporting it here means a file can be judged weeks later without
        anyone having to remember what they saw in a field.
        """
        failed = {
            "st_card":  (ERROR, "the card would not mount"),
            "st_write": (ERROR, "the card mounted but would not accept a test write"),
            "st_radio": (ERROR, "the radio did not answer on the serial link"),
            "st_pos":   (ERROR, "no fixed position was set, so these rows cannot be tied to a place"),
            "st_clock": (WARNING, "the clock was never set, so rows are only relative to boot"),
        }
        for key, (level, message) in failed.items():
            if pairs.get(key) == "0":
                issue = self.err if level == ERROR else self.warn
                issue("SELFTEST", f"the node reported at startup that {message}", lineno)

        heard = pairs.get("st_heard")
        if heard is not None and heard.isdigit() and int(heard) == 0:
            self.warn(
                "SELFTEST",
                "the node heard no other node during its startup listen; if that was "
                "still true an hour later this file has nothing in it",
                lineno,
            )

    def _check_status(self, pairs: dict[str, str], uptime: int, lineno: int) -> None:
        if pairs.get("sd_ok") == "0":
            self.err(
                "SD_FAILED",
                "the node reported its card as unhealthy at this point; rows after "
                "this may be missing",
                lineno,
            )
        if self._last_status_uptime is not None:
            gap = uptime - self._last_status_uptime
            if gap > S.STATUS_GAP_TOLERANCE_MS:
                self.warn(
                    "STATUS_GAP",
                    f"{gap / 1000:.0f} s between status rows, expected about "
                    f"{S.STATUS_INTERVAL_MS / 1000:.0f} s; the logger stalled and this run "
                    "has a hole in it",
                    lineno,
                )
        self._last_status_uptime = uptime

    # -- file-level checks -------------------------------------------------

    def _check_file_level(self) -> None:
        s = self.summary
        if s.by_row_type[S.ROW_BOOT] == 0:
            self.err("NO_BOOT", "no BOOT row; the file does not record how it was configured")
        elif s.by_row_type[S.ROW_BOOT] > 1:
            self.err(
                "MULTIPLE_BOOT",
                f"{s.by_row_type[S.ROW_BOOT]} BOOT rows; each boot must open its own file",
            )

        if s.by_row_type[S.ROW_PKT] == 0:
            self.warn("NO_PACKETS", "no packet rows; the node was running but heard nothing")

        if len(s.schema_versions) > 1:
            self.err(
                "MIXED_SCHEMA",
                f"rows claim more than one schema version: {sorted(s.schema_versions)}",
            )

        if s.by_row_type[S.ROW_PKT] and not s.clock_was_set:
            self.warn(
                "NO_ABSOLUTE_TIME",
                "the device clock was never set, so rows can only be placed relative to "
                "boot. Record the start time by hand or the run cannot be lined up "
                "against the other nodes",
            )

        # A brownout that skipped the status heartbeat entirely.
        expected_status = int(s.duration_s * 1000 // S.STATUS_INTERVAL_MS)
        if expected_status >= 3 and s.by_row_type[S.ROW_STATUS] < expected_status // 2:
            self.warn(
                "FEW_STATUS_ROWS",
                f"{s.by_row_type[S.ROW_STATUS]} status rows over {s.duration_s / 60:.0f} min, "
                f"expected roughly {expected_status}",
            )

        if self.min_packets:
            for (tx, rx), count in sorted(s.direct_links.items()):
                if count < self.min_packets:
                    self.warn(
                        "THIN_LINK",
                        f"{tx} -> {rx} has {count} direct packets, below the {self.min_packets} "
                        "asked for; a median over this few is not stable",
                    )


def validate_text(text: str, path: Path | str = "<string>", min_packets: int = 0) -> Result:
    """Validate CSV content already in memory."""
    return _Checker(Path(path), text, min_packets).run()


def unreadable(path: Path | str, reason: str) -> Result:
    """A stand-in result for a file that could not be opened at all.

    Returned rather than raised so that one unreadable card in a batch does
    not hide the verdict on the others — which is exactly the situation this
    tool exists to survive.
    """
    result = Result(summary=Summary(path=str(path)))
    result.issues.append(Issue(ERROR, "UNREADABLE", reason))
    return result


def validate_file(path: Path | str, min_packets: int = 0) -> Result:
    """Validate a log file on disk."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return unreadable(path, f"cannot read the file: {exc.strerror or exc}")

    decode_error: str | None = None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        # Fall back to a lossy decode so the rest of the file still produces
        # findings with line numbers attached, and report the bad bytes
        # separately. Checking for the replacement character after a lossy
        # decode would not do: a file may legitimately contain one.
        decode_error = f"byte {exc.start} is not valid text ({exc.reason})"
        text = raw.decode("utf-8", errors="replace")

    result = _Checker(path, text, min_packets).run()
    if decode_error:
        result.issues.append(
            Issue(ERROR, "NOT_TEXT", f"the card holds bytes that are not text: {decode_error}")
        )
    return result
