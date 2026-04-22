"""End-to-end smoke test of the packet builder against fixture files."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pypdf = pytest.importorskip("pypdf")
pytest.importorskip("reportlab")

from scripts.packet._manifest import load_manifest  # noqa: E402
from scripts.packet.build import build_packet  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "packet"


def _stage_fixture(tmp_path: Path) -> Path:
    """Copy the fixture tree into `tmp_path` and return the manifest path.

    Copying keeps tests hermetic: the builder writes into `out/`, and
    using a fresh tmp_path per test guarantees no cross-test pollution.
    """
    dst = tmp_path / "packet"
    shutil.copytree(FIXTURES, dst)
    return dst / "manifest.yaml"


def test_build_produces_packet_and_exhibits(tmp_path: Path):
    manifest_path = _stage_fixture(tmp_path)
    manifest = load_manifest(manifest_path)
    result = build_packet(manifest)

    assert result["packet"].is_file()
    assert len(result["exhibits"]) == 2
    for p in result["exhibits"]:
        assert p.is_file()
        assert p.suffix == ".pdf"
    assert len(result["appendices"]) == 1
    assert result["appendices"][0].is_file()

    # The merged packet must have at least:
    # cover(1) + complaint(1) + per-exhibit(sep+body) + appendix pages.
    reader = pypdf.PdfReader(str(result["packet"]))
    assert len(reader.pages) >= 6


def test_exhibit_labels_default_alphabetical(tmp_path: Path):
    manifest_path = _stage_fixture(tmp_path)
    manifest = load_manifest(manifest_path)
    labels = [ex.label for ex in manifest.exhibits]
    assert labels == ["A", "B"]


def test_output_filenames_include_short_code(tmp_path: Path):
    manifest_path = _stage_fixture(tmp_path)
    manifest = load_manifest(manifest_path)
    result = build_packet(manifest)
    assert "frb" in result["packet"].name.lower()
    assert result["packet"].name.startswith("fixture-packet-")
