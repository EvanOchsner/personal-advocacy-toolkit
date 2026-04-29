#!/usr/bin/env python3
"""Capture a per-file provenance snapshot for a tree.

For every file under `--root`, record:
- relative path
- size
- mtime (POSIX)
- SHA-256 digest
- file metadata, cross-platform: macOS xattrs
  (`com.apple.metadata:kMDItemWhereFroms`, `com.apple.quarantine`),
  Linux XDG xattrs (`user.xdg.origin.url`, `user.xdg.referrer.url`),
  and Windows NTFS Zone.Identifier ADS (under a synthetic
  `win.zone_identifier` key). Empty if the platform offers no
  mechanism or the file has nothing.

The result is written as a single JSON file under
`provenance.snapshot_dir` (default `provenance/snapshots/`) named
`<UTC-timestamp>.json`. The snapshot directory is intended to be
committed — it gives a regulator a cryptographic "where this file came
from and when we first saw it" fingerprint.

Cross-platform notes:
- macOS auto-populates xattrs for downloaded files (Safari, Mail,
  Finder). Forensic gold.
- Windows auto-populates Zone.Identifier on NTFS for any file
  downloaded via IE/Edge/Chrome/Firefox/Outlook. Equally rich.
- Linux populates XDG attrs only for Firefox downloads, and only on
  filesystems that support xattrs. Often empty in practice; that's
  fine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts._config import load_config
from scripts._file_metadata import read_raw


CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def read_xattrs(path: Path) -> dict[str, str]:
    """Return platform-appropriate file metadata as a name->str dict.

    Thin wrapper around `_file_metadata.read_raw` preserved under the
    historical name. POSIX xattrs land under their native names;
    Windows NTFS Zone.Identifier ADS lands under the synthetic key
    `win.zone_identifier` so the snapshot JSON schema stays uniform.
    Values that are not UTF-8 decodable are hex-prefixed (`hex:...`).
    """
    return read_raw(path)


def snapshot_tree(root: Path) -> list[dict]:
    entries: list[dict] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        st = p.stat()
        entries.append(
            {
                "path": rel,
                "size": st.st_size,
                "mtime": st.st_mtime,
                "sha256": sha256_file(p),
                "xattrs": read_xattrs(p),
            }
        )
    return entries


def write_snapshot(snapshot_dir: Path, root: Path, entries: list[dict]) -> Path:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = snapshot_dir / f"{ts}.json"
    payload = {
        "schema": "advocacy-toolkit/provenance-snapshot/v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "count": len(entries),
        "entries": entries,
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, help="Directory to snapshot.")
    ap.add_argument("--snapshot-dir", type=Path, help="Where to write the snapshot.")
    ap.add_argument("--config", type=Path, help="Path to advocacy.toml.")
    ap.add_argument("--repo-root", type=Path, help="Repo root.")
    args = ap.parse_args(argv)

    cfg = load_config(repo_root=args.repo_root, config_path=args.config)
    root = (args.root or cfg.evidence_root).resolve()
    snap_dir = (args.snapshot_dir or cfg.snapshot_dir).resolve()

    if not root.exists():
        print(f"root does not exist: {root}", file=sys.stderr)
        return 2

    entries = snapshot_tree(root)
    out = write_snapshot(snap_dir, root, entries)
    print(f"wrote {len(entries)} entries to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
