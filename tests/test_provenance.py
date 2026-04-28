"""Tests for scripts.provenance (per-file tool) + scripts.provenance_bundle.

The aggregate-mode API from Phase 6 has been replaced with the source
project's per-file shape — see
~/.claude/plans/validated-conjuring-balloon.md Track B for rationale.
"""
from __future__ import annotations

import hashlib
import json
import plistlib
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")


from scripts import provenance  # noqa: E402
from scripts import provenance_bundle  # noqa: E402
from scripts.provenance import (  # noqa: E402
    Report,
    build_report,
    decode_quarantine,
    decode_wherefroms_from_hex,
    format_human,
    format_yaml,
)


# -----------------------------------------------------------------------------
# Fixture helpers
# -----------------------------------------------------------------------------


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    return repo


def _commit_file(repo: Path, rel: str, body: str, msg: str) -> str:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


# -----------------------------------------------------------------------------
# Section unit tests
# -----------------------------------------------------------------------------


def test_build_report_returns_six_sections(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    ev = repo / "evidence"
    ev.mkdir()
    body = "hello, provenance\n"
    _commit_file(repo, "evidence/a.txt", body, "add a")

    rep = build_report(
        repo / "evidence" / "a.txt",
        repo_root=repo,
        evidence_root=ev,
        manifest_path=ev / "missing-manifest.sha256",
        snapshot_dir=ev / "missing-snapshots",
        pipeline_config=repo / "data" / "pipeline_dispatch.yaml",
    )
    assert set(rep.sections.keys()) == {
        "identity",
        "git_trail",
        "hash_manifest",
        "download",
        "pipeline",
        "verdict",
    }
    assert rep.sections["identity"]["sha256"] == _sha256(body)
    assert rep.sections["identity"]["git_tracked"] is True
    assert rep.sections["git_trail"]["commit_count"] == 1
    assert rep.sections["git_trail"]["commits"][0]["change_type"] == "initial"


def test_git_trail_flags_content_edits_under_evidence(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    ev = repo / "evidence"
    ev.mkdir()
    _commit_file(repo, "evidence/a.txt", "v1\n", "add a")
    _commit_file(repo, "evidence/a.txt", "v2\n", "edit a")

    rep = build_report(
        repo / "evidence" / "a.txt",
        repo_root=repo,
        evidence_root=ev,
        manifest_path=ev / "m.sha256",
        snapshot_dir=ev / "snaps",
        pipeline_config=repo / "data" / "pipeline_dispatch.yaml",
    )
    assert rep.sections["git_trail"]["content_change_count"] == 1
    assert any("content change" in w for w in rep.warnings)
    assert "content edit" in rep.sections["verdict"]


def test_hash_manifest_mismatch_flags_warning(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    ev = repo / "evidence"
    ev.mkdir()
    _commit_file(repo, "evidence/a.txt", "actual body\n", "add a")
    manifest = ev / "m.sha256"
    manifest.write_text("deadbeef" * 8 + "  a.txt\n")

    rep = build_report(
        repo / "evidence" / "a.txt",
        repo_root=repo,
        evidence_root=ev,
        manifest_path=manifest,
        snapshot_dir=ev / "snaps",
        pipeline_config=repo / "data" / "pipeline_dispatch.yaml",
    )
    assert rep.sections["hash_manifest"]["matches"] is False
    assert any("HASH MISMATCH" in w for w in rep.warnings)


def test_verify_returns_nonzero_on_warning(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    ev = repo / "evidence"
    ev.mkdir()
    _commit_file(repo, "evidence/a.txt", "body\n", "add a")
    manifest = ev / "m.sha256"
    manifest.write_text("deadbeef" * 8 + "  a.txt\n")

    rc = provenance.main(
        [
            str(repo / "evidence" / "a.txt"),
            "--evidence-root", str(ev),
            "--hash-manifest", str(manifest),
            "--snapshot-dir", str(ev / "snaps"),
            "--repo-root", str(repo),
            "--verify",
        ]
    )
    assert rc == 1


# -----------------------------------------------------------------------------
# Decoder tests
# -----------------------------------------------------------------------------


def test_decode_quarantine_parses_fields() -> None:
    raw = "0081;67380000;Safari;ABCD-1234-5678"
    out = decode_quarantine(raw)
    assert out is not None
    assert out["flag"] == "0081"
    assert out["app"] == "Safari"
    assert out["uuid"] == "ABCD-1234-5678"
    assert out["timestamp_iso"] is not None


def test_decode_wherefroms_parses_hex_bplist() -> None:
    urls = ["https://example.com/form", "https://example.com/index"]
    bplist = plistlib.dumps(urls, fmt=plistlib.FMT_BINARY)
    hex_blob = bplist.hex()
    assert decode_wherefroms_from_hex(hex_blob) == urls


def test_decode_wherefroms_handles_garbage() -> None:
    assert decode_wherefroms_from_hex("not-hex") == []
    assert decode_wherefroms_from_hex("deadbeef") == []


# -----------------------------------------------------------------------------
# Pipeline dispatcher
# -----------------------------------------------------------------------------


def test_pipeline_dispatches_email_three_layer(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    ev = repo / "evidence"
    (ev / "emails" / "raw").mkdir(parents=True)
    (ev / "emails" / "structured").mkdir(parents=True)
    (ev / "emails" / "readable").mkdir(parents=True)

    raw = ev / "emails" / "raw" / "001_2025-03-16_first-message.eml"
    raw.write_text("From: a@example.com\n")
    sibling = ev / "emails" / "structured" / "001_2025-03-16_first-message.json"
    sibling.write_text(
        json.dumps(
            {
                "message_id": "<001@example.com>",
                "from": "a@example.com",
                "subject": "hi",
                "date": "2025-03-16T09:00Z",
            }
        )
    )
    _git(repo, "add", "evidence")
    _git(repo, "commit", "-q", "-m", "add emails")

    cfg = tmp_path / "pipeline.yaml"
    cfg.write_text(
        "rules:\n"
        "  - path_prefix: \"emails/\"\n"
        "    extensions: [\".eml\", \".json\", \".txt\"]\n"
        "    handler: email_three_layer\n"
        "    config:\n"
        "      filename_stem_re: \"^(\\\\d+)_(\\\\d{4}-\\\\d{2}-\\\\d{2})_(.+)$\"\n"
        "      json_layer_dir: \"structured\"\n"
        "      raw_layer_dir: \"raw\"\n"
        "      readable_layer_dir: \"readable\"\n"
    )

    rep = build_report(
        raw,
        repo_root=repo,
        evidence_root=ev,
        manifest_path=ev / "m.sha256",
        snapshot_dir=ev / "snaps",
        pipeline_config=cfg,
    )
    pipe = rep.sections["pipeline"]
    assert pipe["kind"] == "email-three-layer"
    assert pipe["stem"] == "001_2025-03-16_first-message"
    assert pipe["message_id"] == "<001@example.com>"
    assert "json_sibling" in pipe


def test_pipeline_falls_through_when_no_rule_matches(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    ev = repo / "evidence"
    ev.mkdir()
    _commit_file(repo, "evidence/random.bin", "\x00\x01", "add bin")
    cfg = tmp_path / "pipeline.yaml"
    cfg.write_text("rules: []\n")

    rep = build_report(
        repo / "evidence" / "random.bin",
        repo_root=repo,
        evidence_root=ev,
        manifest_path=ev / "m.sha256",
        snapshot_dir=ev / "snaps",
        pipeline_config=cfg,
    )
    assert rep.sections["pipeline"]["kind"] == "none"


# -----------------------------------------------------------------------------
# Output formatters
# -----------------------------------------------------------------------------


def test_format_yaml_works_without_pyyaml_available() -> None:
    """The emitter has a stdlib-only fallback so regulators/attorneys
    can read `--forensic` output without installing PyYAML."""
    report = Report(
        abs_path="/tmp/x",
        rel_path="x",
        repo_root=Path("/tmp"),
        evidence_root=Path("/tmp/evidence"),
    )
    report.sections["identity"] = {"sha256": "abc", "size_bytes": 42}
    report.sections["verdict"] = "git: add-only ✓"
    out = format_yaml(report)
    assert "rel_path:" in out
    assert "identity:" in out
    assert "sha256:" in out


def test_format_human_renders_verdict_and_flags() -> None:
    report = Report(
        abs_path="/tmp/x",
        rel_path="x",
        repo_root=Path("/tmp"),
        evidence_root=Path("/tmp/evidence"),
    )
    report.warn("example warning")
    report.sections["identity"] = {
        "rel_path": "x",
        "size_bytes": 10,
        "sha256": "a" * 64,
        "git_blob_sha1": "b" * 40,
        "git_tracked": True,
    }
    report.sections["git_trail"] = {
        "commits": [],
        "commit_count": 0,
        "content_change_count": 0,
    }
    report.sections["hash_manifest"] = {"applies": False}
    report.sections["download"] = {
        "live": {
            "present": False,
            "attribute_names": [],
            "download_urls": [],
            "quarantine": None,
        },
        "snapshots": [],
    }
    report.sections["pipeline"] = {"kind": "none"}
    report.sections["verdict"] = "git: ⚠ untracked; xattr: none"
    out = format_human(report)
    assert "**Verdict:**" in out
    assert "example warning" in out
    assert "## Identity" in out


# -----------------------------------------------------------------------------
# Bundle
# -----------------------------------------------------------------------------


def test_bundle_on_synthetic_tree(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    ev = repo / "evidence"
    ev.mkdir()
    _commit_file(repo, "evidence/a.txt", "aaa\n", "add a")
    _commit_file(repo, "evidence/b.txt", "bbb\n", "add b")

    manifest = repo / ".evidence-manifest.sha256"
    a_hash = _sha256("aaa\n")
    b_hash = _sha256("bbb\n")
    manifest.write_text(f"{a_hash}  a.txt\n{b_hash}  b.txt\n")
    pipeline_cfg = tmp_path / "pipeline.yaml"
    pipeline_cfg.write_text("rules: []\n")

    bundle = provenance_bundle.build_bundle(
        manifest,
        repo_root=repo,
        evidence_root=ev,
        snapshot_dir=ev / "snaps",
        pipeline_config=pipeline_cfg,
    )
    assert bundle["count"] == 2
    assert bundle["verdict_counts"]["fail"] == 0
    paths = [f["path"] for f in bundle["files"]]
    assert "a.txt" in paths and "b.txt" in paths


def test_bundle_flags_missing_file_as_fail(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    ev = repo / "evidence"
    ev.mkdir()
    manifest = repo / "m.sha256"
    manifest.write_text("deadbeef" * 8 + "  not-here.txt\n")
    pipeline_cfg = tmp_path / "pipeline.yaml"
    pipeline_cfg.write_text("rules: []\n")

    bundle = provenance_bundle.build_bundle(
        manifest,
        repo_root=repo,
        evidence_root=ev,
        snapshot_dir=ev / "snaps",
        pipeline_config=pipeline_cfg,
    )
    assert bundle["verdict_counts"]["fail"] == 1
    assert bundle["files"][0]["note"] == "missing-on-disk"


# -----------------------------------------------------------------------------
# Mustang end-to-end smoke
# -----------------------------------------------------------------------------


def test_mustang_emails_eml_via_cli(capsys) -> None:
    """End-to-end: `provenance` against a real Mustang email file.

    All six sections render; pipeline dispatcher routes to
    email-three-layer; verdict line includes the git-trail status."""
    repo = Path(__file__).resolve().parent.parent
    eml = (
        repo
        / "examples"
        / "maryland-mustang"
        / "evidence"
        / "emails"
        / "raw"
        / "020_2025-08-15_midlife-crisis-opinion-letter.eml"
    )
    if not eml.exists():
        pytest.skip("Mustang fixture not present")
    ev_root = repo / "examples" / "maryland-mustang" / "evidence"
    hash_mf = repo / "examples" / "maryland-mustang" / ".evidence-manifest.sha256"
    snap_dir = repo / "examples" / "maryland-mustang" / "provenance" / "snapshots"

    rc = provenance.main(
        [
            str(eml),
            "--evidence-root", str(ev_root),
            "--hash-manifest", str(hash_mf),
            "--snapshot-dir", str(snap_dir),
            "--repo-root", str(repo),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    for section_header in (
        "## Identity",
        "## Git trail",
        "## Hash manifest",
        "## Download provenance",
        "## Pipeline provenance",
    ):
        assert section_header in out
    assert "**Verdict:**" in out
    assert "email-three-layer" in out
