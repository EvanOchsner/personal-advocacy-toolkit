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


def test_report_assigns_verdicts(tmp_path: Path) -> None:
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
    provenance.main(
        [
            "--manifest", str(manifest),
            "--snapshot-dir", str(snap_dir),
            "--out", str(out),
            "--repo-root", str(repo),
        ]
    )
    data = json.loads(out.read_text())
    entry = data["files"][0]
    assert "verdict" in entry
    assert "reason_codes" in entry
    assert "verdict_counts" in data
    # Without git tracking, the verdict may warn on `git-untracked`; with
    # a full snapshot and matching hash, it must never be `fail`.
    assert entry["verdict"] != "fail"


def test_report_flags_missing_file_as_fail(tmp_path: Path) -> None:
    repo = tmp_path
    evidence = repo / "evidence"
    evidence.mkdir()
    (evidence / "a.txt").write_bytes(b"alpha")

    manifest = repo / "MANIFEST.sha256"
    evidence_hash.main(
        ["--root", str(evidence), "--manifest", str(manifest), "--repo-root", str(repo)]
    )
    (evidence / "a.txt").unlink()

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
    assert entry["verdict"] == "fail"
    assert "missing-on-disk" in entry["reason_codes"]


def test_report_flags_sha_mismatch_in_forensic_mode(tmp_path: Path) -> None:
    repo = tmp_path
    evidence = repo / "evidence"
    evidence.mkdir()
    (evidence / "a.txt").write_bytes(b"alpha")

    manifest = repo / "MANIFEST.sha256"
    evidence_hash.main(
        ["--root", str(evidence), "--manifest", str(manifest), "--repo-root", str(repo)]
    )
    # Mutate the file in place so its digest no longer matches the manifest.
    (evidence / "a.txt").write_bytes(b"tampered")

    out = repo / "report.yaml"
    provenance.main(
        [
            "--manifest", str(manifest),
            "--snapshot-dir", str(repo / "snaps"),
            "--out", str(out),
            "--repo-root", str(repo),
            "--forensic",
        ]
    )
    text = out.read_text()
    assert "sha-mismatch" in text
    assert "verdict" in text


def test_verify_passes_on_match_and_fails_on_mismatch(tmp_path: Path) -> None:
    repo = tmp_path
    evidence = repo / "evidence"
    evidence.mkdir()
    (evidence / "a.txt").write_bytes(b"alpha")

    manifest = repo / "MANIFEST.sha256"
    evidence_hash.main(
        ["--root", str(evidence), "--manifest", str(manifest), "--repo-root", str(repo)]
    )
    rc = provenance.main(
        [
            "--manifest", str(manifest),
            "--snapshot-dir", str(repo / "snaps"),
            "--repo-root", str(repo),
            "--verify",
        ]
    )
    assert rc == 0

    (evidence / "a.txt").write_bytes(b"tampered")
    rc = provenance.main(
        [
            "--manifest", str(manifest),
            "--snapshot-dir", str(repo / "snaps"),
            "--repo-root", str(repo),
            "--verify",
        ]
    )
    assert rc != 0


def test_decode_quarantine_parses_fields() -> None:
    raw = "0081;5f2b1c00;Safari;ABCDEF01-2345-6789-ABCD-EF0123456789"
    decoded = provenance.decode_quarantine(raw)
    assert decoded["flags"] == "0081"
    assert decoded["agent"] == "Safari"
    assert decoded["uuid"] == "ABCDEF01-2345-6789-ABCD-EF0123456789"
    assert "timestamp" in decoded


def test_forensic_on_mustang_fixture_every_entry_has_verdict(tmp_path: Path) -> None:
    """End-to-end smoke against the synthetic Mustang example tree."""
    repo = Path(__file__).resolve().parents[1]
    manifest = repo / "examples/mustang-in-maryland/.evidence-manifest.sha256"
    snap_dir = repo / "examples/mustang-in-maryland/provenance/snapshots"
    if not manifest.exists() or not snap_dir.exists():
        return  # example tree not present in this checkout

    out = tmp_path / "mustang-forensic.yaml"
    rc = provenance.main(
        [
            "--manifest", str(manifest),
            "--snapshot-dir", str(snap_dir),
            "--out", str(out),
            "--repo-root", str(repo),
            "--forensic",
        ]
    )
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    # YAML output.
    assert "schema:" in text
    # Every entry must carry a verdict.
    verdict_count = text.count("verdict:")
    # One verdict per file, plus we also emit `verdict_counts:` at the top.
    assert verdict_count >= 2
    # The fixture hashes on disk match the manifest today, so no sha
    # mismatches should be reported in forensic mode.
    assert "sha-mismatch" not in text


def test_verify_on_mustang_fixture_passes(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    manifest = repo / "examples/mustang-in-maryland/.evidence-manifest.sha256"
    snap_dir = repo / "examples/mustang-in-maryland/provenance/snapshots"
    if not manifest.exists() or not snap_dir.exists():
        return
    rc = provenance.main(
        [
            "--manifest", str(manifest),
            "--snapshot-dir", str(snap_dir),
            "--verify",
            "--repo-root", str(repo),
        ]
    )
    assert rc == 0


def test_decode_wherefroms_parses_plist() -> None:
    import plistlib
    payload = plistlib.dumps(["https://example.com/post", "https://example.com/file.pdf"])
    decoded = provenance.decode_wherefroms("hex:" + payload.hex())
    assert decoded["urls"] == [
        "https://example.com/post",
        "https://example.com/file.pdf",
    ]
