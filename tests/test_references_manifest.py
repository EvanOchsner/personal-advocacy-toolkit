"""Tests for scripts.references._manifest."""
from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from scripts.references import _manifest


def test_append_and_dedup(tmp_path: Path) -> None:
    m = tmp_path / ".references-manifest.yaml"
    _manifest.append_entry(m, {"source_id": "abc", "kind": "statute", "citation": "C1"})
    _manifest.append_entry(m, {"source_id": "def", "kind": "regulation", "citation": "C2"})
    entries = _manifest.list_entries(m)
    assert [e["source_id"] for e in entries] == ["abc", "def"]


def test_clobber_protection(tmp_path: Path) -> None:
    m = tmp_path / ".references-manifest.yaml"
    _manifest.append_entry(m, {"source_id": "abc", "kind": "statute"})
    with pytest.raises(FileExistsError):
        _manifest.append_entry(m, {"source_id": "abc", "kind": "statute"})


def test_force_overwrites(tmp_path: Path) -> None:
    m = tmp_path / ".references-manifest.yaml"
    _manifest.append_entry(m, {"source_id": "abc", "kind": "statute", "citation": "C1"})
    _manifest.append_entry(
        m, {"source_id": "abc", "kind": "statute", "citation": "C1-updated"}, force=True
    )
    entries = _manifest.list_entries(m)
    assert len(entries) == 1
    assert entries[0]["citation"] == "C1-updated"


def test_missing_source_id_raises(tmp_path: Path) -> None:
    m = tmp_path / ".references-manifest.yaml"
    with pytest.raises(ValueError):
        _manifest.append_entry(m, {"kind": "statute"})


def test_refresh_sha256_manifest(tmp_path: Path) -> None:
    refs = tmp_path / "references"
    (refs / "raw").mkdir(parents=True)
    (refs / "readable").mkdir(parents=True)
    (refs / "raw" / "doc.html").write_bytes(b"<p>hello</p>")
    (refs / "readable" / "doc.txt").write_text("hello")
    # Drop a manifest file in place so we can confirm it's skipped.
    (refs / ".references-manifest.yaml").write_text("entries: []\n")

    sha_manifest = tmp_path / ".references-manifest.sha256"
    count = _manifest.refresh_sha256_manifest(refs, sha_manifest)
    assert count == 2

    rows = sha_manifest.read_text(encoding="utf-8").strip().splitlines()
    paths = [r.split("  ", 1)[1] for r in rows]
    assert "raw/doc.html" in paths
    assert "readable/doc.txt" in paths
    # The manifest file itself is not included.
    assert all(".references-manifest" not in p for p in paths)
