#!/usr/bin/env python3
"""Build a unified provenance report for a case workspace.

Joins four sources into a single document (JSON by default, YAML when
`--forensic` is set):

1. The SHA-256 manifest produced by `evidence_hash.py`.
2. The most recent provenance snapshot (xattrs + mtimes) under
   `provenance.snapshot_dir`.
3. Git history for each tracked file (first and last commit touching it),
   if the workspace is a git repo.
4. Pipeline metadata sidecars (`<file>.meta.json`), when present — these
   are written by ingestion scripts (e.g. email EML → JSON → TXT) to
   record what transformed the file.

Each entry carries a verdict (``pass`` / ``warn`` / ``fail``) and a
``reason_codes`` list explaining it. ``--verify`` is the short-circuit
path: recompute every manifest digest on disk, print any mismatches, and
exit non-zero if anything drifted. ``--forensic`` expands the full
report as YAML — with xattr decoders for macOS WhereFroms / quarantine
fields — for regulator or attorney handoff.

The report is designed for a non-technical reader (regulator, attorney,
journalist) to skim: one row per evidence file, with every derivable
fact visible. An attorney can then subpoena git server logs or platform
records corresponding to the timestamps and xattr URLs.
"""

from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts._config import Config, load_config
from scripts.evidence_hash import read_manifest, sha256_file


# A snapshot older than this is still used, but entries it backs are
# marked with a `stale-snapshot` warning.
SNAPSHOT_STALE_SECONDS = 30 * 24 * 3600


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


def git_is_tracked(repo_root: Path, rel_path: str) -> bool | None:
    """Return True/False if git can answer, None if git is unavailable."""
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "ls-files",
                "--error-unmatch",
                "--",
                rel_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    return result.returncode == 0


