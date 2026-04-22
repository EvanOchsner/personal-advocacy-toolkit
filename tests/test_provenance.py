"""Smoke tests for scripts.provenance (unified report)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import evidence_hash, provenance, provenance_snapshot


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    )


def test_report_joins_manifest_and_snapshot(tmp_path: Path) -> None:
    repo = tmp_path
    evidence = repo / "evidence"
    evidence.mkdir()
    (evidence / "a.txt").write_bytes(b"alpha")

    manifest = repo / "MANIFEST.sha256"
    evidence_hash.main(
        ["--root", str(evidence), "--manifest", str(manifest), "--repo-root", str(repo)]
    )
    snap_dir = repo / "snaps"
    provenance_snapshot.main(
        ["--root", str(evidence), "--snapshot-dir", str(snap_dir), "--repo-root", str(repo)]
    )

    out = repo / "report.json"
    rc = provenance.main(
        [
            "--manifest", str(manifest),
            "--snapshot-dir", str(snap_dir),
            "--out", str(out),
            "--repo-root", str(repo),
        ]
    )
    assert rc == 0

    data = json.loads(out.read_text())
    assert data["schema"] == "advocacy-toolkit/provenance-report/v1"
    assert data["count"] == 1
    entry = data["files"][0]
    assert entry["path"] == "a.txt"
    assert "sha256" in entry
    # Snapshot join present.
    assert entry["size"] == 5
    assert "xattrs" in entry


def test_report_includes_git_history_when_present(tmp_path: Path) -> None:
    repo = tmp_path
    evidence = repo / "evidence"
    evidence.mkdir()
    (evidence / "a.txt").write_bytes(b"hi")

    try:
        _git(repo, "init", "-b", "main")
        _git(repo, "config", "user.email", "t@example.invalid")
        _git(repo, "config", "user.name", "Test")
        _git(repo, "add", "evidence/a.txt")
        _git(repo, "commit", "-m", "add a")
    except (FileNotFoundError, subprocess.CalledProcessError):
        # git not available — the non-git case is already covered above.
        return

    manifest = repo / "MANIFEST.sha256"
    evidence_hash.main(
        ["--root", str(evidence), "--manifest", str(manifest), "--repo-root", str(repo)]
    )
    out = repo / "report.json"
    provenance.main(
        [
            "--manifest", str(manifest),
            "--snapshot-dir", str(repo / "snaps"),
            "--out", str(out),
            "--repo-root", str(repo),
        ]
    )
    data = json.loads(out.read_text())
    entry = data["files"][0]
    assert "git" in entry
    assert entry["git"]["added"] is not None
    assert entry["git"]["last_touched"] is not None


def test_report_includes_pipeline_sidecar(tmp_path: Path) -> None:
    repo = tmp_path
    evidence = repo / "evidence"
    evidence.mkdir()
    (evidence / "a.txt").write_bytes(b"hi")
    (evidence / "a.txt.meta.json").write_text(
        json.dumps({"tool": "email_eml_to_json", "version": "0.1"})
    )

    manifest = repo / "MANIFEST.sha256"
    evidence_hash.main(
        ["--root", str(evidence), "--manifest", str(manifest), "--repo-root", str(repo)]
    )
    out = repo / "report.json"
    provenance.main(
        [
            "--manifest", str(manifest),
            "--snapshot-dir", str(repo / "snaps"),
            "--out", str(out),
            "--repo-root", str(repo),
        ]
    )
    data = json.loads(out.read_text())
    by_path = {e["path"]: e for e in data["files"]}
    # The .meta.json file itself is in the manifest, but the real file
    # `a.txt` should have its pipeline sidecar joined in.
    assert "pipeline" in by_path["a.txt"]
    assert by_path["a.txt"]["pipeline"]["tool"] == "email_eml_to_json"
