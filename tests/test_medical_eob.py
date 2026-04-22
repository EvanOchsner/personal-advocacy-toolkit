"""Tests for scripts.ingest.medical_eob."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ingest import medical_eob


FIXTURE = Path(__file__).parent / "fixtures" / "eob_sample.csv"


def test_parse_csv_basic() -> None:
    records = medical_eob.parse_csv(FIXTURE.read_bytes())
    assert len(records) == 3
    r0 = records[0]
    assert r0["cpt_code"] == "99213"
    assert r0["billed"] == 250.0
    assert r0["patient_responsibility"] == 30.0
    assert r0["date_of_service"] == "2024-02-15"
    # extra column preserved
    assert r0["extra"].get("claim_id") == "SYN-001"

    # US-style date is normalized.
    r2 = records[2]
    assert r2["date_of_service"] == "2024-03-01"
    assert r2["billed"] == 2100.0


def test_write_three_layers_and_totals(tmp_path: Path) -> None:
    raw = FIXTURE.read_bytes()
    records = medical_eob.parse_csv(raw)
    summary = medical_eob.write_three_layers(
        raw, records, FIXTURE, tmp_path, "generic-eob-csv"
    )
    assert summary["line_item_count"] == 3
    assert summary["totals"]["billed"] == 2435.0
    assert summary["totals"]["allowed"] == 1242.5
    assert summary["totals"]["patient_responsibility"] == 288.5

    struct = Path(summary["structured_dir"])
    jsons = sorted(struct.glob("*.json"))
    assert len(jsons) == 3
    rec = json.loads(jsons[0].read_text())
    assert rec["provider"].startswith("Dr. Synthetic")


def test_cli_and_manifest(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    out_dir = tmp_path / "eob"
    manifest = tmp_path / "manifest.yaml"
    rc = medical_eob.main(
        [str(FIXTURE), "--out-dir", str(out_dir), "--manifest", str(manifest)]
    )
    assert rc == 0
    import yaml

    data = yaml.safe_load(manifest.read_text())
    e = data["entries"][0]
    assert e["kind"] == "medical_eob"
    assert e["line_item_count"] == 3
    assert e["format"] == "generic-eob-csv"


def test_pdf_format_is_stub(tmp_path: Path) -> None:
    """PDF format selection raises NotImplementedError (documented stub)."""
    bogus = tmp_path / "eob.pdf"
    bogus.write_bytes(b"%PDF-1.4\nnot a real eob")
    with pytest.raises(NotImplementedError):
        medical_eob.parse_anthem_pdf(bogus)


def test_clobber_protection(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    out_dir = tmp_path / "eob"
    manifest = tmp_path / "manifest.yaml"
    args = [str(FIXTURE), "--out-dir", str(out_dir), "--manifest", str(manifest)]
    assert medical_eob.main(args) == 0
    assert medical_eob.main(args) == 3
    assert medical_eob.main(args + ["--force"]) == 0
