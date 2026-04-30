"""Tests for scripts.references.extract."""
from __future__ import annotations

from pathlib import Path

from scripts.references import extract


def test_extract_html_returns_plaintext() -> None:
    raw = b"<html><head><title>The Title</title></head><body><p>Hello, <b>world</b>.</p></body></html>"
    result = extract.extract(raw, "text/html")
    assert "Hello, world." in result.text
    assert result.method == "html-to-text"
    assert result.title == "The Title"


def test_extract_text_plain_identity() -> None:
    raw = "section 27-303\n  unfair claims practices\n".encode("utf-8")
    result = extract.extract(raw, "text/plain")
    assert "section 27-303" in result.text
    assert result.method == "identity"


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
