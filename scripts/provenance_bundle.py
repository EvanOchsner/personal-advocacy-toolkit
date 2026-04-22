#!/usr/bin/env python3
"""Produce one attestation document for a whole packet of evidence.

Thin aggregator over `scripts.provenance`: reads a SHA-256 manifest,
runs the per-file forensic build_report on every entry, concatenates
the per-file results into a single YAML file, and prints a
verdict-count summary.

This is the "whole-tree" use case that the per-file tool doesn't cover
on its own. Consumed by the skill's "prepare a regulator handoff"
workflow.

Usage:
    python -m scripts.provenance_bundle \\
        --manifest PATH \\
        --out PATH.yaml \\
        [--evidence-root PATH] [--snapshot-dir PATH]
        [--pipeline-config PATH] [--repo-root PATH]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts._config import load_config
from scripts.provenance import (
    DEFAULT_PIPELINE_CONFIG,
    Report,
    _resolve_paths,
    build_report,
    format_yaml,
)


def _read_manifest(manifest_path: Path) -> list[tuple[str, str]]:
    """Return [(digest, rel_path), ...] for a shasum-style manifest."""
    out: list[tuple[str, str]] = []
    if not manifest_path.exists():
        return out
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            continue
        out.append((parts[0].strip(), parts[1].strip()))
    return out


def _verdict_from_report(report: Report) -> str:
    """Reduce a per-file report to a single verdict bucket."""
    # Structural fails (file missing on disk / hash mismatch) set
    # manifest.matches=False and appear in warnings as "HASH MISMATCH".
    for w in report.warnings:
        if "HASH MISMATCH" in w:
            return "fail"
        if "content change" in w:
            return "warn"
    if report.warnings:
        return "warn"
    return "pass"


def build_bundle(
    manifest_path: Path,
    *,
    repo_root: Path,
    evidence_root: Path,
    snapshot_dir: Path,
    pipeline_config: Path,
) -> dict[str, Any]:
    """Run per-file provenance over every manifest entry."""
    entries = _read_manifest(manifest_path)
    if not entries:
        raise FileNotFoundError(
            f"no manifest entries at {manifest_path} — "
            "run `scripts.evidence_hash` first?"
        )

    now = datetime.now(timezone.utc)
    files: list[dict[str, Any]] = []
    counts: dict[str, int] = {"pass": 0, "warn": 0, "fail": 0}

    for _digest, rel in entries:
        on_disk = evidence_root / rel
        if not on_disk.exists():
            files.append(
                {
                    "path": rel,
                    "verdict": "fail",
                    "note": "missing-on-disk",
                }
            )
            counts["fail"] += 1
            continue
        rep = build_report(
            on_disk,
            repo_root=repo_root,
            evidence_root=evidence_root,
            manifest_path=manifest_path,
            snapshot_dir=snapshot_dir,
            pipeline_config=pipeline_config,
        )
        verdict = _verdict_from_report(rep)
        counts[verdict] += 1
        files.append(
            {
                "path": rel,
                "verdict": verdict,
                "warnings": rep.warnings,
                "sections": rep.sections,
            }
        )

    return {
        "schema": "advocacy-toolkit/provenance-bundle/v1",
        "generated_at": now.isoformat(),
        "repo_root": str(repo_root),
        "evidence_root": str(evidence_root),
        "manifest": str(manifest_path),
        "count": len(files),
        "verdict_counts": counts,
        "files": files,
    }


def _dump_yaml(data: Any, fh: Any) -> None:
    """Re-use the per-file tool's YAML emitter so external readers need
    no PyYAML to open the attestation."""
    # We piggyback on format_yaml by wrapping the bundle in a shim
    # Report-like object that exposes warnings and sections on the
    # top-level dict. Simplest path: PyYAML if available, else
    # hand-rolled serializer.
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        from scripts.provenance import format_yaml as _fy

        # Build a Report shell to reuse the same emitter.
        class _Shim:
            def __init__(self, payload: dict[str, Any]) -> None:
                self.rel_path = payload.get("manifest", "")
                self.abs_path = payload.get("evidence_root", "")
                self.warnings = []
                self.sections = payload

        fh.write(_fy(_Shim(data)))  # type: ignore[arg-type]
        return
    yaml.safe_dump(
        data, fh, sort_keys=False, default_flow_style=False, allow_unicode=True
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--evidence-root", type=Path, default=None)
    ap.add_argument("--snapshot-dir", type=Path, default=None)
    ap.add_argument("--pipeline-config", type=Path, default=None)
    ap.add_argument("--repo-root", type=Path, default=None)
    ap.add_argument("--config", type=Path, default=None)
    # Alias --hash-manifest to --manifest for shared shape with `provenance`.
    args = ap.parse_args(argv)

    # Lean on the per-file tool's path resolution helper.
    class _Ns:
        hash_manifest = args.manifest
        evidence_root = args.evidence_root
        snapshot_dir = args.snapshot_dir

    cfg = load_config(repo_root=args.repo_root, config_path=args.config)
    repo_root, evidence_root, manifest_path, snapshot_dir = _resolve_paths(cfg, _Ns())
    pipeline_config = (
        args.pipeline_config.resolve()
        if args.pipeline_config
        else (repo_root / DEFAULT_PIPELINE_CONFIG).resolve()
    )

    try:
        bundle = build_bundle(
            manifest_path,
            repo_root=repo_root,
            evidence_root=evidence_root,
            snapshot_dir=snapshot_dir,
            pipeline_config=pipeline_config,
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        _dump_yaml(bundle, fh)

    counts = bundle["verdict_counts"]
    print(
        f"wrote provenance bundle ({bundle['count']} files) to {args.out} "
        f"[pass={counts['pass']}, warn={counts['warn']}, fail={counts['fail']}]"
    )
    return 0 if counts["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
