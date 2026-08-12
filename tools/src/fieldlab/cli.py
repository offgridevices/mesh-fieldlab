"""Command line entry point: `validate-csv <file-or-directory>...`

Written to be run on a laptop in a field, on a card that was just pulled out
of a node, by someone who wants a yes or a no before they pack up.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fieldlab import schema as S
from fieldlab.validate import Result, validate_file

EXIT_OK = 0
EXIT_PROBLEMS = 1
EXIT_USAGE = 2


def collect_paths(inputs: list[str]) -> list[Path]:
    paths: list[Path] = []
    for raw in inputs:
        p = Path(raw)
        if p.is_dir():
            paths.extend(sorted(p.glob("*.csv")))
        else:
            paths.append(p)
    return paths


def print_report(result: Result, *, quiet: bool) -> None:
    s = result.summary
    verdict = "OK" if result.ok else "PROBLEMS"
    print(f"\n{s.path}  [{verdict}]")

    if s.rows:
        counts = "  ".join(f"{t}={s.by_row_type[t]}" for t in S.ROW_TYPES if s.by_row_type[t])
        print(f"  node {s.rx_node}   boot {s.boot_count or '?'}   "
              f"{s.duration_s / 60:.0f} min   {s.rows} rows   {counts}")
        if s.firmware or s.preset:
            print(f"  firmware {s.firmware or '?'}   preset {s.preset or '?'}")
        if s.duplicate_rows:
            print(f"  {s.duplicate_rows} duplicate flood copies (expected; deduplicated in analysis)")

    if s.direct_links:
        print("  direct links (tx -> rx: packets):")
        for (tx, rx), count in sorted(s.direct_links.items(), key=lambda kv: -kv[1]):
            print(f"    {tx} -> {rx}: {count}")
    elif s.by_row_type[S.ROW_PKT]:
        print("  no direct receptions — every packet arrived via a relay")

    if s.relayed_links:
        total = sum(s.relayed_links.values())
        print(f"  {total} relayed packets across {len(s.relayed_links)} links "
              "(routing behaviour only, not a path measurement)")

    shown = result.issues if not quiet else result.errors
    for issue in shown:
        print(f"  {issue}")

    if quiet and result.warnings:
        print(f"  ({len(result.warnings)} warnings hidden; run without --quiet to see them)")


def as_dict(result: Result) -> dict:
    s = result.summary
    return {
        "path": s.path,
        "ok": result.ok,
        "rows": s.rows,
        "row_types": dict(s.by_row_type),
        "rx_node": s.rx_node,
        "boot_count": s.boot_count,
        "firmware": s.firmware,
        "preset": s.preset,
        "duration_s": round(s.duration_s, 1),
        "clock_was_set": s.clock_was_set,
        "duplicate_rows": s.duplicate_rows,
        "direct_links": {f"{tx}->{rx}": n for (tx, rx), n in sorted(s.direct_links.items())},
        "relayed_links": {f"{tx}->{rx}": n for (tx, rx), n in sorted(s.relayed_links.items())},
        "issues": [
            {"level": i.level, "code": i.code, "line": i.line, "message": i.message}
            for i in result.issues
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="validate-csv",
        description=(
            "Check logger CSV files against the schema. Errors mean the file cannot "
            "be trusted; warnings mean it is readable but something is worth knowing."
        ),
    )
    p.add_argument("paths", nargs="+", metavar="PATH", help="CSV files, or directories of them")
    p.add_argument(
        "--min-packets",
        type=int,
        default=0,
        metavar="N",
        help="warn about any direct link with fewer than N packets (100 is the usual target)",
    )
    p.add_argument("--strict", action="store_true", help="treat warnings as failures")
    p.add_argument("--quiet", action="store_true", help="show errors only")
    p.add_argument("--json", action="store_true", help="emit machine-readable output")
    p.add_argument(
        "--schema",
        action="store_true",
        help="print the current header line and exit; use this to check firmware output",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.schema:
        print(S.HEADER)
        return EXIT_OK

    paths = collect_paths(args.paths)
    if not paths:
        print("no CSV files found in the given paths", file=sys.stderr)
        return EXIT_USAGE

    results: list[Result] = []
    for path in paths:
        # A file that cannot be read comes back as a failing result rather than
        # aborting the run: four cards in a folder and one of them dead should
        # still tell you about the other three.
        results.append(validate_file(path, min_packets=args.min_packets))

    if args.json:
        print(json.dumps([as_dict(r) for r in results], indent=2))
    else:
        for result in results:
            print_report(result, quiet=args.quiet)

        n_err = sum(len(r.errors) for r in results)
        n_warn = sum(len(r.warnings) for r in results)
        good = sum(1 for r in results if r.ok)
        print(
            f"\n{good}/{len(results)} files usable   "
            f"{n_err} {'error' if n_err == 1 else 'errors'}   "
            f"{n_warn} {'warning' if n_warn == 1 else 'warnings'}"
        )

    failed = any(not r.ok for r in results)
    if args.strict:
        failed = failed or any(r.warnings for r in results)
    return EXIT_PROBLEMS if failed else EXIT_OK


def synth_main(argv: list[str] | None = None) -> int:
    """`synth-log`: write synthetic log files for developing the analysis tools."""
    from fieldlab.synth import SynthConfig, filename_for, synth_log

    p = argparse.ArgumentParser(
        prog="synth-log",
        description=(
            "Write synthetic log files that obey the schema. The numbers are made "
            "up; this exists so the analysis tooling can be built and tested before "
            "there is hardware to record anything real."
        ),
    )
    p.add_argument("outdir", help="directory to write the files into")
    p.add_argument("--nodes", type=int, default=4, help="how many nodes in the mesh")
    p.add_argument("--minutes", type=int, default=60, help="length of the session")
    p.add_argument("--interval", type=int, default=20, help="seconds between packets")
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args(argv)

    if args.nodes < 2:
        print("a mesh needs at least two nodes", file=sys.stderr)
        return EXIT_USAGE
    if args.interval < 1:
        print("--interval must be at least one second", file=sys.stderr)
        return EXIT_USAGE
    if args.minutes < 1:
        print("--minutes must be at least one minute", file=sys.stderr)
        return EXIT_USAGE
    if args.interval > args.minutes * 60:
        print("--interval is longer than the whole session; no packets would be sent", file=sys.stderr)
        return EXIT_USAGE

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    node_ids = [1001 + i for i in range(args.nodes)]

    for index, node in enumerate(node_ids):
        config = SynthConfig(
            rx_node=node,
            peers=tuple(n for n in node_ids if n != node),
            short_name=f"N{index + 1}",
            boot_count=1,
            duration_s=args.minutes * 60,
            interval_s=args.interval,
            lat=39.8283 + 0.004 * index,
            lon=-98.5795 + 0.005 * index,
            seed=args.seed + index,
        )
        path = outdir / filename_for(config)
        path.write_text(synth_log(config))
        print(f"wrote {path}")

    print("\nThese are invented numbers, not measurements.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
