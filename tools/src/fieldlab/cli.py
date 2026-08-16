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


def analyze_main(argv: list[str] | None = None) -> int:
    """`analyze-logs`: reduce a folder of cards to per-link measurements."""
    from fieldlab.analyze import asymmetry, link_stats, load_directory

    p = argparse.ArgumentParser(
        prog="analyze-logs",
        description=(
            "Reduce a session to its links. Only direct receptions count — a "
            "relayed packet measures the last hop, not the pair of nodes at its "
            "ends. Flood copies are removed first, and every figure is a median."
        ),
    )
    p.add_argument("directory", help="folder of log files from one session")
    p.add_argument("--min-packets", type=int, default=100, metavar="N",
                   help="mark links with fewer than N direct packets as thin (default 100)")
    p.add_argument("--force", action="store_true",
                   help="analyse files the checker rejected; the numbers cannot be trusted")
    p.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = p.parse_args(argv)

    session = load_directory(args.directory, force=args.force)
    if not session.files:
        print(f"no usable log files in {args.directory}", file=sys.stderr)
        for path, why in session.skipped:
            print(f"  skipped {path}: {why}", file=sys.stderr)
        return EXIT_USAGE

    links = link_stats(session)

    if args.json:
        print(json.dumps({
            "files": session.files,
            "skipped": [{"path": p2, "reason": r} for p2, r in session.skipped],
            "nodes": {str(n.node): {
                "name": n.name, "lat": n.lat, "lon": n.lon, "alt": n.alt,
                "preset": n.preset, "region": n.region, "boot": n.boot,
                "antenna": n.antenna,
            } for n in session.nodes.values()},
            "config_mismatches": session.config_mismatches(),
            "duplicates_dropped": session.duplicates_dropped,
            "links": [{
                "tx": s.tx, "rx": s.rx, "packets": s.packets,
                "rssi_median": s.rssi_median, "rssi_p10": s.rssi_p10, "rssi_p90": s.rssi_p90,
                "snr_median": round(s.snr_median, 2),
                "snr_p10": round(s.snr_p10, 2), "snr_p90": round(s.snr_p90, 2),
                "relayed_packets": s.relayed_packets,
                "heard_fraction": s.heard_fraction,
                "distance_m": s.distance_m,
                "elevation_diff_m": s.elevation_diff_m,
            } for s in links],
        }, indent=2))
        return EXIT_OK

    print(f"\n{len(session.files)} files   {len(session.nodes)} nodes   "
          f"{len(session.receptions)} receptions   "
          f"{session.duplicates_dropped} flood copies removed")

    for path, why in session.skipped:
        print(f"  SKIPPED {path}\n          {why}")

    for problem in session.config_mismatches():
        print(f"  MISMATCH  {problem}")

    missing = [n for n in session.nodes.values() if not n.has_position]
    for n in missing:
        print(f"  NO POSITION  node {n.node} never had its coordinate set; "
              "its distances cannot be computed")

    if not links:
        print("\nno direct receptions — every packet arrived via a relay, so "
              "nothing here measures a single radio path")
        return EXIT_PROBLEMS

    print("\nDIRECT LINKS")
    print(f"  {'from':>10} {'to':>10} {'pkts':>5} {'RSSI':>7} {'p10..p90':>13} "
          f"{'SNR':>6} {'share':>6} {'dist':>8}")
    for s in links:
        thin = "  thin" if s.packets < args.min_packets else ""
        distance = f"{s.distance_m:7.0f}m" if s.distance_m is not None else "      --"
        share = f"{s.heard_fraction * 100:5.0f}%" if s.heard_fraction is not None else "   --"
        print(f"  {s.tx:>10} {s.rx:>10} {s.packets:>5} "
              f"{s.rssi_median:>6.0f}  {s.rssi_p10:>5.0f}..{s.rssi_p90:<5.0f} "
              f"{s.snr_median:>5.1f} {share} {distance}{thin}")

    pairs = asymmetry(links)
    if pairs:
        print("\nASYMMETRY  (the two directions of one pair, in dB)")
        for a, b, diff, worse in pairs:
            note = "  <- worth knowing" if diff >= 6 else ""
            print(f"  {a} <-> {b}: {diff:4.1f} dB apart, worse direction {worse:.0f} dBm{note}")

    thin = [s for s in links if s.packets < args.min_packets]
    if thin:
        print(f"\n{len(thin)} of {len(links)} links have fewer than {args.min_packets} "
              "direct packets. Medians over that few are not stable.")

    print("\nOnly direct receptions are counted. 'share' is the fraction of this "
          "sender's packets\nthat reached anyone which also reached this receiver "
          "directly — not an absolute\ndelivery rate, since nothing here records "
          "what was transmitted.")
    return EXIT_OK


def synth_main(argv: list[str] | None = None) -> int:
    """`synth-log`: write synthetic log files for developing the analysis tools."""
    from fieldlab.synth import MeshConfig, synth_session

    p = argparse.ArgumentParser(
        prog="synth-log",
        description=(
            "Write a synthetic session: one shared mesh, so the same transmission "
            "appears in several nodes' files exactly as it would in the field. The "
            "numbers are made up; this exists so the analysis can be built and "
            "tested before there is hardware to record anything real."
        ),
    )
    p.add_argument("outdir", help="directory to write the files into")
    p.add_argument("--nodes", type=int, default=4, help="how many nodes in the mesh")
    p.add_argument("--minutes", type=int, default=60, help="length of the session")
    p.add_argument("--interval", type=int, default=20, help="seconds between transmissions")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--no-clock", action="store_true",
                   help="simulate radios whose clock was never set")
    args = p.parse_args(argv)

    config = MeshConfig(
        node_count=args.nodes,
        duration_s=args.minutes * 60,
        interval_s=args.interval,
        seed=args.seed,
        set_clock=not args.no_clock,
    )

    try:
        files = synth_session(config)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return EXIT_USAGE

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    for name, text in sorted(files.items()):
        path = outdir / name
        path.write_text(text)
        print(f"wrote {path}")

    print("\nThese are invented numbers, not measurements.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
