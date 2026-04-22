#!/usr/bin/env python3
"""Build a unified provenance report for a case workspace.

Joins four sources into a single JSON document:

1. The SHA-256 manifest produced by `evidence_hash.py`.
2. The most recent provenance snapshot (xattrs + mtimes) under
   `provenance.snapshot_dir`.
3. Git history for each tracked file (first and last commit touching it),
   if the workspace is a git repo.
4. Pipeline metadata sidecars (`<file>.meta.json`), when present — these
   are written by ingestion scripts (e.g. email EML → JSON → TXT) to
   record what transformed the file.

The output is designed for a non-technical reader (regulator, attorney,
journalist) to skim: one row per evidence file, with every derivable
fact visible. An attorney can then subpoena git server logs or platform
records corresponding to the timestamps and xattr URLs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts._config import Config, load_config
from scripts.evidence_hash import read_manifest


def latest_snapshot(snapshot_dir: Path) -> dict[str, Any] | None:
    if not snapshot_dir.exists():
        return None
    candidates = sorted(snapshot_dir.glob("*.json"))
    if not candidates:
        return None
    with open(candidates[-1], encoding="utf-8") as fh:
        return json.load(fh)


def git_history_for(repo_root: Path, rel_path: str) -> dict[str, Any] | None:
    """Return first/last commit touching `rel_path`, or None if not in git."""
    try:
        first = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "log",
                "--diff-filter=A",
                "--follow",
                "--format=%H%x09%an%x09%aI",
                "--",
                rel_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        last = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "log",
                "-1",
                "--format=%H%x09%an%x09%aI",
                "--",
                rel_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if first.returncode != 0 and last.returncode != 0:
        return None

    def _parse(line: str) -> dict[str, str] | None:
        line = line.strip().splitlines()[-1] if line.strip() else ""
        if not line:
            return None
        parts = line.split("\t")
        if len(parts) != 3:
            return None
        return {"sha": parts[0], "author": parts[1], "date": parts[2]}

    return {
        "added": _parse(first.stdout),
        "last_touched": _parse(last.stdout),
    }


def load_pipeline_meta(evidence_root: Path, rel_path: str) -> dict[str, Any] | None:
    sidecar = evidence_root / f"{rel_path}.meta.json"
    if not sidecar.exists():
        return None
    try:
        with open(sidecar, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def build_report(cfg: Config) -> dict[str, Any]:
    manifest = read_manifest(cfg.manifest_path)
    snap = latest_snapshot(cfg.snapshot_dir)
    snap_by_path: dict[str, dict[str, Any]] = {}
    if snap:
        for e in snap.get("entries", []):
            snap_by_path[e["path"]] = e

    files: list[dict[str, Any]] = []
    for digest, rel in manifest:
        entry: dict[str, Any] = {"path": rel, "sha256": digest}
        s = snap_by_path.get(rel)
        if s:
            entry["size"] = s.get("size")
            entry["mtime"] = s.get("mtime")
            entry["xattrs"] = s.get("xattrs", {})
        git = git_history_for(cfg.repo_root, str(cfg.evidence_root.relative_to(cfg.repo_root) / rel))
        if git:
            entry["git"] = git
        meta = load_pipeline_meta(cfg.evidence_root, rel)
        if meta is not None:
            entry["pipeline"] = meta
        files.append(entry)

    return {
        "schema": "advocacy-toolkit/provenance-report/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(cfg.repo_root),
        "evidence_root": str(cfg.evidence_root),
        "manifest": str(cfg.manifest_path),
        "snapshot": (
            snap.get("captured_at") if snap else None
        ),
        "count": len(files),
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, help="SHA-256 manifest path.")
    ap.add_argument("--snapshot-dir", type=Path, help="Snapshot directory.")
    ap.add_argument("--out", type=Path, help="Report output path (default from config).")
    ap.add_argument("--config", type=Path, help="Path to advocacy.toml.")
    ap.add_argument("--repo-root", type=Path, help="Repo root.")
    ap.add_argument("--stdout", action="store_true", help="Also print the report to stdout.")
    args = ap.parse_args(argv)

    cfg = load_config(repo_root=args.repo_root, config_path=args.config)
    if args.manifest is not None:
        cfg.manifest_path = args.manifest.resolve()
    if args.snapshot_dir is not None:
        cfg.snapshot_dir = args.snapshot_dir.resolve()
    out = (args.out or cfg.report_path).resolve()

    report = build_report(cfg)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"wrote provenance report ({report['count']} files) to {out}")
    if args.stdout:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
