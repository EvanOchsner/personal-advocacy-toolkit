"""Tests for scripts.publish.pdf_redact.

Primary test target: POST-CHECK. A redaction that only draws a black box on
top of existing text leaves the text layer intact — any PDF reader can still
extract the "redacted" string. The post-check must catch this.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pypdf = pytest.importorskip("pypdf")
reportlab = pytest.importorskip("reportlab")

from scripts.publish.pdf_redact import (  # noqa: E402
    Redaction,
    RedactionPostCheckError,
    redact_pdf,
)


def _make_pdf(path: Path, lines: list[tuple[float, float, str]]) -> None:
    """Produce a 1-page PDF with each (x, y, text) drawn at that position."""
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path), pagesize=(612, 792))
    c.setFont("Helvetica", 12)
    for x, y, text in lines:
        c.drawString(x, y, text)
    c.showPage()
    c.save()


def test_redaction_removes_text_under_bbox(tmp_path: Path) -> None:
    src = tmp_path / "src.pdf"
    dst = tmp_path / "dst.pdf"
    _make_pdf(
        src,
        [
            (72, 720, "Dear John Doe,"),
            (72, 600, "Please call our office."),
        ],
    )
    # Redact the line at y=720.
    redactions = [Redaction(page=0, bbox=(50, 710, 560, 735), replacement_text="[REDACTED]")]
    redact_pdf(src, dst, redactions=redactions, banned_terms=["John Doe"])
    # Output exists and post-check already ran (no exception).
    assert dst.exists()
    reader = pypdf.PdfReader(str(dst))
    text = (reader.pages[0].extract_text() or "")
    assert "John Doe" not in text
    # Unredacted line survives.
    assert "office" in text


def test_post_check_catches_leak(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Core defense: if the text-stripping step silently no-ops, the
    post-check must still delete the output and raise."""
    src = tmp_path / "src.pdf"
    dst = tmp_path / "dst.pdf"
    _make_pdf(src, [(72, 720, "Contact John Doe at jdoe@example.com")])

    # Force the text-stripper to do nothing — simulates the
    # "black box drawn over the text but text layer intact" failure mode.
    from scripts.publish import pdf_redact
    monkeypatch.setattr(pdf_redact, "_strip_text_in_bboxes", lambda page, bboxes: None)

    redactions = [Redaction(page=0, bbox=(50, 710, 560, 735), replacement_text="X")]
    with pytest.raises(RedactionPostCheckError, match="John Doe"):
        redact_pdf(src, dst, redactions=redactions, banned_terms=["John Doe"])
    # Output must have been deleted.
    assert not dst.exists()


def test_metadata_is_stripped(tmp_path: Path) -> None:
    from reportlab.pdfgen import canvas
    src = tmp_path / "src.pdf"
    c = canvas.Canvas(str(src), pagesize=(612, 792))
    c.setAuthor("John Doe")
    c.setTitle("Secret Policy Number CIM-VEH-2023")
    c.setCreator("TestCreator")
    c.drawString(72, 720, "Body text only.")
    c.showPage()
    c.save()

    dst = tmp_path / "dst.pdf"
    redact_pdf(
        src, dst,
        redactions=[],
        banned_terms=["John Doe", "CIM-VEH-2023"],
    )
    assert dst.exists()
    reader = pypdf.PdfReader(str(dst))
    meta = reader.metadata or {}
    blob = " ".join(str(v) for v in meta.values())
    assert "John Doe" not in blob
    assert "CIM-VEH-2023" not in blob


def test_empty_redactions_still_post_checks(tmp_path: Path) -> None:
    src = tmp_path / "src.pdf"
    dst = tmp_path / "dst.pdf"
    _make_pdf(src, [(72, 720, "Clean content only.")])
    # No banned terms, no redactions — should pass.
    redact_pdf(src, dst, redactions=[], banned_terms=[])
    assert dst.exists()
