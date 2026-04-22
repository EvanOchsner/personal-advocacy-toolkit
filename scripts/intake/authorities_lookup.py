#!/usr/bin/env python3
"""Look up authorities (regulators, ombuds, bar, AG, federal) for
(situation, jurisdiction) from data/authorities.yaml.

This is reference information, not legal advice. Output always includes
a disclaimer banner.

Usage:
    python -m scripts.intake.authorities_lookup \\
        --situation insurance_dispute --jurisdiction MD

    # JSON output for pipelines
    python -m scripts.intake.authorities_lookup \\
        --situation insurance_dispute --jurisdiction MD --format json

Behavior notes:
  - An unknown situation exits non-zero with a helpful error listing
    valid situation slugs.
  - An unknown jurisdiction falls back gracefully: we still return the
    "federal" bucket (if present) and print a warning that
    state-specific authorities are not yet populated.
  - Every record is emitted with its TODO/populated status so callers
    can tell stubs from real entries.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.intake._common import DISCLAIMER, data_dir, load_yaml


class LookupError_(Exception):
    pass


def known_situations(authorities_yaml: dict[str, Any]) -> set[str]:
    slugs: set[str] = set()
    for _, jdata in (authorities_yaml.get("jurisdictions") or {}).items():
        for sit_slug in (jdata.get("situations") or {}).keys():
            slugs.add(sit_slug)
    return slugs


def known_jurisdictions(authorities_yaml: dict[str, Any]) -> list[str]:
    return sorted((authorities_yaml.get("jurisdictions") or {}).keys())


def lookup(
    authorities_yaml: dict[str, Any],
    situation: str,
    jurisdiction: str,
) -> dict[str, Any]:
    """Return a structured result dict; never raises for missing jurisdiction."""
    all_situations = known_situations(authorities_yaml)
    if situation not in all_situations:
        raise LookupError_(
            f"unknown situation {situation!r}. "
            f"Known: {sorted(all_situations)}"
        )

    jurisdictions = authorities_yaml.get("jurisdictions") or {}
    warnings: list[str] = []

    juris_key = jurisdiction.upper() if jurisdiction else ""
    state_entry = jurisdictions.get(juris_key)
    if state_entry is None and juris_key:
        warnings.append(
            f"No jurisdiction entry for {juris_key!r}; returning federal-only "
            "results. Contribute to data/authorities.yaml to fill this in."
        )

    results: list[dict[str, Any]] = []

    # Federal bucket first (if present).
    fed = jurisdictions.get("federal") or {}
    fed_sit = (fed.get("situations") or {}).get(situation)
    if fed_sit:
        for a in fed_sit.get("authorities") or []:
            results.append({**a, "scope": "federal", "status": fed_sit.get("status", "stub")})

    # State bucket.
    if state_entry is not None:
        st_sit = (state_entry.get("situations") or {}).get(situation)
        if st_sit:
            for a in st_sit.get("authorities") or []:
                results.append(
                    {**a, "scope": juris_key, "status": st_sit.get("status", "stub")}
                )
        else:
            warnings.append(
                f"{juris_key} has no entry for situation {situation!r}. "
                "Federal-only results returned."
            )

    return {
        "disclaimer": DISCLAIMER,
        "situation": situation,
        "jurisdiction": juris_key or None,
        "warnings": warnings,
        "authorities": results,
    }


def format_text(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"[{result['disclaimer']}]")
    lines.append(
        f"Authorities for situation={result['situation']} "
        f"jurisdiction={result['jurisdiction']}"
    )
    for w in result.get("warnings", []):
        lines.append(f"WARNING: {w}")
    if not result["authorities"]:
        lines.append("(no authorities found; consider contributing to data/authorities.yaml)")
    for a in result["authorities"]:
        status_tag = "" if a.get("status") == "populated" else f" [{a.get('status','stub').upper()}]"
        lines.append("")
        lines.append(f"- {a.get('name')} ({a.get('short_name','')}){status_tag}")
        lines.append(f"  scope:  {a.get('scope')}")
        lines.append(f"  kind:   {a.get('kind')}")
        if a.get("url"):
            lines.append(f"  url:    {a.get('url')}")
        notes = (a.get("notes") or "").strip()
        if notes:
            for nl in notes.splitlines():
                lines.append(f"    {nl}")
    lines.append("")
    lines.append(f"-- {result['disclaimer']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--situation", required=True)
    p.add_argument("--jurisdiction", default="", help="2-letter state (e.g., MD)")
    p.add_argument("--format", choices=("text", "json"), default="text")
    p.add_argument("--authorities-yaml", type=Path, default=None)
    p.add_argument("--root", type=Path, default=None)
    args = p.parse_args(argv)

    path = args.authorities_yaml or (data_dir(args.root) / "authorities.yaml")
    data = load_yaml(path)

    try:
        result = lookup(data, args.situation, args.jurisdiction)
    except LookupError_ as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(f"known jurisdictions: {known_jurisdictions(data)}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
