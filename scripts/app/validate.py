"""CLI: validate a case directory's entities.yaml + events.yaml.

Usage:
    uv run python -m scripts.app.validate --case-dir path/to/case

Exits 0 on success with a one-line summary; exits 2 with a human-
readable CaseMapError on failure. Used in CI against
examples/maryland-mustang/ to catch schema drift early.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.intake._common import DISCLAIMER, load_yaml

from scripts.app._aggregate import build_timeline
from scripts.app._loaders import load_case_map
from scripts.app._schema import CaseMapError


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--case-dir", type=Path, required=True)
    p.add_argument(
        "--correspondence-manifest",
        type=Path,
        default=None,
        help="Optional correspondence-manifest.yaml for timeline aggregation.",
    )
    p.add_argument(
        "--show-timeline",
        action="store_true",
        help="Print the aggregated timeline (without correspondence / deadlines "
        "unless those sources are supplied) as YYYY-MM-DD title pairs.",
    )
    args = p.parse_args(argv)

    try:
        loaded = load_case_map(args.case_dir)
    except CaseMapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    corresp = None
    if args.correspondence_manifest and args.correspondence_manifest.is_file():
        corresp = load_yaml(args.correspondence_manifest)

    try:
        markers = build_timeline(loaded, correspondence_manifest=corresp, deadlines=None)
    except CaseMapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        f"OK  {args.case_dir}: "
        f"{len(loaded.entities)} entities, "
        f"{len(loaded.events)} events, "
        f"{len(markers)} timeline markers."
    )
    if args.show_timeline:
        for m in markers:
            print(f"  {m.date}  [{m.kind}]  {m.title}")

    print(DISCLAIMER, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
