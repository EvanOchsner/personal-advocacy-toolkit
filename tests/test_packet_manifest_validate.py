"""Tests for scripts/packet/packet_manifest_validate.py."""

from __future__ import annotations

import hashlib
import textwrap
from pathlib import Path

import pytest

from scripts.packet.packet_manifest_validate import validate


REPO_ROOT = Path(__file__).resolve().parent.parent
MUSTANG_MANIFEST = (
    REPO_ROOT
    / "examples"
    / "mustang-in-maryland"
    / "complaint_packet"
    / "packet-manifest.yaml"
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


_HEADER = """schema_version: "1.0"
packet:
  name: "synthetic-test-packet"
  authority:
    name: "Synthetic Authority"
    short_code: "SYN"
  complainant:
    name: "Test Person"
  respondent:
    name: "Fictional Co."
  complaint:
    source: "drafts/complaint.md"
    title: "Test Complaint"
  output_dir: "out/"
  exhibits:
"""


def _write_minimal_tree(tmp_path: Path, exhibits_yaml: str) -> Path:
    """Build a synthetic on-disk manifest tree. Returns manifest path."""
    (tmp_path / "evidence").mkdir()
    (tmp_path / "drafts").mkdir()
    (tmp_path / "drafts" / "complaint.md").write_text("# complaint\n")
    (tmp_path / "evidence" / "a.txt").write_text("alpha\n")
    (tmp_path / "evidence" / "b.txt").write_text("bravo\n")
    (tmp_path / "evidence" / "c.txt").write_text("charlie\n")

    manifest = tmp_path / "packet-manifest.yaml"
    manifest.write_text(_HEADER + exhibits_yaml)
    return manifest


_GOOD_EXHIBITS = """    - label: "A"
      title: "Exhibit A"
      description: "first"
      source: "evidence/a.txt"
    - label: "B"
      title: "Exhibit B"
      description: "second"
      source: "evidence/b.txt"
    - label: "C"
      title: "Exhibit C"
      description: "third"
      source: "evidence/c.txt"
"""


def test_happy_path_mustang_manifest():
    code, schema_errors, integrity_errors = validate(MUSTANG_MANIFEST)
    assert schema_errors == [], schema_errors
    assert integrity_errors == [], integrity_errors
    assert code == 0


def test_happy_path_synthetic(tmp_path: Path):
    m = _write_minimal_tree(tmp_path, _GOOD_EXHIBITS)
    code, schema_errors, integrity_errors = validate(m)
    assert schema_errors == []
    assert integrity_errors == []
    assert code == 0


def test_missing_required_key_is_schema_error(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        textwrap.dedent(
            """\
            schema_version: "1.0"
            packet:
              name: "no-authority"
              complainant: {name: a}
              respondent: {name: b}
              complaint: {source: "x.md"}
              output_dir: "out/"
              exhibits: []
            """
        )
    )
    code, schema_errors, integrity_errors = validate(bad)
    assert code == 1
    assert schema_errors
    assert any("authority" in e.lower() for e in schema_errors)


def test_exhibit_ordering_gap_is_integrity_error(tmp_path: Path):
    # A, C (skipping B)
    exhibits = """    - label: "A"
      title: "Exhibit A"
      description: "first"
      source: "evidence/a.txt"
    - label: "C"
      title: "Exhibit C"
      description: "third"
      source: "evidence/c.txt"
"""
    m = _write_minimal_tree(tmp_path, exhibits)
    code, schema_errors, integrity_errors = validate(m)
    assert code == 2
    assert any("out of sequence" in e for e in integrity_errors)


def test_missing_file_is_integrity_error(tmp_path: Path):
    exhibits = """    - label: "A"
      title: "Exhibit A"
      description: "first"
      source: "evidence/a.txt"
    - label: "B"
      title: "Exhibit B"
      description: "missing"
      source: "evidence/does-not-exist.txt"
"""
    m = _write_minimal_tree(tmp_path, exhibits)
    code, schema_errors, integrity_errors = validate(m)
    assert code == 2
    assert any("does-not-exist" in e for e in integrity_errors)


def test_hash_mismatch_is_integrity_error(tmp_path: Path):
    m = _write_minimal_tree(tmp_path, _GOOD_EXHIBITS)
    # Write a hash manifest with a deliberately wrong hash for b.txt
    real_a = _sha256(tmp_path / "evidence" / "a.txt")
    real_c = _sha256(tmp_path / "evidence" / "c.txt")
    wrong_b = "0" * 64
    hash_manifest = tmp_path / "evidence" / "manifest.sha256"
    hash_manifest.write_text(
        f"{real_a}  a.txt\n{wrong_b}  b.txt\n{real_c}  c.txt\n"
    )
    code, schema_errors, integrity_errors = validate(m, hash_manifest)
    assert code == 2
    assert any("hash mismatch" in e for e in integrity_errors)


def test_hash_match_clean(tmp_path: Path):
    m = _write_minimal_tree(tmp_path, _GOOD_EXHIBITS)
    ev = tmp_path / "evidence"
    lines = [f"{_sha256(ev / n)}  {n}" for n in ("a.txt", "b.txt", "c.txt")]
    hash_manifest = ev / "manifest.sha256"
    hash_manifest.write_text("\n".join(lines) + "\n")
    code, schema_errors, integrity_errors = validate(m, hash_manifest)
    assert schema_errors == []
    assert integrity_errors == [], integrity_errors
    assert code == 0
