"""Command line interface for the lease expiry calendar."""
from __future__ import annotations

import argparse
import sys
from datetime import date

from . import core


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lease_calendar", description="Critical dates from a lease register.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("list", "print the critical dates"), ("ics", "write an .ics calendar file")):
        p = sub.add_parser(name, help=text)
        p.add_argument("register", help="lease register CSV")
        p.add_argument("--today", help="reference date YYYY-MM-DD (default: today)")
        p.add_argument("--within", type=int, help="only dates within this many days")
        p.add_argument("--include-past", action="store_true", help="also include dates that have passed")
        if name == "ics":
            p.add_argument("--out", default="lease-dates.ics", help="output file (default lease-dates.ics)")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the tool. Returns the exit code."""
    args = build_parser().parse_args(argv)
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
        events = core.upcoming(core.read_register(args.register), today, args.within, args.include_past)
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if args.command == "ics":
        with open(args.out, "w", encoding="utf-8", newline="") as handle:
            handle.write(core.to_ics(events))
        print(f"Wrote {len(events)} events to {args.out}")
        return 0
    print(f"{'Date':<11} {'In days':>7}  {'Lease':<12} {'Tenant':<20} Event")
    for e in events:
        days = e.days_from(today)
        mark = "  <- within 30 days" if 0 <= days <= 30 else ""
        print(f"{e.when.isoformat():<11} {days:>7}  {e.lease:<12} {e.tenant:<20} {e.kind}{mark}")
    print(f"\n{len(events)} dates")
    return 0
