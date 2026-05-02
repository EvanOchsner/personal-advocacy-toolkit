"""Tier-0 extractors — direct unit tests against synthesized inputs.

Tier 0 is the fast path. We pin its behavior directly (rather than
only via the cascade) so a regression here surfaces without
needing to interpret merge / fall-through logic.
"""
from __future__ import annotations


import pytest

from scripts.extraction.extractors import (
    email_stdlib,
    html_tier0_stdlib,
    pdf_tier0_pypdf,
)
from scripts.extraction.result import ExtractionResult


# ---- HTML --------------------------------------------------------------

def test_html_tier0_extracts_visible_text_and_title() -> None:
    raw = (
        b"<html><head><title>Claim Update</title></head>"
        b"<body><p>Status:</p><ul><li>received</li><li>under review</li></ul>"
        b'<p>See <a href="https://example.com">portal</a>.</p>'
        b"</body></html>"
    )
    r = html_tier0_stdlib.extract(raw)
    assert isinstance(r, ExtractionResult)
    assert r.tier == 0
    assert r.method == "html.parser"
    assert r.title == "Claim Update"
    assert "Status:" in r.text
    assert "- received" in r.text
    assert "- under review" in r.text
    # Links rendered as "text (url)" so URLs stay grep-able.
    assert "portal (https://example.com)" in r.text


def test_html_tier0_drops_script_and_style() -> None:
    raw = (
        b"<html><body>"
        b"<script>alert('x')</script>"
        b"<style>body{color:red}</style>"
        b"<p>Visible</p>"
        b"</body></html>"
    )
    r = html_tier0_stdlib.extract(raw)
    assert "alert" not in r.text
    assert "color:red" not in r.text
    assert "Visible" in r.text


def test_html_tier0_charset_detected_from_meta() -> None:
    raw = (
        b'<html><head><meta charset="iso-8859-1">'
        b"<title>x</title></head><body><p>hi</p></body></html>"
    )
    r = html_tier0_stdlib.extract(raw)
    assert r.charset == "iso-8859-1"


def test_html_tier0_handles_charset_garbage_gracefully() -> None:
    raw = (
        b'<html><head><meta charset="bogus-charset"></head>'
        b"<body><p>fine</p></body></html>"
    )
    r = html_tier0_stdlib.extract(raw)
    # Unknown charset: parser falls back to UTF-8 decoding and reports it.
    assert r.charset == "utf-8"
    assert "fine" in r.text


# ---- Email -------------------------------------------------------------

def test_email_tier0_parses_canonical_record(make_eml) -> None:
    eml = make_eml(subject="Hi", body="Body text here.")
    record = email_stdlib.parse_eml(eml)
    assert record["subject"] == "Hi"
    assert record["from"][0]["email"] == "sally@example.com"
    assert record["to"][0]["email"] == "adjuster@cim.example"
    assert record["body_text"].strip() == "Body text here."
    assert record["date_iso"].startswith("2025-")
    assert record["source_sha256"]
    assert len(record["source_sha256"]) == 64


def test_email_tier0_render_text_includes_headers_and_body(make_eml) -> None:
    eml = make_eml(subject="Important Update", body="Multi\nline\nbody.")
    result = email_stdlib.extract(eml)
    assert isinstance(result, ExtractionResult)
    assert result.tier == 0
    assert result.method == "email.parser"
    assert "Subject: Important Update" in result.text
    assert "From:    Sally <sally@example.com>" in result.text
    assert "Multi\nline\nbody." in result.text
    assert result.title == "Important Update"


def test_email_tier0_settings_carry_canonical_record(make_eml) -> None:
    eml = make_eml()
    result = email_stdlib.extract(eml)
    record = result.settings["record"]
    assert "headers" in record
    assert record["body_text"]


# ---- PDF ---------------------------------------------------------------

def test_pdf_tier0_extracts_text_layer(make_simple_pdf) -> None:
    pdf = make_simple_pdf(pages=["The agreed-value endorsement was acknowledged."])
    pytest.importorskip("pypdf")
    r = pdf_tier0_pypdf.extract(pdf)
    assert isinstance(r, ExtractionResult)
    assert r.tier == 0
    assert r.method == "pypdf"
    assert "agreed-value" in r.text
    assert r.page_results is not None
    assert len(r.page_results) == 1
    assert r.page_results[0].page_number == 1
    assert "agreed-value" in r.page_results[0].text


def test_pdf_tier0_per_page_split(make_simple_pdf) -> None:
    pdf = make_simple_pdf(pages=["Page one body.", "Page two body.", "Page three body."])
    pytest.importorskip("pypdf")
    r = pdf_tier0_pypdf.extract(pdf)
    assert r.page_results is not None
    assert [p.page_number for p in r.page_results] == [1, 2, 3]
    assert "one" in r.page_results[0].text
    assert "two" in r.page_results[1].text
    assert "three" in r.page_results[2].text


def test_pdf_tier0_settings_capture_page_count_and_ocr_flag(make_simple_pdf) -> None:
    pdf = make_simple_pdf(pages=["body"])
    r = pdf_tier0_pypdf.extract(pdf)
    assert r.settings["page_count"] == 1
    assert r.settings["ocr_applied"] is False
    # ocr_engine is None when no OCR ran.
    assert r.settings["ocr_engine"] is None


def test_pdf_has_text_layer_helper(make_simple_pdf) -> None:
    pytest.importorskip("pypdf")
    pdf = make_simple_pdf(pages=["text layer"])
    assert pdf_tier0_pypdf.pdf_has_text_layer(pdf)


def test_extract_text_helper_returns_concatenated_pages(make_simple_pdf) -> None:
    pytest.importorskip("pypdf")
    pdf = make_simple_pdf(pages=["alpha words here", "beta words here"])
    text = pdf_tier0_pypdf.extract_text(pdf)
    assert "alpha" in text and "beta" in text
