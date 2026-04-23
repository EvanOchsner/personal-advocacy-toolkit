#!/usr/bin/env python3
"""Classify a situation into a situation_type slug and emit case-intake.yaml.

This is a rules-based classifier (no LLM). It either reads a YAML
"answers" file (preferred, non-interactive) or, if stdin is a tty and no
answers file is given, prompts the user through a minimal questionnaire.

Routing rules come from data/situation_types.yaml: each situation
declares router_answers.counterparty_kind (set match) and
router_answers.keywords (substring-match against the free-text
"situation" answer). The first populated match wins; if nothing hits, we
fall through to the "unknown" slug.

Usage:
    uv run python -m scripts.intake.situation_classify \\
        --answers intake-answers.yaml \\
        --out case-intake.yaml

    # interactive (only if stdin is a tty)
    uv run python -m scripts.intake.situation_classify --out case-intake.yaml

Answers-file schema (all fields optional except `situation`):
    claimant_name: str
    jurisdiction_state: str         # 2-letter
    counterparty_kind: str          # one of the router vocab values
    situation: str                  # free-text describing the issue
    loss_date: YYYY-MM-DD
    notes: str
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from scripts.intake._common import DISCLAIMER, data_dir, load_yaml


@dataclass
class Answers:
    claimant_name: str = ""
    jurisdiction_state: str = ""
    counterparty_kind: str = ""
    situation: str = ""
    loss_date: str = ""
    notes: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Answers":
        return cls(
            claimant_name=str(d.get("claimant_name", "") or ""),
            jurisdiction_state=str(d.get("jurisdiction_state", "") or "").upper(),
            counterparty_kind=str(d.get("counterparty_kind", "") or "").lower(),
            situation=str(d.get("situation", "") or ""),
            loss_date=str(d.get("loss_date", "") or ""),
            notes=str(d.get("notes", "") or ""),
        )


@dataclass
class ClassifyResult:
    situation_slug: str
    matched_on: list[str] = field(default_factory=list)
    candidate_scores: dict[str, int] = field(default_factory=dict)


def classify(answers: Answers, situations_yaml: dict[str, Any]) -> ClassifyResult:
    """Score each situation; return the best match.

    Scoring:
      +2 for a counterparty_kind hit
      +1 for each keyword substring hit in the free-text situation
    "unknown" is reserved as the zero-score fallback.
    """
    situations = situations_yaml.get("situations", [])
    text = (answers.situation or "").lower()
    scores: dict[str, int] = {}
    matched_on: dict[str, list[str]] = {}

    for sit in situations:
        slug = sit.get("slug")
        if not slug or slug == "unknown":
            continue
        router = sit.get("router_answers") or {}
        cp_kinds = [str(x).lower() for x in (router.get("counterparty_kind") or [])]
        keywords = [str(x).lower() for x in (router.get("keywords") or [])]

        score = 0
        hits: list[str] = []
        if answers.counterparty_kind and answers.counterparty_kind in cp_kinds:
            score += 2
            hits.append(f"counterparty_kind={answers.counterparty_kind}")
        for kw in keywords:
            if kw and kw in text:
                score += 1
                hits.append(f"keyword={kw!r}")
        if score > 0:
            scores[slug] = score
            matched_on[slug] = hits

    if not scores:
        return ClassifyResult(situation_slug="unknown")

    # highest score wins; ties break on original list order.
    ordered = [s.get("slug") for s in situations if s.get("slug") in scores]
    best_slug = max(ordered, key=lambda s: scores[s])
    return ClassifyResult(
        situation_slug=best_slug,
        matched_on=matched_on.get(best_slug, []),
        candidate_scores=scores,
    )


def build_case_intake(answers: Answers, result: ClassifyResult) -> dict[str, Any]:
    """Produce a dict matching the case-intake.yaml schema v0.1 (partial)."""
    intake: dict[str, Any] = {
        "schema_version": "0.1",
        "synthetic": False,
        "situation_type": result.situation_slug,
        "classifier": {
            "matched_on": result.matched_on,
            "candidate_scores": result.candidate_scores,
            "disclaimer": DISCLAIMER,
        },
        "claimant": {
            "name": answers.claimant_name or None,
        },
        "jurisdiction": {
            "state": answers.jurisdiction_state or None,
        },
        "counterparty_kind": answers.counterparty_kind or None,
        "loss": {
            "date": answers.loss_date or None,
            "description": answers.situation or None,
        },
        "notes": answers.notes or None,
    }
    return intake


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

QUESTIONS = [
    ("claimant_name", "Your name (or claimant name):"),
    ("jurisdiction_state", "Jurisdiction (2-letter state, e.g. MD):"),
    (
        "counterparty_kind",
        "Counterparty kind (insurer / landlord / employer / debt_collector / "
        "merchant / hospital / online_platform / individual / other):",
    ),
    ("situation", "Describe the situation in one or two sentences:"),
    ("loss_date", "Loss/incident date (YYYY-MM-DD, or blank if N/A):"),
    ("notes", "Anything else worth capturing (optional):"),
]


def _interactive_prompt() -> Answers:
    d: dict[str, str] = {}
    print("Situation classifier — minimal questionnaire")
    print(DISCLAIMER)
    print()
    for key, prompt in QUESTIONS:
        try:
            ans = input(f"{prompt} ").strip()
        except EOFError:
            ans = ""
        d[key] = ans
    return Answers.from_dict(d)


def _dump_yaml(obj: dict[str, Any], out: Path) -> None:
    import yaml  # type: ignore

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(obj, sort_keys=False, allow_unicode=True))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--answers", type=Path, default=None, help="YAML file of pre-filled answers")
    p.add_argument("--out", type=Path, required=True, help="output case-intake.yaml path")
    p.add_argument(
        "--situations-yaml",
        type=Path,
        default=None,
        help="override data/situation_types.yaml (defaults to repo-root data dir)",
    )
    p.add_argument("--root", type=Path, default=None, help="repo root override")
    p.add_argument(
        "--non-interactive",
        action="store_true",
        help="fail instead of prompting if --answers is absent",
    )
    args = p.parse_args(argv)

    situations_path = args.situations_yaml or (data_dir(args.root) / "situation_types.yaml")
    situations_yaml = load_yaml(situations_path)

    if args.answers is not None:
        raw = load_yaml(args.answers)
        answers = Answers.from_dict(raw)
    elif args.non_interactive or not sys.stdin.isatty():
        print(
            "error: --answers not provided and stdin is not a tty (or --non-interactive set).",
            file=sys.stderr,
        )
        return 2
    else:
        answers = _interactive_prompt()

    # Light validation of loss_date
    if answers.loss_date:
        try:
            date.fromisoformat(answers.loss_date)
        except ValueError:
            print(
                f"warning: loss_date {answers.loss_date!r} is not ISO YYYY-MM-DD; "
                "leaving as-is.",
                file=sys.stderr,
            )

    result = classify(answers, situations_yaml)
    intake = build_case_intake(answers, result)
    _dump_yaml(intake, args.out)

    print(f"{DISCLAIMER}")
    print(f"situation_type: {result.situation_slug}")
    if result.matched_on:
        print(f"matched on: {', '.join(result.matched_on)}")
    else:
        print("matched on: (no rules fired; fell through to 'unknown')")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
