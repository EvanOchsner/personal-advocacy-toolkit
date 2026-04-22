"""Smoke tests for the reference-compiler and appendix-cover tools."""

from __future__ import annotations

from pathlib import Path

import pytest

pypdf = pytest.importorskip("pypdf")
pytest.importorskip("reportlab")

from scripts.packet.appendix_cover import build_appendix_cover  # noqa: E402
from scripts.packet.compile_reference import compile_reference  # noqa: E402


def test_appendix_cover_writes_pdf(tmp_path: Path):
    out = tmp_path / "cover.pdf"
    build_appendix_cover(
        output=out,
        title="Synthetic Counterparty Terms Reference",
        counterparty="Fictional Co.",
        note="Compiled from public website on 2026-01-05.",
    )
    assert out.is_file()
    reader = pypdf.PdfReader(str(out))
    assert len(reader.pages) == 1


def test_compile_reference_includes_cover_and_sources(tmp_path: Path):
    src1 = tmp_path / "policy-1.txt"
    src2 = tmp_path / "policy-2.txt"
    src1.write_text("First fictional policy document.", encoding="utf-8")
    src2.write_text("Second fictional policy document.", encoding="utf-8")
    out = tmp_path / "reference.pdf"

    compile_reference(
        title="Fictional Counterparty Reference",
        counterparty="Fictional Co.",
        sources=[src1, src2],
        output=out,
        note="Test compile.",
    )

    assert out.is_file()
    reader = pypdf.PdfReader(str(out))
    # cover + (section cover + body) * 2 sources = 5 pages minimum
    assert len(reader.pages) >= 5


def test_compile_reference_requires_sources(tmp_path: Path):
    with pytest.raises(ValueError):
        compile_reference(
            title="x",
            counterparty="y",
            sources=[],
            output=tmp_path / "x.pdf",
        )
