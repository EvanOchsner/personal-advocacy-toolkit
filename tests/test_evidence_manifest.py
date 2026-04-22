"""Tests for scripts.manifest.evidence_manifest.

Key assertions:
  - scan_tree infers kinds from data/kind_inference.yaml.
  - --merge folds in a Phase 3B-shaped ingester manifest.
  - build → write → read round-trip is idempotent modulo generated_at.
  - the dashboard renders non-zero Evidence counts against the output.
"""
from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from scripts.manifest import evidence_manifest as em  # noqa: E402
from scripts.status import case_dashboard as cd  # noqa: E402


def _write(p: Path, body: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)


def test_kind_inference_known_patterns(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root / "emails/raw/001.eml", "From: a@b\n")
    _write(root / "emails/structured/001.json", "{}")
    _write(root / "photos/IMG_0001.jpg", "")
    _write(root / "valuation/report.md", "# v")
    _write(root / "policy/form.md", "# p")
    _write(root / "stray.xyz", "?")

    rules = em._load_rules()
    entries = em.scan_tree(root, rules, compute_hashes=False)
    kinds = {e["path"]: e["kind"] for e in entries}

    assert kinds["emails/raw/001.eml"] == "email_raw"
    assert kinds["emails/structured/001.json"] == "email_structured"
    assert kinds["photos/IMG_0001.jpg"] == "photo"
    assert kinds["valuation/report.md"] == "valuation"
    assert kinds["policy/form.md"] == "policy_document"
    assert kinds["stray.xyz"] == "unknown"


def test_build_and_write_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root / "emails/raw/001.eml", "a")
    _write(root / "photos/a.jpg", "b")
    out = tmp_path / "evidence-manifest.yaml"

    m = em.build_manifest(root)
    em.write_manifest(m, out)

    loaded = yaml.safe_load(out.read_text())
    assert loaded["schema"] == "evidence-manifest/1.0"
    assert len(loaded["entries"]) == 2
    for e in loaded["entries"]:
        assert len(e["sha256"]) == 64
        assert e["size"] >= 1


def test_merge_folds_external_manifest(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root / "emails/raw/001.eml", "a")

    ext = tmp_path / "sms-manifest.yaml"
    ext.write_text(
        yaml.safe_dump(
            {
                "entries": [
                    {
                        "source_id": "abcdef0123456789",
                        "kind": "sms",
                        "message_count": 42,
                    }
                ]
            }
        )
    )

    m = em.build_manifest(root, merge_paths=[ext])
    kinds = [e["kind"] for e in m["entries"]]
    assert "email_raw" in kinds
    assert "sms" in kinds
    sms = [e for e in m["entries"] if e["kind"] == "sms"][0]
    assert sms["source_manifest"].endswith("sms-manifest.yaml")


def test_dashboard_renders_nonzero_evidence_from_manifest(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root / "emails/raw/001.eml", "a")
    _write(root / "emails/raw/002.eml", "b")
    _write(root / "photos/c.jpg", "c")

    out = tmp_path / "evidence-manifest.yaml"
    em.write_manifest(em.build_manifest(root, compute_hashes=False), out)

    intake = {
        "case_name": "Test Case",
        "situation_type": "insurance_dispute",
        "jurisdiction": {"state": "MD"},
        "loss": {"date": "2025-03-15"},
        "synthetic": True,
    }
    manifest = cd._load_manifest(out)
    md = cd.render_dashboard(intake, manifest, None, [])
    assert "Total entries in manifest: **3**" in md
    assert "| email_raw | 2 |" in md
    assert "| photo | 1 |" in md


def test_idempotent_entries(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root / "a.eml", "x")
    _write(root / "b.jpg", "y")

    m1 = em.build_manifest(root)
    m2 = em.build_manifest(root)
    # Modulo generated_at, entries are identical and in the same order.
    assert m1["entries"] == m2["entries"]


def test_cli_smoke(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    _write(root / "emails/raw/001.eml", "a")
    out = tmp_path / "m.yaml"
    rc = em.main(["--root", str(root), "--out", str(out), "--no-hash"])
    assert rc == 0
    data = yaml.safe_load(out.read_text())
    assert len(data["entries"]) == 1
