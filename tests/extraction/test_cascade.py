"""Cascade orchestration — escalation, garble checks, per-page merge.

These tests use monkeypatched tier-1+ extractors to keep them fast
and dep-free. The monkeypatched extractors expose the right
interfaces so the cascade's escalation / merge logic gets exercised
end-to-end.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.extraction import cascade
from scripts.extraction.result import ExtractionResult, PageResult


# ---- PDF cascade -------------------------------------------------------

def _stub_tier1_extract(text: str = "", page_texts: list[str] | None = None):
    """Build a stub tier-1 docling extractor that returns the supplied texts."""

    def _extract(pdf, *, settings=None):
        if page_texts is None:
            return ExtractionResult(
                text=text, method="docling@stub", tier=1, settings={}
            )
        pages = [
            PageResult(page_number=i + 1, text=t, method="docling@stub", tier=1)
            for i, t in enumerate(page_texts)
        ]
        return ExtractionResult(
            text="\n\n".join(t.strip() for t in page_texts if t.strip()),
            method="docling@stub",
            tier=1,
            settings={},
            page_results=pages,
        )

    return _extract


def test_pdf_cascade_stops_at_tier_0_on_clean_input(
    make_simple_pdf, case_root, monkeypatch
) -> None:
    pytest.importorskip("pypdf")
    pdf = make_simple_pdf(
        pages=["The agreed-value endorsement was acknowledged at policy inception."]
    )

    # Tier 1 should not be touched — make it explode if reached.
    from scripts.extraction.extractors import pdf_tier1_docling

    def boom(*a, **k):
        raise AssertionError("tier 1 should not run on clean input")

    monkeypatch.setattr(pdf_tier1_docling, "extract", boom)

    result = cascade.extract(pdf, case_root=case_root)
    assert result.tier == 0
    assert result.method == "pypdf"
    assert "agreed-value" in result.text


def test_pdf_cascade_escalates_to_tier_1_when_tier_0_garbled(
    make_simple_pdf, case_root, monkeypatch
) -> None:
    pytest.importorskip("pypdf")
    # PDF with too-short text on each page → tier 0 will be flagged
    # as garbled by the chars/page floor.
    pdf = make_simple_pdf(pages=["x", "y"])

    from scripts.extraction.extractors import pdf_tier1_docling

    monkeypatch.setattr(
        pdf_tier1_docling,
        "extract",
        _stub_tier1_extract(
            page_texts=[
                "Tier 1 produced a clean readable paragraph for page one with "
                "many real words.",
                "Tier 1 produced a clean readable paragraph for page two with "
                "many real words.",
            ]
        ),
    )

    result = cascade.extract(pdf, case_root=case_root)
    # Tier 1 stitched in; method label reflects merge.
    assert "docling@stub" in result.method
    assert result.page_results is not None
    # Both pages came from the docling stub.
    assert all("Tier 1" in p.text for p in result.page_results)


def test_pdf_cascade_merges_per_page_keeping_clean_tier0_pages(
    make_simple_pdf, case_root, monkeypatch
) -> None:
    """If page 1 is fine at tier 0 but page 2 is garbled, only page 2 is replaced."""
    pytest.importorskip("pypdf")
    pdf = make_simple_pdf(
        pages=[
            "Page one has real readable words about insurance policy terms and "
            "claims handling and adjusters and so on.",
            "x",  # garbled — tier 1 should replace this one
        ]
    )

    from scripts.extraction.extractors import pdf_tier1_docling

    monkeypatch.setattr(
        pdf_tier1_docling,
        "extract",
        _stub_tier1_extract(
            page_texts=[
                # Tier 1's view of page 1 is *also* fine, but we still
                # want to keep tier 0's version (the cascade should
                # only replace garbled pages, not all of them).
                "Tier 1's page 1 transcription. (different from tier 0)",
                "Tier 1's clean transcription of page two with enough words to "
                "pass the chars/page floor without question.",
            ]
        ),
    )

    result = cascade.extract(pdf, case_root=case_root)
    assert result.page_results is not None
    page1, page2 = result.page_results[0], result.page_results[1]
    assert "Page one has real readable words" in page1.text
    assert page1.tier == 0
    assert "Tier 1's clean transcription of page two" in page2.text
    assert page2.tier == 1


def test_pdf_cascade_force_tier_skips_lower_tiers(
    make_simple_pdf, case_root, monkeypatch
) -> None:
    pytest.importorskip("pypdf")
    pdf = make_simple_pdf(pages=["Clean readable text that would pass tier 0 easily."])

    from scripts.extraction.extractors import pdf_tier1_docling

    called = {"tier1": 0}

    def stub(pdf_, *, settings=None):
        called["tier1"] += 1
        return _stub_tier1_extract(text="forced tier 1 result")(pdf_, settings=settings)

    monkeypatch.setattr(pdf_tier1_docling, "extract", stub)

    # Write an override forcing tier 1.
    src_id = cascade._source_id(pdf)
    ovr_path = case_root / "extraction" / "overrides" / f"{src_id}.yaml"
    ovr_path.parent.mkdir(parents=True, exist_ok=True)
    ovr_path.write_text(
        f"source_id: {src_id}\noverrides:\n  force_tier: 1\n", encoding="utf-8"
    )

    result = cascade.extract(pdf, case_root=case_root)
    assert called["tier1"] == 1
    assert result.tier == 1


def test_pdf_cascade_records_warning_when_tier1_unavailable(
    make_simple_pdf, case_root, monkeypatch
) -> None:
    pytest.importorskip("pypdf")
    # Garbled tier 0 will trigger tier 1 attempt; make tier 1 fail.
    pdf = make_simple_pdf(pages=["x"])

    from scripts.extraction.extractors import pdf_tier1_docling

    def fail(*a, **k):
        raise pdf_tier1_docling.DoclingUnavailable("not installed")

    monkeypatch.setattr(pdf_tier1_docling, "extract", fail)

    # Tier 2 + 3 also unavailable in test env — they'll add warnings.
    result = cascade.extract(pdf, case_root=case_root)
    assert any("tier 1" in w.lower() for w in result.warnings)


# ---- HTML cascade ------------------------------------------------------

def test_html_cascade_stops_at_tier_0_for_clean_html(make_html, case_root) -> None:
    p = make_html(
        body="<p>Substantive HTML content that has more than two hundred characters of real readable text "
        "across multiple paragraphs, so the document-level garble check accepts it without escalation, "
        "and the cascade stays on tier 0 cleanly.</p>"
    )
    result = cascade.extract(p, case_root=case_root)
    assert result.tier == 0
    assert result.method == "html.parser"
    assert "Substantive HTML content" in result.text


def test_html_cascade_escalates_when_tier0_too_short(
    make_html, case_root, monkeypatch
) -> None:
    p = make_html(body="<p>too short</p>")  # tier 0 doc length below floor

    from scripts.extraction.extractors import html_tier1_trafilatura

    def stub(raw, *, settings=None):
        return ExtractionResult(
            text=(
                "Tier 1 main-content extraction produced a substantial body "
                "of readable text past the document-length floor with plenty "
                "of common English words about insurance and claims and so on."
            ),
            method="trafilatura@stub",
            tier=1,
            title="Stub Title",
        )

    monkeypatch.setattr(html_tier1_trafilatura, "extract", stub)

    result = cascade.extract(p, case_root=case_root)
    assert "Tier 1 main-content" in result.text
    assert result.tier >= 1


# ---- Email cascade -----------------------------------------------------

def test_email_cascade_is_single_tier(make_eml, case_root) -> None:
    p = make_eml(subject="Hello", body="A short email body works fine.")
    result = cascade.extract(p, case_root=case_root)
    assert result.tier == 0
    assert result.method == "email.parser"
    assert "Hello" in result.text


# ---- Unknown type ------------------------------------------------------

def test_cascade_rejects_unknown_extension(tmp_path: Path, case_root) -> None:
    p = tmp_path / "thing.xyz"
    p.write_bytes(b"\x00\x01\x02")
    with pytest.raises(ValueError, match="unknown document type"):
        cascade.extract(p, case_root=case_root)


# ---- Override application is preserved ---------------------------------

def test_strip_text_pattern_override_is_applied_to_final_text(
    make_simple_pdf, case_root
) -> None:
    pytest.importorskip("pypdf")
    pdf = make_simple_pdf(
        pages=["CONFIDENTIAL — DO NOT DISTRIBUTE\nReal body content here."]
    )
    src_id = cascade._source_id(pdf)
    ovr_path = case_root / "extraction" / "overrides" / f"{src_id}.yaml"
    ovr_path.parent.mkdir(parents=True, exist_ok=True)
    ovr_path.write_text(
        f"source_id: {src_id}\n"
        "overrides:\n"
        '  strip_text_patterns: ["CONFIDENTIAL — DO NOT DISTRIBUTE"]\n',
        encoding="utf-8",
    )
    result = cascade.extract(pdf, case_root=case_root)
    assert "CONFIDENTIAL" not in result.text
    assert "Real body content here" in result.text
    assert "strip_text_patterns" in result.overrides_applied


def test_skip_pages_override_drops_those_pages(
    make_simple_pdf, case_root
) -> None:
    pytest.importorskip("pypdf")
    pdf = make_simple_pdf(
        pages=[
            "First page real content with many readable words about claims.",
            "Second page real content with many readable words about claims.",
            "Third page real content with many readable words about claims.",
        ]
    )
    src_id = cascade._source_id(pdf)
    ovr_path = case_root / "extraction" / "overrides" / f"{src_id}.yaml"
    ovr_path.parent.mkdir(parents=True, exist_ok=True)
    ovr_path.write_text(
        f"source_id: {src_id}\noverrides:\n  skip_pages: [2]\n",
        encoding="utf-8",
    )
    result = cascade.extract(pdf, case_root=case_root)
    assert result.page_results is not None
    assert [p.page_number for p in result.page_results] == [1, 3]
    assert "Second page" not in result.text
