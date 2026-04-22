"""Tests for scripts.ingest.sms_export (Phase 3 / track B).

Uses the synthetic Android SMS Backup & Restore XML fixture under
tests/fixtures/. No real case data.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ingest import sms_export


FIXTURE = Path(__file__).parent / "fixtures" / "sms_android_sample.xml"


def test_parse_android_xml_basic() -> None:
    records = sms_export.parse_android_sms_xml(FIXTURE.read_bytes())
    assert len(records) == 3
    r0 = records[0]
    assert r0["direction"] == "incoming"
    assert r0["address"] == "+15551234567"
    assert r0["body"].startswith("Hey, did you get")
    # date=1710500000000 ms -> 2024-03-15T10:53:20+00:00
    assert r0["date_iso"].startswith("2024-03-15T")
    assert r0["contact_name"] == "Alice Example"

    r1 = records[1]
    assert r1["direction"] == "outgoing"


def test_write_three_layers(tmp_path: Path) -> None:
    raw = FIXTURE.read_bytes()
    records = sms_export.parse_android_sms_xml(raw)
    summary = sms_export.write_three_layers(raw, records, FIXTURE, tmp_path)

    assert summary["message_count"] == 3
    assert len(summary["source_sha256"]) == 64
    assert Path(summary["raw_path"]).exists()

    struct = Path(summary["structured_dir"])
    human = Path(summary["human_dir"])
    jsons = sorted(struct.glob("*.json"))
    txts = sorted(human.glob("*.txt"))
    assert len(jsons) == 3
    assert len(txts) == 3

    rec = json.loads(jsons[0].read_text())
    assert rec["source_export_sha256"] == summary["source_sha256"]
    assert rec["message_index"] == 0
    assert rec["direction"] in ("incoming", "outgoing")


def test_cli_and_manifest(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    out_dir = tmp_path / "sms"
    manifest = tmp_path / "manifest.yaml"
    rc = sms_export.main(
        [
            str(FIXTURE),
            "--out-dir",
            str(out_dir),
            "--manifest",
            str(manifest),
        ]
    )
    assert rc == 0
    import yaml

    data = yaml.safe_load(manifest.read_text())
    assert data["entries"][0]["kind"] == "sms_export"
    assert data["entries"][0]["message_count"] == 3


def test_manifest_refuses_clobber_without_force(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    out_dir = tmp_path / "sms"
    manifest = tmp_path / "manifest.yaml"
    args = [str(FIXTURE), "--out-dir", str(out_dir), "--manifest", str(manifest)]
    assert sms_export.main(args) == 0
    # Second run with the same source -> clash on source_id, should fail.
    assert sms_export.main(args) == 3
    # With --force, succeeds.
    assert sms_export.main(args + ["--force"]) == 0


def test_unknown_format_errors(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.xyz"
    bogus.write_bytes(b"not an sms export")
    rc = sms_export.main([str(bogus), "--out-dir", str(tmp_path / "out")])
    assert rc == 2
