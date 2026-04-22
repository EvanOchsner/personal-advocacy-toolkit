#!/usr/bin/env python3
"""Render a markdown case-status dashboard.

Inputs:
  --intake   path to case-intake.yaml (claimant, jurisdiction, loss, etc.)
  --manifest path to evidence manifest.yaml (entries: list of {kind, ...})

Pulls:
  - deadlines from data/deadlines.yaml via scripts.intake.deadline_calc
  - packet validation status from packet-manifest.yaml files under the
    given --packet-dir (optional; skipped if unset or missing)

Output:
  Markdown to stdout by default, or to --out FILE.

This is reference material, not legal advice. Every run carries the
project-wide disclaimer at the top of the rendered dashboard.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Any

from scripts.intake._common import DISCLAIMER, data_dir, find_repo_root, load_yaml


DASHBOARD_DISCLAIMER = (
    "Reference material, not legal advice. Verify every deadline with "
    "counsel licensed in the relevant jurisdiction."
)


# --------------------------------------------------------------------------- #
# Manifest helpers
# --------------------------------------------------------------------------- #


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"entries": []}
    data = load_yaml(path)
    if "entries" not in data:
        data["entries"] = []
    return data


def _count_by_kind(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in entries or []:
        k = str(e.get("kind") or e.get("source_type") or "unknown")
        counts[k] = counts.get(k, 0) + 1
    return counts


# --------------------------------------------------------------------------- #
# Packet status
# --------------------------------------------------------------------------- #


def _find_packet_manifests(packet_dir: Path | None) -> list[Path]:
    if not packet_dir or not packet_dir.exists():
        return []
    out: list[Path] = []
    for name in ("packet-manifest.yaml", "packet-manifest.yml"):
        out.extend(packet_dir.rglob(name))
    return sorted(out)


def _packet_status(manifest_path: Path) -> dict[str, Any]:
    """Return a tiny summary: name + whether the manifest loads cleanly."""
    try:
        from scripts.packet._manifest import load_manifest as _load_pm  # type: ignore

        pm = _load_pm(manifest_path)
        return {
            "path": manifest_path,
            "name": pm.name,
            "authority": pm.authority.short_code,
            "validated": True,
            "error": None,
        }
    except Exception as exc:
        return {
            "path": manifest_path,
            "name": manifest_path.parent.name,
            "authority": None,
            "validated": False,
            "error": str(exc),
        }


# --------------------------------------------------------------------------- #
# Deadlines
# --------------------------------------------------------------------------- #


def _compute_deadlines(intake: dict[str, Any], root: Path | None) -> dict[str, Any] | None:
    situation = intake.get("situation_type")
    juris = (intake.get("jurisdiction") or {}).get("state")
    loss_date_str = ((intake.get("loss") or {}).get("date")) or ""
    if not situation or not juris or not loss_date_str:
        return None
    try:
        loss_date = date.fromisoformat(str(loss_date_str))
    except ValueError:
        return None

    from scripts.intake import deadline_calc as dc

    data = load_yaml(data_dir(root) / "deadlines.yaml")
    inputs = dc.ClockInputs(loss_date=loss_date)
    try:
        return dc.compute_deadlines(data, situation, str(juris), inputs)
    except dc.DeadlineError:
        return None


# --------------------------------------------------------------------------- #
# Dashboard rendering
# --------------------------------------------------------------------------- #


def render_dashboard(
    intake: dict[str, Any],
    manifest: dict[str, Any],
    deadlines: dict[str, Any] | None,
    packet_statuses: list[dict[str, Any]],
) -> str:
    lines: list[str] = []

    lines.append(f"> {DASHBOARD_DISCLAIMER}")
    lines.append("")
    lines.append("# Case dashboard")
    lines.append("")

    # Header
    caption = (
        intake.get("case_name")
        or intake.get("case_slug")
        or (intake.get("claimant") or {}).get("name")
        or "(unnamed case)"
    )
    lines.append("## Header")
    lines.append("")
    lines.append(f"- **Caption:** {caption}")
    lines.append(f"- **Situation type:** {intake.get('situation_type') or '(unset)'}")
    juris = intake.get("jurisdiction") or {}
    lines.append(f"- **Jurisdiction:** {juris.get('state') or '(unset)'}")
    loss = intake.get("loss") or {}
    lines.append(f"- **Loss date:** {loss.get('date') or '(unset)'}")
    if intake.get("synthetic"):
        lines.append("- **SYNTHETIC — NOT A REAL CASE**")
    lines.append("")

    # Evidence counts
    lines.append("## Evidence")
    lines.append("")
    counts = _count_by_kind(manifest.get("entries") or [])
    total = sum(counts.values())
    lines.append(f"Total entries in manifest: **{total}**")
    lines.append("")
    if counts:
        lines.append("| Source type | Count |")
        lines.append("|---|---|")
        for kind in sorted(counts):
            lines.append(f"| {kind} | {counts[kind]} |")
    else:
        lines.append("_No entries yet. Ingest evidence via `scripts/ingest/*`._")
    lines.append("")

    # Deadlines
    lines.append("## Deadlines")
    lines.append("")
    if deadlines is None:
        lines.append(
            "_Not enough information to compute deadlines. Set `situation_type`, "
            "`jurisdiction.state`, and `loss.date` in the intake._"
        )
    else:
        for w in deadlines.get("warnings", []) or []:
            lines.append(f"> WARNING: {w}")
        if not (deadlines.get("deadlines") or []):
            lines.append("_No deadlines returned for this (jurisdiction, situation)._")
        for d in deadlines.get("deadlines") or []:
            label = d.get("label") or "(unlabeled)"
            dl = d.get("deadline_date") or "(unknown)"
            kind = d.get("kind") or "?"
            verify = d.get("verify") or "VERIFY WITH COUNSEL"
            status = d.get("status") or "stub"
            flag = "" if status == "populated" else f" [{status.upper()}]"
            lines.append(f"- **{label}**{flag}: {dl} ({kind}) — {verify}")
    lines.append("")

    # Packet status
    lines.append("## Packets")
    lines.append("")
    if not packet_statuses:
        lines.append("_No packet-manifest.yaml found under the provided packet directory._")
    else:
        lines.append("| Packet | Authority | Validated | Notes |")
        lines.append("|---|---|---|---|")
        for p in packet_statuses:
            ok = "yes" if p["validated"] else "no"
            note = p["error"] or ""
            lines.append(
                f"| {p['name']} | {p['authority'] or '-'} | {ok} | {note} |"
            )
    lines.append("")

    # Pending / Done heuristics
    lines.append("## Pending / Done")
    lines.append("")
    done: list[str] = []
    pending: list[str] = []

    if total > 0:
        done.append(f"Evidence manifest populated ({total} entries).")
    else:
        pending.append("No evidence ingested yet.")

    if packet_statuses and any(p["validated"] for p in packet_statuses):
        done.append(
            f"{sum(1 for p in packet_statuses if p['validated'])} packet manifest(s) validated."
        )
    else:
        pending.append("No validated complaint packet yet.")

    if deadlines and (deadlines.get("deadlines") or []):
        done.append("Deadlines computed — review the table above.")
    else:
        pending.append("Deadlines not computed (missing situation / jurisdiction / loss date).")

    lines.append("### Done")
    if done:
        for d in done:
            lines.append(f"- [x] {d}")
    else:
        lines.append("- _(nothing yet)_")
    lines.append("")
    lines.append("### Pending")
    if pending:
        for d in pending:
            lines.append(f"- [ ] {d}")
    else:
        lines.append("- _(nothing pending)_")
    lines.append("")

    lines.append(f"-- {DASHBOARD_DISCLAIMER}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--intake", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True, help="evidence manifest.yaml")
    p.add_argument(
        "--packet-dir",
        type=Path,
        default=None,
        help="directory to scan for packet-manifest.yaml files",
    )
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--root", type=Path, default=None)
    args = p.parse_args(argv)

    if not args.intake.exists():
        print(f"error: intake not found: {args.intake}", file=sys.stderr)
        return 2

    intake = load_yaml(args.intake)
    manifest = _load_manifest(args.manifest)
    deadlines = _compute_deadlines(intake, args.root)
    packet_manifests = _find_packet_manifests(args.packet_dir)
    packet_statuses = [_packet_status(pm) for pm in packet_manifests]

    md = render_dashboard(intake, manifest, deadlines, packet_statuses)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md, encoding="utf-8")
    else:
        sys.stdout.write(md)

    # Nudge: echo the global disclaimer on stderr so it's visible even
    # when stdout is redirected.
    print(DISCLAIMER, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