def load_pipeline_meta(evidence_root: Path, rel_path: str) -> dict[str, Any] | None:
    sidecar = evidence_root / f"{rel_path}.meta.json"
    if not sidecar.exists():
        return None
    try:
        with open(sidecar, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def decode_wherefroms(raw: str) -> dict[str, Any]:
    """Decode `com.apple.metadata:kMDItemWhereFroms` into URL list.

    The xattr is a binary plist listing URLs (origin page + download URL).
    The snapshot stores it as `hex:<...>` when not UTF-8 decodable, which
    is the usual case for this particular xattr.
    """
    out: dict[str, Any] = {}
    try:
        if raw.startswith("hex:"):
            payload = bytes.fromhex(raw[4:])
        else:
            # Best-effort: the value may have been stored as latin-1 bytes.
            payload = raw.encode("latin-1", errors="replace")
        urls = plistlib.loads(payload)
        if isinstance(urls, list):
            out["urls"] = [str(u) for u in urls if u]
    except Exception as exc:  # pragma: no cover - defensive
        out["decode_error"] = f"{type(exc).__name__}: {exc}"
    return out


def decode_quarantine(raw: str) -> dict[str, Any]:
    """Decode `com.apple.quarantine` semicolon-separated fields.

    Format: ``flags;hex-timestamp;agent;uuid``. The timestamp is a
    hex-encoded seconds-since-epoch integer.
    """
    out: dict[str, Any] = {"raw": raw}
    parts = raw.split(";")
    if len(parts) >= 1:
        out["flags"] = parts[0]
    if len(parts) >= 2:
        try:
            ts = int(parts[1], 16)
            out["timestamp"] = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except ValueError:
            out["timestamp_raw"] = parts[1]
    if len(parts) >= 3:
        out["agent"] = parts[2]
    if len(parts) >= 4:
        out["uuid"] = parts[3]
    return out


def expand_xattrs(xattrs: dict[str, str]) -> dict[str, Any]:
    """Decode known macOS xattrs; leave unknown ones as-is."""
    out: dict[str, Any] = {}
    for name, value in xattrs.items():
        if name == "com.apple.metadata:kMDItemWhereFroms":
            decoded = decode_wherefroms(value)
            out[name] = {"raw": value, **decoded}
        elif name == "com.apple.quarantine":
            out[name] = decode_quarantine(value)
        else:
            out[name] = value
    return out


def _classify(reasons: list[str]) -> str:
    fail_codes = {
        "sha-mismatch",
        "missing-on-disk",
        "xattr-decode-failure",
    }
    if any(r in fail_codes for r in reasons):
        return "fail"
    if reasons:
        return "warn"
    return "pass"


def build_report(cfg: Config, *, forensic: bool = False) -> dict[str, Any]:
    manifest = read_manifest(cfg.manifest_path)
    snap = latest_snapshot(cfg.snapshot_dir)
    snap_by_path: dict[str, dict[str, Any]] = {}
    snap_captured_at: datetime | None = None
    if snap:
        for e in snap.get("entries", []):
            snap_by_path[e["path"]] = e
        captured = snap.get("captured_at")
        if captured:
            try:
                snap_captured_at = datetime.fromisoformat(captured)
            except ValueError:
                snap_captured_at = None

    now = datetime.now(timezone.utc)
    snap_stale = False
    if snap_captured_at is not None:
        age = (now - snap_captured_at).total_seconds()
        snap_stale = age > SNAPSHOT_STALE_SECONDS

    files: list[dict[str, Any]] = []
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for digest, rel in manifest:
        entry: dict[str, Any] = {"path": rel, "sha256": digest}
        reasons: list[str] = []

        on_disk = cfg.evidence_root / rel
        if not on_disk.exists():
            reasons.append("missing-on-disk")
        else:
            if forensic:
                try:
                    actual = sha256_file(on_disk)
                except OSError as exc:
                    reasons.append("missing-on-disk")
                    entry["sha256_error"] = str(exc)
                else:
                    if actual != digest:
                        reasons.append("sha-mismatch")
                        entry["sha256_actual"] = actual

        s = snap_by_path.get(rel)
        if s:
            entry["size"] = s.get("size")
            entry["mtime"] = s.get("mtime")
            raw_xattrs = s.get("xattrs", {}) or {}
            if forensic:
                try:
                    entry["xattrs"] = expand_xattrs(raw_xattrs)
                except Exception:
                    reasons.append("xattr-decode-failure")
                    entry["xattrs"] = raw_xattrs
            else:
                entry["xattrs"] = raw_xattrs
            if snap_stale:
                reasons.append("stale-snapshot")
        else:
            reasons.append("missing-snapshot")

        rel_from_repo = str(cfg.evidence_root.relative_to(cfg.repo_root) / rel)
        git = git_history_for(cfg.repo_root, rel_from_repo)
        if git:
            entry["git"] = git
        tracked = git_is_tracked(cfg.repo_root, rel_from_repo)
        if tracked is False:
            reasons.append("git-untracked")

        meta = load_pipeline_meta(cfg.evidence_root, rel)
        if meta is not None:
            entry["pipeline"] = meta

        verdict = _classify(reasons)
        entry["verdict"] = verdict
        entry["reason_codes"] = reasons
        counts[verdict] += 1
        files.append(entry)

    return {
        "schema": "advocacy-toolkit/provenance-report/v1",
        "generated_at": now.isoformat(),
        "repo_root": str(cfg.repo_root),
        "evidence_root": str(cfg.evidence_root),
        "manifest": str(cfg.manifest_path),
        "snapshot": snap.get("captured_at") if snap else None,
        "snapshot_stale": snap_stale,
        "count": len(files),
        "verdict_counts": counts,
        "files": files,
    }


def verify(cfg: Config) -> int:
    """Recompute SHA-256 for every manifest entry; exit non-zero on mismatch."""
    expected = read_manifest(cfg.manifest_path)
    if not expected:
        print(f"no manifest found at {cfg.manifest_path}", file=sys.stderr)
        return 2

    problems: list[str] = []
    for digest, rel in expected:
        p = cfg.evidence_root / rel
        if not p.exists():
            problems.append(f"missing: {rel}")
            continue
        try:
            actual = sha256_file(p)
        except OSError as exc:
            problems.append(f"unreadable: {rel}: {exc}")
            continue
        if actual != digest:
            problems.append(
                f"hash-mismatch: {rel}\n  expected {digest}\n  actual   {actual}"
            )

    if problems:
        for line in problems:
            print(line, file=sys.stderr)
        return 1
    print(f"ok: {len(expected)} files verified against {cfg.manifest_path}")
    return 0


def _dump_yaml(data: Any, fh: Any) -> None:
    """Write `data` as YAML. Uses PyYAML when available; else a tiny fallback.

    The fallback handles the specific shapes this report emits (nested
    dicts, lists of dicts, scalars) and is good enough for human review.
    """
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        _fallback_yaml(data, fh, indent=0)
        return
    yaml.safe_dump(data, fh, sort_keys=True, default_flow_style=False, allow_unicode=True)


def _fallback_yaml(data: Any, fh: Any, *, indent: int) -> None:
    pad = "  " * indent
    if isinstance(data, dict):
        if not data:
            fh.write("{}\n")
            return
        for k in sorted(data.keys()):
            v = data[k]
            if isinstance(v, (dict, list)) and v:
                fh.write(f"{pad}{k}:\n")
                _fallback_yaml(v, fh, indent=indent + 1)
            else:
                fh.write(f"{pad}{k}: {_yaml_scalar(v)}\n")
    elif isinstance(data, list):
        if not data:
            fh.write("[]\n")
            return
        for item in data:
            if isinstance(item, (dict, list)) and item:
                fh.write(f"{pad}-\n")
                _fallback_yaml(item, fh, indent=indent + 1)
            else:
                fh.write(f"{pad}- {_yaml_scalar(item)}\n")
    else:
        fh.write(f"{pad}{_yaml_scalar(data)}\n")


def _yaml_scalar(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    # Quote if it contains YAML-sensitive characters.
    if any(c in s for c in ":#\n") or s.strip() != s or s == "":
        return json.dumps(s, ensure_ascii=False)
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, help="SHA-256 manifest path.")
    ap.add_argument(
        "--evidence-root",
        type=Path,
        help="Evidence root (overrides config). Defaults to the manifest's "
        "sibling `evidence/` directory when it exists, else config.",
    )
    ap.add_argument("--snapshot-dir", type=Path, help="Snapshot directory.")
    ap.add_argument("--out", type=Path, help="Report output path (default from config).")
    ap.add_argument("--config", type=Path, help="Path to advocacy.toml.")
    ap.add_argument("--repo-root", type=Path, help="Repo root.")
    ap.add_argument("--stdout", action="store_true", help="Also print the report to stdout.")
    ap.add_argument(
        "--verify",
        action="store_true",
        help="Recompute SHA-256 for every manifest entry; exit non-zero on mismatch.",
    )
    ap.add_argument(
        "--forensic",
        action="store_true",
        help="Emit a full YAML report with expanded xattrs and verdicts.",
    )
    args = ap.parse_args(argv)

    cfg = load_config(repo_root=args.repo_root, config_path=args.config)
    if args.manifest is not None:
        cfg.manifest_path = args.manifest.resolve()
    if args.snapshot_dir is not None:
        cfg.snapshot_dir = args.snapshot_dir.resolve()
    if args.evidence_root is not None:
        cfg.evidence_root = args.evidence_root.resolve()
    elif args.manifest is not None and not cfg.evidence_root.exists():
        # Fall back to the manifest's sibling `evidence/` directory if the
        # configured root doesn't exist on disk. Lets `--manifest
        # path/to/.evidence-manifest.sha256` work against an example tree
        # without requiring a separate advocacy.toml.
        sibling = cfg.manifest_path.parent / "evidence"
        if sibling.exists():
            cfg.evidence_root = sibling.resolve()

    if args.verify:
        return verify(cfg)

    report = build_report(cfg, forensic=args.forensic)
    out = (args.out or cfg.report_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        if args.forensic:
            _dump_yaml(report, fh)
        else:
            json.dump(report, fh, indent=2, sort_keys=True)
            fh.write("\n")
    fmt = "YAML" if args.forensic else "JSON"
    print(f"wrote provenance report ({fmt}, {report['count']} files) to {out}")
    if args.stdout:
        if args.forensic:
            _dump_yaml(report, sys.stdout)
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
