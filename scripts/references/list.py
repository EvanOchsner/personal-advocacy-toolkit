"""List trusted reference docs in a case folder.

Reads ``<case>/references/.references-manifest.yaml`` and prints a
tabular view, or returns JSON for downstream tooling.

CLI:

    uv run python -m scripts.references.list [--case-root .]
    uv run python -m scripts.references.list --format json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.references import _manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="List ingested trusted reference docs.",
    )
    ap.add_argument(
        "--case-root",
        type=Path,
        default=Path.cwd(),
        help="Case-folder root (default: cwd).",
    )
    ap.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format.",
    )
    ap.add_argument(
        "--kind",
        type=str,
        default=None,
        help="Filter to a single kind (statute, regulation, official-policy, ...).",
    )
    args = ap.parse_args(argv)

    case_root: Path = args.case_root.resolve()
    manifest = case_root / "references" / ".references-manifest.yaml"
    if not manifest.exists():
        print(
            f"no references manifest at {manifest}; "
            "run scripts.references.ingest first.",
            file=sys.stderr,
        )
        return 2

    entries = _manifest.list_entries(manifest)
    if args.kind:
        entries = [e for e in entries if e.get("kind") == args.kind]

    if args.format == "json":
        print(json.dumps({"entries": entries}, indent=2, ensure_ascii=False))
        return 0

    if not entries:
        print("(no entries)")
        return 0

    print(f"{'ID':<18} {'KIND':<18} {'JURIS':<8} {'CITATION':<32} TITLE")
    print("-" * 120)
    for e in entries:
        sid = (e.get("source_id") or "")[:16]
        kind = e.get("kind") or ""
        juris = e.get("jurisdiction") or ""
        cit = (e.get("citation") or "")[:30]
        title = (e.get("title") or "")[:60]
        print(f"{sid:<18} {kind:<18} {juris:<8} {cit:<32} {title}")
    print()
    print(f"({len(entries)} entries; manifest: {manifest.relative_to(case_root)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
