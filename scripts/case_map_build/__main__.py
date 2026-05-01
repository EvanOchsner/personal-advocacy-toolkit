"""CLI: build the case-map dashboard cache.

Usage:
    uv run python -m scripts.case_map_build --case-dir path/to/case
                                            [--llm | --no-llm]
                                            [--force]

Reads the case files (entities.yaml, case-facts.yaml, events.yaml,
references manifest, authorities-research notes) and writes a
per-widget JSON cache plus a combined dashboard.json under
<case>/.case-map/. The viewer (scripts.app) reads only the cache and
never re-runs the build.

By default the build is deterministic and offline. --llm opts in to
Claude-API enrichment of synopses, gated on ANTHROPIC_API_KEY. LLM
failures are caught per-widget and silently fall back to the
deterministic content; the build still succeeds.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.intake._common import DISCLAIMER

from scripts.app._loaders import load_case_map
from scripts.app._schema import CaseMapError

from scripts.case_map_build import _cache, _widgets


WIDGETS = ("central_issue", "parties", "references", "adjudicators", "timeline")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--case-dir", type=Path, required=True)
    grp = p.add_mutually_exclusive_group()
    grp.add_argument(
        "--llm",
        dest="llm",
        action="store_true",
        help="Enrich synopses with the Claude API (requires ANTHROPIC_API_KEY).",
    )
    grp.add_argument(
        "--no-llm",
        dest="llm",
        action="store_false",
        help="Deterministic only (default).",
    )
    p.set_defaults(llm=False)
    p.add_argument(
        "--force",
        action="store_true",
        help="Discard any cached widgets and regenerate everything.",
    )
    args = p.parse_args(argv)

    case_dir: Path = args.case_dir.resolve()
    try:
        loaded = load_case_map(case_dir)
    except CaseMapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    cache_dir = case_dir / ".case-map"
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest = _cache.CacheManifest() if args.force else _cache.load_manifest(cache_dir)

    llm = None
    if args.llm:
        try:
            from scripts.case_map_build._llm import LLMSummarizer

            llm = LLMSummarizer()
        except RuntimeError as exc:
            print(f"warning: --llm requested but unavailable: {exc}", file=sys.stderr)
            llm = None

    actions: list[str] = []
    payloads: dict[str, dict] = {}

    for widget in WIDGETS:
        inputs = _widgets.widget_inputs(case_dir, widget)
        stale = args.force or _cache.is_widget_stale(widget, inputs, case_dir, manifest, cache_dir)
        if not stale:
            payloads[widget] = _cache.read_widget(cache_dir, widget)
            actions.append(f"{widget}: cached")
            continue

        if widget == "central_issue":
            payload = _widgets.gen_central_issue(loaded, llm=llm)
        elif widget == "parties":
            payload = _widgets.gen_parties(loaded, llm=llm)
        elif widget == "references":
            payload = _widgets.gen_references(case_dir, llm=llm)
        elif widget == "adjudicators":
            payload = _widgets.gen_adjudicators(case_dir, loaded)
        elif widget == "timeline":
            payload = _widgets.gen_timeline(loaded)
        else:  # pragma: no cover — guarded by WIDGETS
            raise AssertionError(f"unreachable widget: {widget}")

        _cache.write_widget(cache_dir, widget, payload)
        _cache.record_widget(widget, inputs, case_dir, manifest)
        payloads[widget] = payload
        actions.append(f"{widget}: regenerated ({len(inputs)} input(s))")

    # Dashboard payload — verbatim what /api/dashboard returns.
    dashboard = {
        "schema_version": _cache.CACHE_SCHEMA_VERSION,
        "case_dir_name": case_dir.name,
        "central_issue": payloads["central_issue"],
        "parties": payloads["parties"],
        "references": payloads["references"],
        "adjudicators": payloads["adjudicators"],
        "disclaimer": DISCLAIMER,
    }
    (cache_dir / _cache.DASHBOARD_NAME).write_text(
        json.dumps(dashboard, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    _cache.write_manifest(cache_dir, manifest)

    print(f"case-map cache written to {cache_dir}")
    for line in actions:
        print(f"  {line}")
    print(DISCLAIMER, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
