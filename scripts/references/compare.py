"""Side-by-side comparison of two ingested copies of the same reference doc.

When the user has a doc from two paths (e.g., a user-supplied PDF and a
fresh fetch from the agency's site), this tool surfaces:

  - sha256 equality / inequality
  - char-count and line-count deltas
  - a unified diff of the readable plaintext
  - shared metadata (citation, kind, jurisdiction)

Output is markdown by default so it can be dropped into
``notes/references/<date>_<slug>_compare.md`` and read by a human.
JSON output is also available for scripted callers.

CLI:

    uv run python -m scripts.references.compare \\
        --refs references/structured/md-ins-27-303.json \\
              references/structured/md-ins-27-303-2.json
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any


def _load_sidecar(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_readable(case_root: Path, sidecar: dict[str, Any]) -> str:
    rel = sidecar.get("readable_path")
    if not rel:
        return ""
    p = case_root / rel
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def compare(
    sidecar_a: dict[str, Any],
    sidecar_b: dict[str, Any],
    *,
    text_a: str,
    text_b: str,
) -> dict[str, Any]:
    """Build a comparison record."""
    a_sha = sidecar_a.get("source_sha256")
    b_sha = sidecar_b.get("source_sha256")
    diff_lines: list[str] = []
    if text_a != text_b:
        diff_lines = list(
            difflib.unified_diff(
                text_a.splitlines(),
                text_b.splitlines(),
                fromfile=sidecar_a.get("readable_path") or "a",
                tofile=sidecar_b.get("readable_path") or "b",
                lineterm="",
                n=2,
            )
        )

    shared_citation = sidecar_a.get("citation") == sidecar_b.get("citation")
    shared_kind = sidecar_a.get("kind") == sidecar_b.get("kind")
    shared_juris = sidecar_a.get("jurisdiction") == sidecar_b.get("jurisdiction")

    return {
        "a": {
            "source_id": sidecar_a.get("source_id"),
            "source_sha256": a_sha,
            "source_origin": sidecar_a.get("source_origin"),
            "source_url": sidecar_a.get("source_url"),
            "fetched_at": sidecar_a.get("fetched_at"),
            "readable_path": sidecar_a.get("readable_path"),
            "char_count": len(text_a),
        },
        "b": {
            "source_id": sidecar_b.get("source_id"),
            "source_sha256": b_sha,
            "source_origin": sidecar_b.get("source_origin"),
            "source_url": sidecar_b.get("source_url"),
            "fetched_at": sidecar_b.get("fetched_at"),
            "readable_path": sidecar_b.get("readable_path"),
            "char_count": len(text_b),
        },
        "raw_sha256_equal": a_sha == b_sha,
        "readable_text_equal": text_a == text_b,
        "shared_citation": shared_citation,
        "shared_kind": shared_kind,
        "shared_jurisdiction": shared_juris,
        "char_delta": len(text_b) - len(text_a),
        "diff_lines": diff_lines[:500],  # cap to keep notes readable
        "diff_truncated": len(diff_lines) > 500,
    }


def render_markdown(report: dict[str, Any]) -> str:
    a = report["a"]
    b = report["b"]
    lines: list[str] = []
    lines.append("# Reference-doc cross-source comparison")
    lines.append("")
    lines.append("This is reference information, not legal advice.")
    lines.append("")
    lines.append("| Field | A | B |")
    lines.append("|---|---|---|")
    lines.append(f"| source_id | `{a['source_id']}` | `{b['source_id']}` |")
    lines.append(f"| origin | {a['source_origin']} | {b['source_origin']} |")
    lines.append(f"| url | {a['source_url'] or '(local)'} | {b['source_url'] or '(local)'} |")
    lines.append(f"| fetched_at | {a['fetched_at']} | {b['fetched_at']} |")
    lines.append(f"| char_count | {a['char_count']} | {b['char_count']} |")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    if report["raw_sha256_equal"]:
        lines.append("- **Raw bytes are byte-identical** (sha256 match).")
    else:
        lines.append("- **Raw bytes differ** — the two copies are not byte-identical.")
    if report["readable_text_equal"]:
        lines.append("- Extracted plaintext is identical.")
    else:
        lines.append(
            f"- Extracted plaintext differs by {report['char_delta']:+d} characters."
        )
    if not report["shared_citation"]:
        lines.append("- ⚠️ The two sidecars carry **different citations**.")
    if not report["shared_kind"]:
        lines.append("- ⚠️ The two sidecars carry **different kinds**.")
    if not report["shared_jurisdiction"]:
        lines.append("- ⚠️ The two sidecars carry **different jurisdictions**.")
    lines.append("")
    if report["diff_lines"]:
        lines.append("## Diff (unified, truncated)")
        lines.append("")
        lines.append("```diff")
        for ln in report["diff_lines"]:
            lines.append(ln)
        lines.append("```")
        if report["diff_truncated"]:
            lines.append("")
            lines.append("_(diff truncated to first 500 lines.)_")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Side-by-side compare of two ingested reference docs.",
    )
    ap.add_argument(
        "--refs",
        nargs=2,
        type=Path,
        required=True,
        metavar=("A.json", "B.json"),
        help="Two sidecar JSON paths from references/structured/.",
    )
    ap.add_argument(
        "--case-root",
        type=Path,
        default=Path.cwd(),
        help="Case-folder root (default: cwd).",
    )
    ap.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format.",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write the report to this file instead of stdout.",
    )
    args = ap.parse_args(argv)

    case_root: Path = args.case_root.resolve()
    a_path, b_path = args.refs
    if not a_path.is_file() or not b_path.is_file():
        print("error: both --refs paths must exist", file=sys.stderr)
        return 2
    sidecar_a = _load_sidecar(a_path)
    sidecar_b = _load_sidecar(b_path)
    text_a = _load_readable(case_root, sidecar_a)
    text_b = _load_readable(case_root, sidecar_b)
    report = compare(sidecar_a, sidecar_b, text_a=text_a, text_b=text_b)
    payload = (
        json.dumps(report, indent=2, ensure_ascii=False)
        if args.format == "json"
        else render_markdown(report)
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(payload)
        if not payload.endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
