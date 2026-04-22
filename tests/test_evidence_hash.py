"""Smoke tests for scripts.evidence_hash.

All fixtures are synthetic and built inline — no real case data.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from scripts import evidence_hash


def _write(p: Path, data: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def test_build_and_verify_manifest(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root / "a.txt", b"hello\n")
    _write(root / "sub" / "b.bin", b"\x00\x01\x02")

    manifest = tmp_path / "MANIFEST.sha256"
    rc = evidence_hash.main(
        [
            "--root", str(root),
            "--manifest", str(manifest),
            "--repo-root", str(tmp_path),
        ]
    )
    assert rc == 0
    assert manifest.exists()

    rows = evidence_hash.read_manifest(manifest)
    paths = {rel for _, rel in rows}
    assert paths == {"a.txt", "sub/b.bin"}

    # Digests match stdlib output.
    want = hashlib.sha256(b"hello\n").hexdigest()
    got = dict((rel, d) for d, rel in rows)["a.txt"]
    assert got == want

    # Verify mode succeeds.
    rc = evidence_hash.main(
        [
            "--root", str(root),
            "--manifest", str(manifest),
            "--repo-root", str(tmp_path),
            "--verify",
        ]
    )
    assert rc == 0


def test_verify_detects_mutation(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root / "a.txt", b"original")
    manifest = tmp_path / "MANIFEST.sha256"
    evidence_hash.main(
        ["--root", str(root), "--manifest", str(manifest), "--repo-root", str(tmp_path)]
    )

    # Tamper.
    (root / "a.txt").write_bytes(b"tampered")

    rc = evidence_hash.main(
        [
            "--root", str(root),
            "--manifest", str(manifest),
            "--repo-root", str(tmp_path),
            "--verify",
        ]
    )
    assert rc == 1


def test_check_flags_untracked(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root / "a.txt", b"x")
    manifest = tmp_path / "MANIFEST.sha256"
    evidence_hash.main(
        ["--root", str(root), "--manifest", str(manifest), "--repo-root", str(tmp_path)]
    )

    _write(root / "extra.txt", b"surprise")

    rc_verify = evidence_hash.main(
        ["--root", str(root), "--manifest", str(manifest), "--repo-root", str(tmp_path), "--verify"]
    )
    assert rc_verify == 0  # verify ignores untracked

    rc_check = evidence_hash.main(
        ["--root", str(root), "--manifest", str(manifest), "--repo-root", str(tmp_path), "--check"]
    )
    assert rc_check == 1


def test_exclude_patterns(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root / "good.txt", b"1")
    _write(root / ".DS_Store", b"junk")
    manifest = tmp_path / "MANIFEST.sha256"
    evidence_hash.main(
        ["--root", str(root), "--manifest", str(manifest), "--repo-root", str(tmp_path)]
    )
    paths = {rel for _, rel in evidence_hash.read_manifest(manifest)}
    assert paths == {"good.txt"}


def test_config_file_sets_defaults(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root / "a.txt", b"hi")
    manifest = tmp_path / "custom_manifest.sha256"
    cfg = tmp_path / "advocacy.toml"
    cfg.write_text(
        f'[evidence]\n'
        f'root = "evidence"\n'
        f'manifest = "custom_manifest.sha256"\n'
    )
    rc = evidence_hash.main(["--repo-root", str(tmp_path), "--config", str(cfg)])
    assert rc == 0
    assert manifest.exists()
