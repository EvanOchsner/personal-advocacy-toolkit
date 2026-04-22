"""Smoke tests for scripts.provenance_snapshot."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts import provenance_snapshot


def test_snapshot_captures_files(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_bytes(b"alpha")
    (root / "sub" / "b.txt").write_bytes(b"beta")

    snap_dir = tmp_path / "snaps"
    rc = provenance_snapshot.main(
        [
            "--root", str(root),
            "--snapshot-dir", str(snap_dir),
            "--repo-root", str(tmp_path),
        ]
    )
    assert rc == 0
    files = list(snap_dir.glob("*.json"))
    assert len(files) == 1

    payload = json.loads(files[0].read_text())
    assert payload["schema"] == "advocacy-toolkit/provenance-snapshot/v1"
    assert payload["count"] == 2

    by_path = {e["path"]: e for e in payload["entries"]}
    assert set(by_path) == {"a.txt", "sub/b.txt"}
    assert by_path["a.txt"]["sha256"] == hashlib.sha256(b"alpha").hexdigest()
    # xattrs present as a dict (possibly empty on Linux).
    assert isinstance(by_path["a.txt"]["xattrs"], dict)
    assert by_path["a.txt"]["size"] == 5


def test_missing_root_returns_error(tmp_path: Path) -> None:
    rc = provenance_snapshot.main(
        [
            "--root", str(tmp_path / "does-not-exist"),
            "--snapshot-dir", str(tmp_path / "snaps"),
            "--repo-root", str(tmp_path),
        ]
    )
    assert rc == 2
