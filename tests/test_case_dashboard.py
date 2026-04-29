"""Tests for scripts/status/case_dashboard.py.

Renders against a Maryland-Mustang synthetic intake + evidence
manifest fixture and asserts on structure: all expected sections
present, deadline lines carry the verify tag, disclaimer appears at
top.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")

import yaml  # noqa: E402

from scripts.status import case_dashboard as cd  # noqa: E402


MUSTANG_INTAKE = {
    "schema_version": "0.1",
    "synthetic": True,
    "case_name": "The Maryland Mustang",
    "situation_type": "insurance_dispute",
    "claimant": {"name": "Sally Ridesdale"},
    "jurisdiction": {"state": "MD"},
    "loss": {"date": "2025-03-15"},
}

MANIFEST = {
    "entries": [
        {"source_id": "a" * 64, "kind": "email"},
        {"source_id": "b" * 64, "kind": "email"},
        {"source_id": "c" * 64, "kind": "sms_export"},
        {"source_id": "d" * 64, "kind": "screenshot_capture"},
        {"source_id": "e" * 64, "kind": "medical_eob"},
    ],
}


@pytest.fixture
def intake_path(tmp_path: Path) -> Path:
    p = tmp_path / "case-intake.yaml"
    p.write_text(yaml.safe_dump(MUSTANG_INTAKE, sort_keys=False))
    return p


@pytest.fixture
def manifest_path(tmp_path: Path) -> Path:
    p = tmp_path / "manifest.yaml"
    p.write_text(yaml.safe_dump(MANIFEST, sort_keys=False))
    return p


def test_dashboard_sections_present(intake_path: Path, manifest_path: Path, capsys) -> None:
    rc = cd.main(["--intake", str(intake_path), "--manifest", str(manifest_path)])
    assert rc == 0
    out = capsys.readouterr().out
    # Expected section headers.
    for header in ("# Case dashboard", "## Header", "## Evidence", "## Deadlines", "## Packets", "## Pending / Done"):
        assert header in out, f"missing section: {header}"
    # Disclaimer at top.
    assert "not legal advice" in out.lower()
    # Header values.
    assert "The Maryland Mustang" in out
    assert "insurance_dispute" in out
    assert "MD" in out
    assert "2025-03-15" in out


def test_dashboard_evidence_counts(intake_path: Path, manifest_path: Path, tmp_path: Path) -> None:
    out_path = tmp_path / "dashboard.md"
    rc = cd.main(
        [
            "--intake", str(intake_path),
            "--manifest", str(manifest_path),
            "--out", str(out_path),
        ]
    )
    assert rc == 0
    body = out_path.read_text(encoding="utf-8")
    # Each kind with its count should appear in the evidence table.
    assert "| email | 2 |" in body
    assert "| sms_export | 1 |" in body
    assert "| screenshot_capture | 1 |" in body
    assert "| medical_eob | 1 |" in body
    assert "Total entries in manifest: **5**" in body


def test_dashboard_deadline_lines_have_verify_tag(
    intake_path: Path, manifest_path: Path, capsys
) -> None:
    rc = cd.main(["--intake", str(intake_path), "--manifest", str(manifest_path)])
    assert rc == 0
    out = capsys.readouterr().out
    # There should be at least one deadline bullet line, and every such
    # line should carry the VERIFY tag.
    deadline_lines = [
        ln for ln in out.splitlines()
        if ln.startswith("- **") and ("(sol)" in ln or "(notice)" in ln or "(admin_complaint)" in ln)
    ]
    assert deadline_lines, "expected at least one deadline bullet"
    for ln in deadline_lines:
        assert "VERIFY WITH COUNSEL" in ln, f"missing verify tag: {ln}"
    # The 3-year SOL from 2025-03-15 -> 2028-03-15 should appear.
    assert "2028-03-15" in out


def test_dashboard_pending_when_no_evidence(tmp_path: Path, intake_path: Path) -> None:
    empty_manifest = tmp_path / "empty.yaml"
    empty_manifest.write_text(yaml.safe_dump({"entries": []}))
    out_path = tmp_path / "dash.md"
    rc = cd.main(
        [
            "--intake", str(intake_path),
            "--manifest", str(empty_manifest),
            "--out", str(out_path),
        ]
    )
    assert rc == 0
    body = out_path.read_text(encoding="utf-8")
    assert "No evidence ingested yet." in body
    assert "No validated complaint packet yet." in body


def test_dashboard_packet_dir_validates(tmp_path: Path, intake_path: Path, manifest_path: Path) -> None:
    # Point packet-dir at the repo's test fixture packet manifest so we
    # exercise the packet-validation code path.
    fixtures = Path(__file__).parent / "fixtures" / "packet"
    if not (fixtures / "manifest.yaml").exists():
        pytest.skip("fixture packet manifest absent")
    out_path = tmp_path / "dash.md"
    rc = cd.main(
        [
            "--intake", str(intake_path),
            "--manifest", str(manifest_path),
            "--packet-dir", str(fixtures),
            "--out", str(out_path),
        ]
    )
    assert rc == 0
    body = out_path.read_text(encoding="utf-8")
    assert "## Packets" in body
