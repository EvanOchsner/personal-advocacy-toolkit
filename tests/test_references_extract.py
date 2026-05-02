"""Tests for scripts.references.extract.

After the migration to ``scripts.extraction``, this module is a thin
dispatcher that delegates HTML/PDF to the cascade's tier-0 extractors
and keeps an in-module path for plain text + .docx. These tests pin
that dispatcher's contract — what method label it returns, how it
warns on unsupported types, how content-type normalization works.
"""
from __future__ import annotations

from pathlib import Path

from scripts.references import extract


def test_extract_html_returns_plaintext() -> None:
    raw = b"<html><head><title>The Title</title></head><body><p>Hello, <b>world</b>.</p></body></html>"
    result = extract.extract(raw, "text/html")
    assert "Hello, world." in result.text
    # Method label reflects the actual extractor used (stdlib parser).
    assert result.method == "html.parser"
    assert result.title == "The Title"


def test_extract_text_plain_identity() -> None:
    raw = "section 27-303\n  unfair claims practices\n".encode("utf-8")
    result = extract.extract(raw, "text/plain")
    assert "section 27-303" in result.text
    assert result.method == "identity"


def test_extract_pdf_method_label_is_pypdf(tmp_path: Path) -> None:
    """Smoke test for the PDF dispatch path — exact tier-0 behavior is
    covered by the cascade tests. This pins the method label so a
    reviewer reading a references manifest can tell what produced it.
    """
    pytest = __import__("pytest")
    pytest.importorskip("pypdf")
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    pdf = tmp_path / "x.pdf"
    c = canvas.Canvas(str(pdf), pagesize=letter)
    c.drawString(72, 720, "section 27-303")
    c.showPage()
    c.save()

    result = extract.extract(pdf.read_bytes(), "application/pdf")
    assert result.method == "pypdf"
    assert "27-303" in result.text


def test_extract_unknown_type_warns() -> None:
    result = extract.extract(b"\x00\x01\x02", "application/x-fancy-binary")
    assert result.text == ""
    assert result.method == "no-extractor"
    assert any("no plaintext extractor" in w for w in result.warnings)


def test_extract_legacy_doc_warns() -> None:
    result = extract.extract(b"\x00", "application/msword")
    assert result.method == "no-extractor"
    assert any("legacy .doc" in w for w in result.warnings)


def test_normalize_content_type_uses_declared_when_known() -> None:
    assert extract.normalize_content_type("text/html; charset=utf-8", Path("a.bin")) == "text/html"
    assert (
        extract.normalize_content_type("application/octet-stream", Path("a.html")) == "text/html"
    )


def test_normalize_content_type_falls_back_to_suffix() -> None:
    assert extract.normalize_content_type(None, Path("policy.pdf")) == "application/pdf"
    assert extract.normalize_content_type(None, Path("doc.md")) == "text/markdown"
    assert extract.normalize_content_type(None, Path("unknown.xyz")) == "application/octet-stream"


def test_extract_re_exports_cascade() -> None:
    """References module surfaces the cascade for callers that want full access."""
    assert hasattr(extract, "cascade")
    assert hasattr(extract.cascade, "extract")
