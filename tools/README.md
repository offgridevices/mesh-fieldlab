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

## The schema

`src/fieldlab/schema.py` is the single source of truth for the file format.
The firmware writes what it describes and every tool reads through it.
Changing a column, a range, or a required key means bumping the schema
version there and recording the change in
[`docs/packet-logger-design.md`](../docs/packet-logger-design.md).
