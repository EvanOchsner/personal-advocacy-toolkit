#!/usr/bin/env python3
"""Provenance reader — per-file forensic inspection.

Given one path inside the repo, surface every forensic fact the workspace
records about it:

  1. Identity     — rel_path, size, ext, current SHA-256, git blob SHA-1,
                    git-tracked flag.
  2. Git trail    — `git log --follow` over the file, classifying each
                    commit as `initial` / `content` / `rename-or-metadata`
                    by comparing blob SHAs against the previous commit.
  3. Hash manifest — recorded SHA vs on-disk; mismatch / missing / OK.
  4. Download     — live xattrs (cross-platform: macOS xattrs via
                    os.getxattr, Linux user.xdg.* attrs, Windows NTFS
                    Zone.Identifier ADS) plus every historical entry
                    from `provenance_snapshots/` matching the basename.
                    Decodes `com.apple.metadata:kMDItemWhereFroms` (binary
                    plist → URL list), `com.apple.quarantine`, and
                    Windows `[ZoneTransfer]` blocks.
  5. Pipeline     — config-driven dispatcher
                    (`data/pipeline_dispatch.yaml`) that surfaces
                    content-type-specific sidecar data (email headers,
                    catalog mentions, sibling YAML frontmatter, etc.).
  6. Verdict      — one-line human summary combining the above.

Usage:
    uv run python -m scripts.provenance PATH             # human-readable report
    uv run python -m scripts.provenance PATH --forensic  # YAML for lawyer/regulator
    uv run python -m scripts.provenance PATH --verify    # silent unless warnings; exit 1 on any ⚠

For the whole-packet attestation case ("produce one document of
provenance for a regulator"), see `scripts/provenance_bundle.py`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts import _file_metadata
from scripts._config import Config, load_config


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    return r.returncode, r.stdout, r.stderr


# -----------------------------------------------------------------------------
# Report dataclass
# -----------------------------------------------------------------------------


@dataclass
class Report:
    abs_path: str
    rel_path: str
    repo_root: Path
    evidence_root: Path
    sections: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def under_evidence(self) -> bool:
        try:
            p = (self.repo_root / self.rel_path).resolve()
            p.relative_to(self.evidence_root.resolve())
            return True
        except (ValueError, OSError):
            return False


# -----------------------------------------------------------------------------
# Section 1: Identity
# -----------------------------------------------------------------------------


def section_identity(path: Path, report: Report) -> dict[str, Any]:
    stat = path.stat()
    sha = sha256_file(path)
    rc, blob, _ = _run(["git", "hash-object", str(path)], cwd=report.repo_root)
    blob_sha = blob.strip() if rc == 0 else None
    rc, _, _ = _run(
        ["git", "ls-files", "--error-unmatch", str(path)], cwd=report.repo_root
    )
    tracked = rc == 0
    return {
        "abs_path": str(path),
        "rel_path": report.rel_path,
        "size_bytes": stat.st_size,
        "extension": path.suffix.lower(),
        "sha256": sha,
        "git_blob_sha1": blob_sha,
        "git_tracked": tracked,
    }


# -----------------------------------------------------------------------------
# Section 2: Git trail
# -----------------------------------------------------------------------------


def section_git(path: Path, report: Report) -> dict[str, Any]:
    """Walk the file's history with --follow; classify each commit.

    Content-edits to files under the configured evidence root are flagged
    as warnings — post-placement content changes are the primary forensic
    red flag for evidence integrity.
    """
    rc, out, _ = _run(
        [
            "git",
            "log",
            "--follow",
            "--name-status",
            "--format=%x00COMMIT%x00%H%x00%h%x00%ai%x00%an%x00%s",
            "--",
            str(path),
        ],
        cwd=report.repo_root,
    )
    commits: list[dict[str, Any]] = []
    if rc == 0 and out.strip():
        blocks = out.split("\x00COMMIT\x00")
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            head, _, body = block.partition("\n")
            parts = head.split("\x00")
            if len(parts) < 5:
                continue
            full_sha, short_sha, date, author, subject = parts[:5]
            status = None
            path_at_commit: str | None = None
            for ns_line in body.splitlines():
                ns_line = ns_line.strip()
                if not ns_line:
                    continue
                fields = ns_line.split("\t")
                code = fields[0]
                if code.startswith("R") and len(fields) >= 3:
                    status, path_at_commit = "rename", fields[2]
                elif code == "A" and len(fields) >= 2:
                    status, path_at_commit = "add", fields[1]
                elif code == "M" and len(fields) >= 2:
                    status, path_at_commit = "modify", fields[1]
                elif code == "D" and len(fields) >= 2:
                    status, path_at_commit = "delete", fields[1]
                elif len(fields) >= 2:
                    status, path_at_commit = code, fields[-1]
                break
            blob = None
            if path_at_commit:
                rc2, out2, _ = _run(
                    ["git", "ls-tree", full_sha, path_at_commit],
                    cwd=report.repo_root,
                )
                if rc2 == 0 and out2.strip():
                    blob_parts = out2.strip().split()
                    if len(blob_parts) >= 3 and blob_parts[1] == "blob":
                        blob = blob_parts[2]
            commits.append(
                {
                    "short_sha": short_sha,
                    "full_sha": full_sha,
                    "date": date,
                    "author": author,
                    "subject": subject,
                    "status": status,
                    "path_at_commit": path_at_commit,
                    "blob_sha": blob,
                }
            )

    # Classify each commit oldest→newest by comparing blob SHAs.
    ordered = list(reversed(commits))
    prev_blob = None
    content_changes: list[dict[str, Any]] = []
    for c in ordered:
        if prev_blob is None:
            c["change_type"] = "initial"
        else:
            c["change_type"] = (
                "content" if c["blob_sha"] != prev_blob else "rename-or-metadata"
            )
        if c["change_type"] == "content":
            content_changes.append(c)
        prev_blob = c["blob_sha"] or prev_blob

    if report.under_evidence and content_changes:
        names = ", ".join(
            f"{c['short_sha']} ({c['subject'][:50]})" for c in content_changes
        )
        report.warn(
            f"evidence file has {len(content_changes)} post-placement "
            f"content change(s): {names}"
        )
    if not commits:
        report.warn("file has no git history (not tracked, or never committed)")
    return {
        "commits": commits,
        "commit_count": len(commits),
        "content_change_count": len(content_changes),
    }


# -----------------------------------------------------------------------------
# Section 3: Hash manifest
# -----------------------------------------------------------------------------


def _read_manifest(manifest_path: Path) -> dict[str, str]:
    """Read a shasum-style manifest as {posix_relpath: hex_digest}."""
    out: dict[str, str] = {}
    if not manifest_path.exists():
        return out
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            continue
        out[parts[1].strip()] = parts[0].strip()
    return out


def section_manifest(
    path: Path, identity: dict[str, Any], manifest_path: Path, report: Report
) -> dict[str, Any]:
    """Look up the file in the hash manifest."""
    # Manifest paths are relative to the evidence root.
    try:
        rel_to_evidence = str(path.resolve().relative_to(report.evidence_root.resolve()))
    except ValueError:
        rel_to_evidence = None

    result: dict[str, Any] = {
        "applies": report.under_evidence,
        "manifest_path": str(manifest_path),
        "relative_key": rel_to_evidence,
        "recorded_sha256": None,
        "matches": None,
    }
    if not result["applies"]:
        return result
    if not manifest_path.exists():
        report.warn(f"hash manifest not present at {manifest_path}")
        return result
    manifest = _read_manifest(manifest_path)
    if rel_to_evidence and rel_to_evidence in manifest:
        recorded = manifest[rel_to_evidence]
        result["recorded_sha256"] = recorded
        result["matches"] = recorded == identity["sha256"]
        if not result["matches"]:
            report.warn(
                f"HASH MISMATCH: manifest records {recorded}, "
                f"on-disk file hashes to {identity['sha256']}"
            )
        return result
    report.warn(
        f"file is under evidence/ but not recorded in {manifest_path.name}"
    )
    return result


# -----------------------------------------------------------------------------
# Section 4: Download provenance (xattr live + all snapshots)
# -----------------------------------------------------------------------------


# Public decoder re-exports — back-compat for callers that imported them
# from this module before the cross-platform refactor split decoders into
# scripts/_file_metadata.py.
decode_quarantine = _file_metadata.decode_quarantine


def decode_wherefroms_from_hex(raw_hex: str) -> list[str]:
    """Decode hex-encoded binary plist to URL list. Empty on failure.

    Back-compat wrapper around `_file_metadata.decode_wherefroms`. The
    new function accepts both the legacy hex-string form and the
    `hex:`-prefixed form produced by `os.getxattr`.
    """
    return _file_metadata.decode_wherefroms(raw_hex)


def live_xattr(path: Path, repo_root: Path) -> dict[str, Any]:
    """Read live file metadata cross-platform; decode known formats.

    `repo_root` is unused (kept in the signature for back-compat with
    callers that pass it). Returns a superset of the legacy shape:
    `present`, `attribute_names`, `download_urls`, `quarantine` are the
    legacy fields; `platform`, `capability`, `referrer_url`,
    `download_timestamp_iso`, `zone`, `raw`, `decoded` are added by the
    cross-platform refactor.
    """
    del repo_root  # legacy parameter, kept for signature stability
    norm = _file_metadata.read_and_normalize(path)
    quarantine = norm["decoded"].get("quarantine")
    return {
        # Legacy fields (preserved for back-compat).
        "present": norm["present"],
        "attribute_names": norm["attribute_names"],
        "download_urls": list(norm["origin_urls"]),
        "quarantine": quarantine,
        # New cross-platform fields.
        "platform": norm["platform"],
        "capability": norm["capability"],
        "referrer_url": norm["referrer_url"],
        "download_timestamp_iso": norm["download_timestamp_iso"],
        "zone": norm["zone"],
        "raw": norm["raw"],
        "decoded": norm["decoded"],
    }


def all_snapshot_entries(snapshot_dir: Path, basename: str) -> list[dict[str, Any]]:
    """Walk every snapshot file; return every entry matching `basename`.

    Supports both the JSON snapshot format
    (`provenance_snapshot.py` current output — `{entries: [{path, xattrs,
    ...}, ...]}`) and the legacy text format
    (`File: <path>` / `====` dividers / xattr block) from the source
    project.
    """
    entries: list[dict[str, Any]] = []
    if not snapshot_dir.exists():
        return entries
    for sf in sorted(snapshot_dir.iterdir()):
        if not sf.is_file():
            continue
        suffix = sf.suffix.lower()
        try:
            if suffix == ".json":
                entries.extend(_json_snapshot_entries(sf, basename))
            elif suffix == ".txt":
                entries.extend(_text_snapshot_entries(sf, basename))
        except (OSError, json.JSONDecodeError):
            continue
    return entries


def _json_snapshot_entries(sf: Path, basename: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with sf.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    for e in data.get("entries", []) or []:
        p = str(e.get("path", ""))
        if Path(p).name == basename:
            out.append(
                {
                    "snapshot": str(sf),
                    "captured_at": data.get("captured_at"),
                    "filename_in_snapshot": p,
                    "xattrs": e.get("xattrs", {}) or {},
                    "mtime": e.get("mtime"),
                    "size": e.get("size"),
                }
            )
    return out


def _text_snapshot_entries(sf: Path, basename: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    text = sf.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"^={10,}\s*\n", text, flags=re.MULTILINE)
    for i, block in enumerate(blocks):
        lines = block.splitlines()
        if not lines:
            continue
        if lines[0].startswith("File: "):
            filename = lines[0][len("File: "):].strip()
            if Path(filename).name == basename:
                body = blocks[i + 1] if i + 1 < len(blocks) else ""
                body = body.split("\n========================================", 1)[0]
                out.append(
                    {
                        "snapshot": str(sf),
                        "filename_in_snapshot": filename,
                        "body": body.rstrip(),
                    }
                )
    return out


def section_download(
    path: Path, snapshot_dir: Path, report: Report
) -> dict[str, Any]:
    live = live_xattr(path, report.repo_root)
    snaps = all_snapshot_entries(snapshot_dir, path.name)
    if not live["present"] and not snaps:
        report.warn(
            "no download provenance (no live xattr on disk, "
            "no snapshot entry for this basename)"
        )
    return {"live": live, "snapshots": snaps}


# -----------------------------------------------------------------------------
# Section 5: Pipeline dispatcher
# -----------------------------------------------------------------------------


def section_pipeline(
    path: Path, pipeline_config: Path, report: Report
) -> dict[str, Any]:
    """Dispatch to a pipeline handler via data/pipeline_dispatch.yaml."""
    from scripts.provenance_handlers import dispatch

    return dispatch(path, pipeline_config, report)


# -----------------------------------------------------------------------------
# Section 6: Verdict
# -----------------------------------------------------------------------------


def section_verdict(
    report: Report,
    identity: dict[str, Any],
    git: dict[str, Any],
    manifest: dict[str, Any],
    download: dict[str, Any],
) -> str:
    """One-line human summary combining sections 1–4."""
    bits: list[str] = []
    n = git["commit_count"]
    content_changes = git.get("content_change_count", 0)
    under_evidence = report.under_evidence
    if n == 0:
        bits.append("git: ⚠ untracked")
    elif under_evidence and content_changes > 0:
        bits.append(f"git: ⚠ {content_changes} content edit(s)")
    elif under_evidence and n == 1:
        bits.append("git: add-only ✓")
    elif under_evidence and n > 1:
        bits.append(f"git: {n} commits (renames only) ✓")
    else:
        bits.append(f"git: {n} commit(s)")
    if manifest.get("applies"):
        if manifest.get("matches") is True:
            bits.append("hash: matches manifest ✓")
        elif manifest.get("matches") is False:
            bits.append("hash: ⚠ MISMATCH")
        else:
            bits.append("hash: ⚠ not in manifest")
    live_present = download["live"]["present"]
    snap_count = len(download["snapshots"])
    if live_present and snap_count:
        bits.append(f"xattr: live + {snap_count} snapshot(s) ✓")
    elif snap_count:
        bits.append(f"xattr: snapshot-only ({snap_count})")
    elif live_present:
        bits.append("xattr: live-only (not yet snapshotted)")
    else:
        bits.append("xattr: none")
    return "; ".join(bits)


# -----------------------------------------------------------------------------
# Build report
# -----------------------------------------------------------------------------


def build_report(
    path: Path,
    *,
    repo_root: Path,
    evidence_root: Path,
    manifest_path: Path,
    snapshot_dir: Path,
    pipeline_config: Path,
) -> Report:
    """Assemble the 6-section report for one file."""
    rel = path.resolve().relative_to(repo_root).as_posix()
    report = Report(
        abs_path=str(path.resolve()),
        rel_path=rel,
        repo_root=repo_root.resolve(),
        evidence_root=evidence_root.resolve(),
    )

    identity = section_identity(path, report)
    report.sections["identity"] = identity

    git_info = section_git(path, report)
    report.sections["git_trail"] = git_info

    manifest_info = section_manifest(path, identity, manifest_path, report)
    report.sections["hash_manifest"] = manifest_info

    download = section_download(path, snapshot_dir, report)
    report.sections["download"] = download

    report.sections["pipeline"] = section_pipeline(path, pipeline_config, report)

    report.sections["verdict"] = section_verdict(
        report, identity, git_info, manifest_info, download
    )
    return report


# -----------------------------------------------------------------------------
# Output formatters
# -----------------------------------------------------------------------------


def format_human(report: Report) -> str:
    """Markdown-ish human-readable report."""
    lines: list[str] = []
    ident = report.sections["identity"]
    lines.append(f"# Provenance: {ident['rel_path']}")
    lines.append("")
    lines.append(f"**Verdict:** {report.sections['verdict']}")
    if report.warnings:
        lines.append("")
        lines.append("**Flags:**")
        for w in report.warnings:
            lines.append(f"- ⚠ {w}")
    lines.append("")

    # Identity
    lines.append("## Identity")
    lines.append(f"- path: `{ident['rel_path']}`")
    lines.append(f"- size: {ident['size_bytes']:,} bytes")
    lines.append(f"- sha256: `{ident['sha256']}`")
    lines.append(f"- git blob sha1: `{ident['git_blob_sha1'] or '(not tracked)'}`")
    lines.append(f"- git tracked: {ident['git_tracked']}")
    lines.append("")

    # Git trail
    lines.append("## Git trail")
    git = report.sections["git_trail"]
    if not git["commits"]:
        lines.append("- (no commits)")
    else:
        for c in git["commits"]:
            tag = {
                "initial": "[initial]",
                "content": "[⚠ content edit]",
                "rename-or-metadata": "[rename/metadata]",
            }.get(c.get("change_type", ""), "")
            path_note = ""
            if c.get("path_at_commit") and c["path_at_commit"] != report.rel_path:
                path_note = f"  (as `{c['path_at_commit']}`)"
            lines.append(
                f"- {c['short_sha']}  {c['date']}  {tag}  {c['subject']}{path_note}"
            )
    lines.append("")

    # Hash manifest
    lines.append("## Hash manifest")
    m = report.sections["hash_manifest"]
    if not m["applies"]:
        lines.append(
            "- not applicable (only files under the evidence root are "
            "covered by the hash manifest)"
        )
    else:
        lines.append(f"- manifest: `{m['manifest_path']}`")
        lines.append(f"- recorded: `{m['recorded_sha256'] or '(missing)'}`")
        lines.append(f"- on-disk:  `{ident['sha256']}`")
        lines.append(f"- matches:  {m['matches']}")
    lines.append("")

    # Download
    lines.append("## Download provenance")
    d = report.sections["download"]
    live = d["live"]
    capability = live.get("capability", "posix-xattr")
    if live["present"]:
        lines.append("- live xattr on disk:")
        lines.append(f"  - attributes: {', '.join(live['attribute_names'])}")
        for url in live["download_urls"]:
            lines.append(f"  - origin URL: {url}")
        if live.get("referrer_url"):
            lines.append(f"  - referrer: {live['referrer_url']}")
        if live.get("download_timestamp_iso"):
            lines.append(f"  - downloaded: {live['download_timestamp_iso']}")
        if live.get("zone"):
            lines.append(f"  - zone: {live['zone']}")
        if live["quarantine"]:
            q = live["quarantine"]
            lines.append(
                f"  - quarantine: app={q['app']}, ts={q['timestamp_iso']}, "
                f"uuid={q['uuid']}"
            )
    else:
        if capability == "unsupported":
            plat = live.get("platform", "?")
            lines.append(
                f"- live xattr: not supported on this platform ({plat})"
            )
        else:
            lines.append("- live xattr: none on disk")
    if d["snapshots"]:
        lines.append(f"- historical snapshots ({len(d['snapshots'])}):")
        for entry in d["snapshots"]:
            snap = entry.get("snapshot", "")
            lines.append(
                f"  - from `{snap}` (file: {entry.get('filename_in_snapshot', '?')})"
            )
            xattrs = entry.get("xattrs") or {}
            for name, val in xattrs.items():
                lines.append(f"      {name}: {val}")
            body = entry.get("body")
            if body:
                for line in body.splitlines():
                    if line.strip():
                        lines.append(f"      {line}")
    else:
        lines.append("- historical snapshots: none matching this basename")
    lines.append("")

    # Pipeline
    lines.append("## Pipeline provenance")
    p = report.sections["pipeline"]
    kind = p.get("kind", "none")
    lines.append(f"- kind: {kind}")
    # Surface all non-"kind" keys as a simple bullet list.
    for k, v in p.items():
        if k == "kind":
            continue
        if isinstance(v, (dict, list)):
            lines.append(f"- {k}:")
            _render_nested(lines, v, indent=1)
        else:
            lines.append(f"- {k}: {v}")
    lines.append("")
    return "\n".join(lines)


def _render_nested(lines: list[str], obj: Any, *, indent: int) -> None:
    pad = "  " * indent
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)) and v:
                lines.append(f"{pad}- {k}:")
                _render_nested(lines, v, indent=indent + 1)
            else:
                lines.append(f"{pad}- {k}: {v}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{pad}-")
                _render_nested(lines, item, indent=indent + 1)
            else:
                lines.append(f"{pad}- {item}")


def format_yaml(report: Report) -> str:
    """Hand-rolled YAML emitter so `--forensic` works without PyYAML.

    Regulator/attorney handoffs shouldn't require the recipient to
    install PyYAML to read the report.
    """
    def emit(value: Any, indent: int = 0) -> list[str]:
        pad = "  " * indent
        out: list[str] = []
        if isinstance(value, dict):
            if not value:
                out.append(f"{pad}{{}}")
                return out
            for k, v in value.items():
                if isinstance(v, (dict, list)) and v:
                    out.append(f"{pad}{k}:")
                    out.extend(emit(v, indent + 1))
                else:
                    out.append(f"{pad}{k}: {_scalar(v)}")
        elif isinstance(value, list):
            if not value:
                out.append(f"{pad}[]")
                return out
            for item in value:
                if isinstance(item, (dict, list)) and item:
                    sublines = emit(item, indent + 1)
                    if sublines:
                        first = sublines[0].lstrip()
                        out.append(f"{pad}- {first}")
                        out.extend(sublines[1:])
                else:
                    out.append(f"{pad}- {_scalar(item)}")
        else:
            out.append(f"{pad}{_scalar(value)}")
        return out

    def _scalar(v: Any) -> str:
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        s = str(v)
        if (
            any(ch in s for ch in (":", "#", "\n", '"', "'"))
            or s.strip() != s
            or s == ""
        ):
            return json.dumps(s, ensure_ascii=False)
        return s

    payload = {
        "rel_path": report.rel_path,
        "abs_path": report.abs_path,
        "warnings": report.warnings,
        "sections": report.sections,
    }
    return "\n".join(emit(payload)) + "\n"


# -----------------------------------------------------------------------------
# Config resolution
# -----------------------------------------------------------------------------


def _resolve_paths(
    cfg: Config, args: argparse.Namespace
) -> tuple[Path, Path, Path, Path]:
    """Resolve (repo_root, evidence_root, manifest_path, snapshot_dir)."""
    repo_root = cfg.repo_root
    evidence_root = (
        args.evidence_root.resolve() if args.evidence_root else cfg.evidence_root
    )
    manifest_path = (
        args.hash_manifest.resolve() if args.hash_manifest else cfg.manifest_path
    )
    snapshot_dir = (
        args.snapshot_dir.resolve() if args.snapshot_dir else cfg.snapshot_dir
    )

    # Auto-fallback for examples where the config's evidence_root doesn't
    # match the target file's location: look for a sibling `evidence/`
    # directory next to the manifest.
    if not evidence_root.exists() and manifest_path.exists():
        sibling = manifest_path.parent / "evidence"
        if sibling.exists():
            evidence_root = sibling.resolve()

    return repo_root, evidence_root, manifest_path, snapshot_dir


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------


DEFAULT_PIPELINE_CONFIG = Path("data/pipeline_dispatch.yaml")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Per-file forensic provenance inspection.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("path", type=Path, help="Path to a file in the repo.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        "--forensic", action="store_true", help="YAML output for external handoff."
    )
    mode.add_argument(
        "--verify",
        action="store_true",
        help="Silent unless warnings; exit 1 on any ⚠.",
    )
    ap.add_argument(
        "--hash-manifest", type=Path, help="Hash manifest path (default from config)."
    )
    ap.add_argument(
        "--snapshot-dir",
        type=Path,
        help="Historical snapshot directory (default from config).",
    )
    ap.add_argument(
        "--evidence-root",
        type=Path,
        help="Evidence root (default from config; auto-falls back to "
        "manifest's sibling `evidence/` dir).",
    )
    ap.add_argument(
        "--pipeline-config",
        type=Path,
        default=None,
        help="Pipeline dispatch YAML (default: data/pipeline_dispatch.yaml).",
    )
    ap.add_argument("--repo-root", type=Path, help="Repo root.")
    ap.add_argument("--config", type=Path, help="Path to advocacy.toml.")
    args = ap.parse_args(argv)

    p = Path(args.path).resolve()
    if not p.exists():
        print(f"error: {p} does not exist", file=sys.stderr)
        return 2
    if not p.is_file():
        print(f"error: {p} is not a regular file", file=sys.stderr)
        return 2

    cfg = load_config(repo_root=args.repo_root, config_path=args.config)
    try:
        p.relative_to(cfg.repo_root)
    except ValueError:
        print(
            f"error: {p} is outside the repo ({cfg.repo_root})", file=sys.stderr
        )
        return 2

    repo_root, evidence_root, manifest_path, snapshot_dir = _resolve_paths(cfg, args)
    pipeline_config = (
        args.pipeline_config.resolve()
        if args.pipeline_config
        else (repo_root / DEFAULT_PIPELINE_CONFIG).resolve()
    )

    report = build_report(
        p,
        repo_root=repo_root,
        evidence_root=evidence_root,
        manifest_path=manifest_path,
        snapshot_dir=snapshot_dir,
        pipeline_config=pipeline_config,
    )

    if args.verify:
        if report.warnings:
            for w in report.warnings:
                print(f"⚠ {w}", file=sys.stderr)
            return 1
        return 0
    if args.forensic:
        sys.stdout.write(format_yaml(report))
    else:
        sys.stdout.write(format_human(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
