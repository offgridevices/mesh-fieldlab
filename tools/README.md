# tools

Python tooling for cairn-fieldlab packet logs. Managed with [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run pytest
```

## validate-csv

Checks a log file against the schema and prints what it contains. Run it on
the card before leaving a test site.

```bash
uv run validate-csv /Volumes/LOGGER/LOG_N1_7.csv
uv run validate-csv ./data/raw/2026-08-20/ --min-packets 100
uv run validate-csv --schema            # the exact header the firmware must write
```

**Errors** mean the file cannot be trusted: a wrong header, an impossible
value, a hop count that contradicts itself, packets that arrived over the
internet rather than the air. Analysing a file with errors produces numbers
that look reasonable and mean nothing.

**Warnings** mean the file is readable but something is worth knowing: a
truncated last row from a power cut, a gap where the logger went quiet, a
link with too few packets to take a median from.

Exit code is 0 when every file is usable and 1 otherwise. `--strict` makes
warnings count as failure too; `--json` gives machine-readable output.

## analyze-logs

Reduces a session to its links.

```bash
uv run analyze-logs ./data/raw/2026-08-20/
uv run analyze-logs ./data/raw/2026-08-20/ --json
```

Four nodes make six pairs, and each pair is two directed links, because radio
paths are not symmetric. The output is those twelve numbers and the confidence
you can place in each.

Three decisions do most of the work, and getting any of them wrong produces a
result that looks reasonable and means nothing:

- **Only direct receptions measure a path.** A relayed packet tells you about
  its last hop, not about the pair of nodes at its ends.
- **Flood copies are removed first.** The same packet reaches a node several
  times by different routes; counting them inflates every figure in proportion
  to how well the mesh was working.
- **Medians, not means.** A single multipath null drags an average somewhere no
  reading ever was.

It refuses files the checker rejected, reports nodes configured differently
from each other, and flags links with too few packets to take a median from.
`--force` overrides the first of those, and the numbers cannot be trusted if
you use it.

The `share` column is the fraction of a sender's packets that reached *anyone*
which also reached that receiver directly. It is not an absolute delivery
rate — nothing in these files records what was transmitted, only what arrived.

## synth-log

Writes a synthetic session so the analysis can be built and tested before
there is hardware.

```bash
uv run synth-log /tmp/session --minutes 180
```

It models **one shared mesh**, not four independent nodes: each transmission
is a single event with one packet id, and every other node either hears it
directly, hears a relayed copy, or misses it. That is what makes
deduplication, delivery share and asymmetry testable at all.

Signal strength falls with distance and is perturbed per packet and per
direction, so links come out asymmetric and the medians differ by pair —
the properties the analysis is supposed to recover.

The numbers are invented. Never treat them as a measurement.

## The schema

`src/fieldlab/schema.py` is the single source of truth for the file format.
The firmware writes what it describes and every tool reads through it.
Changing a column, a range, or a required key means bumping the schema
version there and recording the change in
[`docs/packet-logger-design.md`](../docs/packet-logger-design.md).
