"""Tests for scripts.ingest.pdf_to_text and scripts.ingest._pdf.

The OCR-required branch is exercised only when `ocrmypdf` is on PATH;
otherwise it's covered by the "missing binary" fallback assertions
(image-only PDFs return empty text plus a warning note).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.ingest import _pdf, pdf_to_text


def _write_text_pdf(path: Path, lines: list[str]) -> None:
    """Generate a tiny PDF with a real text layer via reportlab."""
    reportlab = pytest.importorskip("reportlab")  # noqa: F841
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    y = 720
    for line in lines:
        c.drawString(72, y, line)
        y -= 18
    c.showPage()
    c.save()


@pytest.fixture
def text_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "sample.pdf"
    _write_text_pdf(p, ["Hello from a real PDF", "Line two for grep."])
    return p


def _write_image_only_pdf(path: Path) -> None:
    """Generate a single-page PDF whose only content is a filled rectangle.

    No text operators -> pypdf's extract_text() returns an empty string,
    so this exercises the "no text layer" branch.
    """
    reportlab = pytest.importorskip("reportlab")  # noqa: F841
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    c.setFillGray(0.5)
    c.rect(72, 600, 200, 100, fill=1, stroke=0)
    c.showPage()
    c.save()


def test_has_text_layer_true(text_pdf: Path) -> None:
    assert _pdf.pdf_has_text_layer(text_pdf) is True


def test_has_text_layer_false_for_image_only(tmp_path: Path) -> None:
    p = tmp_path / "image.pdf"
    _write_image_only_pdf(p)
    assert _pdf.pdf_has_text_layer(p) is False


def test_extract_text_on_text_pdf(text_pdf: Path) -> None:
    text = _pdf.extract_text(text_pdf)
    assert "Hello from a real PDF" in text
    assert "Line two for grep." in text


def test_extract_text_returns_empty_on_unreadable(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.pdf"
    bogus.write_bytes(b"not a pdf")
    assert _pdf.extract_text(bogus) == ""


def test_page_count(text_pdf: Path) -> None:
    assert _pdf.page_count(text_pdf) == 1


def test_ingest_pdf_text_layer_path(text_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    record = pdf_to_text.ingest_pdf(text_pdf, out)

    assert record["page_count"] == 1
    assert record["text_chars"] > 0
    assert record["ocr_applied"] is False
    assert record["ocr_engine"] is None
    assert record["notes"] == []

    plaintext = (out / "human" / f"{record['source_id']}.txt").read_text()
    assert "Hello from a real PDF" in plaintext

    raw_copy = out / "raw" / f"{record['source_id']}.pdf"
    assert raw_copy.read_bytes() == text_pdf.read_bytes()

    structured = json.loads(
        (out / "structured" / f"{record['source_id']}.json").read_text()
    )
    assert structured["source_sha256"] == record["source_sha256"]


def test_ingest_image_only_without_ocrmypdf(tmp_path: Path) -> None:
    """Image-only PDF should pass through with a warning note when ocrmypdf is absent."""
    if shutil.which("ocrmypdf"):
        pytest.skip("ocrmypdf available; this test covers the missing-binary fallback")
    p = tmp_path / "image.pdf"
    _write_image_only_pdf(p)
    out = tmp_path / "out"
    record = pdf_to_text.ingest_pdf(p, out)
    assert record["ocr_applied"] is False
    assert record["text_chars"] == 0
    assert record["notes"], "expected a warning note for missing ocrmypdf"


def test_cli_writes_manifest(text_pdf: Path, tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    import yaml

    manifest = tmp_path / "manifest.yaml"
    rc = pdf_to_text.main(
        [str(text_pdf), "--out-dir", str(tmp_path / "out"), "--manifest", str(manifest)]
    )
    assert rc == 0
    data = yaml.safe_load(manifest.read_text())
    e = data["entries"][0]
    assert e["kind"] == "pdf_to_text"
    assert e["page_count"] == 1
    assert e["source_id"]


def test_cli_clobber_protection(text_pdf: Path, tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    out = tmp_path / "out"
    manifest = tmp_path / "manifest.yaml"
    args = [str(text_pdf), "--out-dir", str(out), "--manifest", str(manifest)]
    assert pdf_to_text.main(args) == 0
    assert pdf_to_text.main(args) == 3
    assert pdf_to_text.main(args + ["--force"]) == 0


def test_cli_handles_directory_input(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    _write_text_pdf(src_dir / "a.pdf", ["alpha document"])
    _write_text_pdf(src_dir / "b.pdf", ["beta document"])
    (src_dir / "ignore.txt").write_text("not a pdf")

    out = tmp_path / "out"
    rc = pdf_to_text.main([str(src_dir), "--out-dir", str(out)])
    assert rc == 0
    plaintexts = list((out / "human").glob("*.txt"))
    assert len(plaintexts) == 2
