#!/usr/bin/env python3
"""Compute SOL / notice deadlines for (situation, jurisdiction, loss_date).

Reads data/deadlines.yaml. Every output line includes a
"verify with counsel" disclaimer. This tool provides reference dates
only; it is not legal advice.

Usage:
    python -m scripts.intake.deadline_calc \\
        --situation insurance_dispute \\
        --jurisdiction MD \\
        --loss-date 2025-03-15

    # Provide extra reference dates (denial, last_act, notice-of-loss):
    python -m scripts.intake.deadline_calc \\
        --situation insurance_dispute --jurisdiction MD \\
        --loss-date 2025-03-15 \\
        --notice-of-loss 2025-03-16 \\
        --denial-date 2025-05-09 \\
        --last-act 2025-06-24

If a deadline's clock_starts refers to a date the user did not provide
(e.g., --denial-date), we fall back to loss_date and flag it. Calendar
arithmetic handles month/year rollover (Jan 31 + 1 month -> Feb 28/29).
"""
from __future__ import annotations

import argparse
import calendar
import json
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from scripts.intake._common import DISCLAIMER, data_dir, load_yaml


VERIFY_TAG = "VERIFY WITH COUNSEL"


class DeadlineError(Exception):
    pass


@dataclass
class ClockInputs:
    loss_date: date
    notice_of_loss: date | None = None
    denial_date: date | None = None
    last_act: date | None = None
    custom: date | None = None

    def pick(self, clock: str) -> tuple[date, bool]:
        """Return (date, used_fallback). Fallback = loss_date when the
        requested clock field is absent."""
        m = {
            "loss_date": self.loss_date,
            "notice_of_loss": self.notice_of_loss,
            "denial_date": self.denial_date,
            "last_act": self.last_act,
            "custom": self.custom,
        }
        val = m.get(clock)
        if val is not None:
            return val, False
        return self.loss_date, True


def add_duration(start: date, duration: dict[str, int]) -> date:
    """Add a duration dict to a date. Supports days / months / years.

    Calendar-aware: Jan 31 + 1 month -> Feb 28/29. Leap-year safe.
    """
    if not duration or not isinstance(duration, dict):
        raise DeadlineError(f"invalid duration: {duration!r}")
    keys = {k for k, v in duration.items() if v}
    if len(keys) != 1:
        raise DeadlineError(
            f"duration must have exactly one of days/months/years, got {duration!r}"
        )
    (unit,) = keys
    n = int(duration[unit])
    if unit == "days":
        return start + timedelta(days=n)
    if unit == "months":
        month_total = start.month - 1 + n
        y = start.year + month_total // 12
        m = month_total % 12 + 1
        last_day = calendar.monthrange(y, m)[1]
        d = min(start.day, last_day)
        return date(y, m, d)
    if unit == "years":
        y = start.year + n
        try:
            return start.replace(year=y)
        except ValueError:
            # Feb 29 in a non-leap target year.
            return date(y, 2, 28)
    raise DeadlineError(f"unknown duration unit: {unit!r}")


