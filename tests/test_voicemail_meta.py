"""Tests for scripts.ingest.voicemail_meta."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ingest import voicemail_meta


FIXTURE = Path(__file__).parent / "fixtures" / "call_log_sample.csv"


def test_parse_csv_basic() -> None:
    records = voicemail_meta.parse_csv(FIXTURE.read_bytes())
    assert len(records) == 4
    r0 = records[0]
    assert r0["caller_number"] == "+15551234567"
    assert r0["direction"] == "incoming"
    assert r0["duration_seconds"] == 120
    assert r0["timestamp_iso"].startswith("2024-03-15T14:05:00")

    # Millisecond-epoch timestamp in row 1
    r1 = records[1]
    assert r1["direction"] == "voicemail"
    assert r1["transcript"] and "Bob from the shop" in r1["transcript"]
    assert r1["timestamp_iso"].startswith("2024-03-16T")


def test_write_three_layers(tmp_path: Path) -> None:
    raw = FIXTURE.read_bytes()
    records = voicemail_meta.parse_csv(raw)
    summary = voicemail_meta.write_three_layers(raw, records, FIXTURE, tmp_path)
    assert summary["record_count"] == 4
    assert Path(summary["raw_path"]).exists()
    struct = Path(summary["structured_dir"])
    jsons = sorted(struct.glob("*.json"))
    assert len(jsons) == 4
    rec = json.loads(jsons[1].read_text())
    assert rec["index"] == 1
    assert rec["direction"] == "voicemail"


def test_cli_and_manifest(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    out_dir = tmp_path / "vm"
    manifest = tmp_path / "manifest.yaml"
    rc = voicemail_meta.main(
        [str(FIXTURE), "--out-dir", str(out_dir), "--manifest", str(manifest)]
    )
    assert rc == 0
    import yaml

    data = yaml.safe_load(manifest.read_text())
    e = data["entries"][0]
    assert e["kind"] == "voicemail_meta"
    assert e["record_count"] == 4


def test_clobber_protection(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    out_dir = tmp_path / "vm"
    manifest = tmp_path / "manifest.yaml"
    args = [str(FIXTURE), "--out-dir", str(out_dir), "--manifest", str(manifest)]
    assert voicemail_meta.main(args) == 0
    assert voicemail_meta.main(args) == 3
    assert voicemail_meta.main(args + ["--force"]) == 0


def test_unknown_direction_tagged() -> None:
    raw = b"number,name,direction,timestamp,duration_seconds,transcript\n" \
          b"+15550000000,,weird,2024-01-01T00:00:00Z,10,\n"
    records = voicemail_meta.parse_csv(raw)
    assert records[0]["direction"].startswith("unknown:")
