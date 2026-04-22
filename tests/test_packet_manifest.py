"""Smoke tests for the packet-manifest loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.packet._manifest import (
    ManifestError,
    _default_label,
    load_manifest,
)

FIXTURE = Path(__file__).parent / "fixtures" / "packet" / "manifest.yaml"


def test_loads_fixture_manifest():
    m = load_manifest(FIXTURE)
    assert m.name == "fixture-packet"
    assert m.authority.short_code == "FRB"
    assert m.complainant.name == "Test Complainant"
    assert m.respondent.name == "Fictional Respondent Co."
    assert len(m.exhibits) == 2
    assert m.exhibits[0].label == "A"
    assert m.exhibits[1].label == "B"
    assert len(m.reference_appendices) == 1


def test_default_label_sequence():
    labels = [_default_label(i) for i in range(28)]
    assert labels[:3] == ["A", "B", "C"]
    assert labels[25] == "Z"
    assert labels[26] == "AA"
    assert labels[27] == "AB"


def test_rejects_bad_name(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
schema_version: "1.0"
packet:
  name: "Bad Name With Spaces"
  authority: {name: a, short_code: a}
  complainant: {name: a}
  respondent: {name: a}
  complaint: {source: x.pdf}
  output_dir: out/
""",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError):
        load_manifest(bad)


def test_rejects_unsupported_schema(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
schema_version: "99.0"
packet:
  name: "ok"
  authority: {name: a, short_code: a}
  complainant: {name: a}
  respondent: {name: a}
  complaint: {source: x.pdf}
  output_dir: out/
""",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError):
        load_manifest(bad)


def test_rejects_exhibit_with_both_source_and_sources(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
schema_version: "1.0"
packet:
  name: "ok"
  authority: {name: a, short_code: a}
  complainant: {name: a}
  respondent: {name: a}
  complaint: {source: x.pdf}
  output_dir: out/
  exhibits:
    - title: bad
      description: bad
      source: a.pdf
      sources: [b.pdf]
""",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError):
        load_manifest(bad)