def compute_deadlines(
    deadlines_yaml: dict[str, Any],
    situation: str,
    jurisdiction: str,
    inputs: ClockInputs,
) -> dict[str, Any]:
    jurisdictions = deadlines_yaml.get("jurisdictions") or {}
    juris_key = (jurisdiction or "").upper()

    warnings: list[str] = []
    entries: list[dict[str, Any]] = []

    juris_entry = jurisdictions.get(juris_key)
    if juris_entry is None:
        warnings.append(
            f"No deadlines entry for jurisdiction {juris_key!r}. "
            "Returning empty list. Contribute to data/deadlines.yaml."
        )
        return {
            "disclaimer": deadlines_yaml.get("disclaimer") or DISCLAIMER,
            "situation": situation,
            "jurisdiction": juris_key or None,
            "loss_date": inputs.loss_date.isoformat(),
            "warnings": warnings,
            "deadlines": entries,
        }

    sit_entry = (juris_entry.get("situations") or {}).get(situation)
    if sit_entry is None:
        raise DeadlineError(
            f"unknown or unpopulated situation {situation!r} for "
            f"jurisdiction {juris_key!r}. Known: "
            f"{sorted((juris_entry.get('situations') or {}).keys())}"
        )

    status = sit_entry.get("status", "stub")
    if status != "populated":
        warnings.append(
            f"Deadlines for ({juris_key}, {situation}) are marked {status!r}; "
            "values below are placeholders."
        )

    for d in sit_entry.get("deadlines") or []:
        clock = d.get("clock_starts", "loss_date")
        start, used_fallback = inputs.pick(clock)
        try:
            deadline_date = add_duration(start, d.get("duration") or {})
        except DeadlineError as exc:
            warnings.append(f"bad deadline entry {d.get('label')!r}: {exc}")
            continue
        entry: dict[str, Any] = {
            "label": d.get("label"),
            "kind": d.get("kind"),
            "clock_starts": clock,
            "clock_date": start.isoformat(),
            "used_fallback_loss_date": used_fallback,
            "duration": d.get("duration"),
            "deadline_date": deadline_date.isoformat(),
            "authority_ref": d.get("authority_ref"),
            "notes": d.get("notes"),
            "status": status,
            "verify": VERIFY_TAG,
        }
        entries.append(entry)

    return {
        "disclaimer": deadlines_yaml.get("disclaimer") or DISCLAIMER,
        "situation": situation,
        "jurisdiction": juris_key,
        "loss_date": inputs.loss_date.isoformat(),
        "warnings": warnings,
        "deadlines": entries,
    }


def format_text(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"[{result['disclaimer']}]")
    lines.append(
        f"Deadlines for situation={result['situation']} "
        f"jurisdiction={result['jurisdiction']} loss_date={result['loss_date']}"
    )
    for w in result.get("warnings", []):
        lines.append(f"WARNING: {w}")
    if not result["deadlines"]:
        lines.append("(no deadlines found)")
    for d in result["deadlines"]:
        lines.append("")
        stub = "" if d.get("status") == "populated" else f" [{d.get('status','stub').upper()}]"
        lines.append(f"- {d['label']}{stub}   -- {VERIFY_TAG}")
        lines.append(f"  kind:          {d['kind']}")
        lines.append(f"  clock_starts:  {d['clock_starts']} ({d['clock_date']})")
        if d.get("used_fallback_loss_date"):
            lines.append(
                f"  note:          fell back to loss_date because no "
                f"{d['clock_starts']} was provided"
            )
        lines.append(f"  duration:      {d['duration']}")
        lines.append(f"  DEADLINE:      {d['deadline_date']}   -- {VERIFY_TAG}")
        if d.get("authority_ref"):
            lines.append(f"  authority:     {d['authority_ref']}")
        notes = (d.get("notes") or "").strip()
        if notes:
            for nl in notes.splitlines():
                lines.append(f"    {nl}")
    lines.append("")
    lines.append(f"-- {result['disclaimer']}")
    return "\n".join(lines)


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--situation", required=True)
    p.add_argument("--jurisdiction", required=True)
    p.add_argument("--loss-date", required=True, help="YYYY-MM-DD")
    p.add_argument("--notice-of-loss", default=None)
    p.add_argument("--denial-date", default=None)
    p.add_argument("--last-act", default=None)
    p.add_argument("--custom-date", default=None)
    p.add_argument("--format", choices=("text", "json"), default="text")
    p.add_argument("--deadlines-yaml", type=Path, default=None)
    p.add_argument("--root", type=Path, default=None)
    args = p.parse_args(argv)

    try:
        inputs = ClockInputs(
            loss_date=_parse_date(args.loss_date),  # type: ignore[arg-type]
            notice_of_loss=_parse_date(args.notice_of_loss),
            denial_date=_parse_date(args.denial_date),
            last_act=_parse_date(args.last_act),
            custom=_parse_date(args.custom_date),
        )
    except ValueError as exc:
        print(f"error: bad date: {exc}", file=sys.stderr)
        return 2

    path = args.deadlines_yaml or (data_dir(args.root) / "deadlines.yaml")
    data = load_yaml(path)

    try:
        result = compute_deadlines(data, args.situation, args.jurisdiction, inputs)
    except DeadlineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
