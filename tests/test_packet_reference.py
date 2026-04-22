"""Smoke tests for the reference-compiler and appendix-cover tools."""

from __future__ import annotations

from pathlib import Path

import pytest

pypdf = pytest.importorskip("pypdf")
pytest.importorskip("reportlab")

from scripts.packet.appendix_cover import build_appendix_cover  # noqa: E402
from scripts.packet.compile_reference import (  # noqa: E402
    compile_reference,
    compile_reference_markdown,
)


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


def test_compile_reference_markdown_emits_banner_and_sources(tmp_path: Path):
    src1 = tmp_path / "policy-1.txt"
    src2 = tmp_path / "policy-2.md"
    src1.write_text("First fictional policy document.", encoding="utf-8")
    src2.write_text("# Second\n\nSecond fictional policy document.", encoding="utf-8")
    out = tmp_path / "reference.md"

    compile_reference_markdown(
        title="Fictional Counterparty Reference",
        counterparty="Fictional Co.",
        sources=[src1, src2],
        output=out,
        note="Test compile.",
    )

    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    # Top disclaimer + per-section callouts.
    assert text.count("COMPILED REFERENCE") >= 3  # top + callouts + bottom
    # Top and bottom disclaimers both present.
    assert text.startswith("# ⚠️ COMPILED REFERENCE")
    assert "## ⚠️ COMPILED REFERENCE — NOT AN ORIGINAL DOCUMENT ⚠️" in text
    assert "Fictional Counterparty Reference" in text
    assert "First fictional policy document." in text
    assert "Second fictional policy document." in text
    # Section headers for each source.
    assert "Source 1:" in text
    assert "Source 2:" in text
    # SHA-256 listing in the disclaimers.
    assert "SHA-256:" in text


def test_compile_reference_markdown_requires_sources(tmp_path: Path):
    with pytest.raises(ValueError):
        compile_reference_markdown(
            title="x",
            counterparty="y",
            sources=[],
            output=tmp_path / "x.md",
        )


def test_markdown_fidelity_report_flags_thin_sources(tmp_path: Path, capsys):
    """The fidelity report prints chars/page for each source and flags any
    below the floor (silent-extraction-failure guardrail)."""
    src = tmp_path / "tiny.md"
    src.write_text("x\n", encoding="utf-8")  # well under 200 chars/page
    out = tmp_path / "ref.md"

    compile_reference_markdown(
        title="Test",
        counterparty="Test Co.",
        sources=[src],
        output=out,
    )
    err = capsys.readouterr().err
    assert "chars/page" in err
    assert "WARN" in err
    assert "likely failed text extraction" in err


def test_compile_reference_pdf_is_byte_deterministic(tmp_path: Path):
    """Two runs of compile_reference (PDF) produce byte-identical output
    given identical inputs. Relies on pikepdf's deterministic /ID + pinned
    creationDate/modDate."""
    src = tmp_path / "policy.md"
    src.write_text("# Policy\n\nGoverning document text.\n", encoding="utf-8")

    out1 = tmp_path / "ref-1.pdf"
    out2 = tmp_path / "ref-2.pdf"
    compile_reference(
        title="Det-Test",
        counterparty="Test Co.",
        sources=[src],
        output=out1,
    )
    compile_reference(
        title="Det-Test",
        counterparty="Test Co.",
        sources=[src],
        output=out2,
    )
    assert out1.read_bytes() == out2.read_bytes(), (
        "compile_reference PDFs should be byte-identical across runs with "
        "identical inputs; pikepdf determinism is broken."
    )


def test_compile_reference_markdown_is_deterministic(tmp_path: Path):
    """Same deterministic guarantee for the markdown path."""
    src = tmp_path / "policy.md"
    src.write_text("content\n", encoding="utf-8")

    out1 = tmp_path / "ref-1.md"
    out2 = tmp_path / "ref-2.md"
    compile_reference_markdown(
        title="Det-Test",
        counterparty="Test Co.",
        sources=[src],
        output=out1,
    )
    compile_reference_markdown(
        title="Det-Test",
        counterparty="Test Co.",
        sources=[src],
        output=out2,
    )
    assert out1.read_bytes() == out2.read_bytes()
