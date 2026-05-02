"""Garble detection — does each signal fire when it should and only then?

The cascade depends on these heuristics being trustworthy: a false
positive escalates to a heavy tier needlessly, a false negative ships
garbage as final output. We test each signal in isolation against
hand-crafted inputs.
"""
from __future__ import annotations

from scripts.extraction.garble import (
    DEFAULT_MAX_CID_RATIO,
    DEFAULT_MIN_CHARS_PER_PAGE,
    GarbleScore,
    html_extract_is_empty,
    score_text,
)


# ---- Clean text passes -------------------------------------------------

def test_clean_paragraph_is_not_garbled() -> None:
    text = (
        "The agreed-value endorsement on this policy was acknowledged at "
        "policy inception. The insurer's vendor's later valuation does not "
        "override the schedule of value absent fraud or material "
        "misrepresentation, neither of which is alleged here."
    )
    score = score_text(text, pages=1)
    assert not score.garbled, score.reasons


def test_long_clean_doc_passes_without_pages_floor() -> None:
    text = "Lorem ipsum dolor sit amet. " * 50
    score = score_text(text, pages=None)
    assert not score.garbled


# ---- Empty + short -----------------------------------------------------

def test_empty_text_is_garbled() -> None:
    score = score_text("", pages=1)
    assert score.garbled
    assert any("empty" in r for r in score.reasons)


def test_below_chars_per_page_floor_garbled() -> None:
    # Realistic-looking words but too few of them for a "page".
    text = "Cover page."
    score = score_text(text, pages=1, min_chars_per_page=DEFAULT_MIN_CHARS_PER_PAGE)
    assert score.garbled
    assert any("chars/page" in r for r in score.reasons)


def test_short_doc_without_pages_garbled() -> None:
    score = score_text("hi there", pages=None)
    assert score.garbled
    assert any("document length" in r for r in score.reasons)


# ---- CID-glyph density -------------------------------------------------

def test_cid_glyph_density_garbled() -> None:
    text = "Real word " + "(cid:123)" * 20 + " more text"
    score = score_text(text, pages=1, min_chars_per_page=1)
    assert score.garbled
    assert any("cid-glyph" in r for r in score.reasons)


def test_a_single_cid_glyph_does_not_trip_default_threshold() -> None:
    # Default ratio is 0.02; one (cid:0) in a long doc shouldn't fire.
    text = "Real text " * 50 + "(cid:0)"
    score = score_text(text, pages=1, max_cid_ratio=DEFAULT_MAX_CID_RATIO)
    assert not score.garbled, score.reasons


# ---- Replacement-char / non-printable ----------------------------------

def test_replacement_char_heavy_garbled() -> None:
    text = "abc " + "�" * 50 + " more text past the chars/page floor "
    score = score_text(text, pages=1, min_chars_per_page=1)
    assert score.garbled
    assert any("non-printable" in r for r in score.reasons)


# ---- Word-shape ratio --------------------------------------------------

def test_glyph_substitution_garbled_by_word_shape() -> None:
    # Random non-letter tokens — bezier-glyph substitution looks like
    # this when pypdf hands back garbage codepoints.
    text = " ".join("J6n4 mTpQ bFc 9H2 8E1 7D0 4r2 5v6 3l9 2k0".split() * 30)
    score = score_text(text, pages=1, min_chars_per_page=1)
    assert score.garbled
    assert any("word-shape" in r for r in score.reasons)


def test_mostly_real_words_passes_word_shape() -> None:
    text = "the quick brown fox jumps over the lazy dog. " * 20
    score = score_text(text, pages=1, min_chars_per_page=1)
    assert not score.garbled
    assert score.word_shape_ratio > 0.4


# ---- Threshold overrides flow through ---------------------------------

def test_threshold_overrides_can_relax_pass() -> None:
    # Default would fail (too few chars) — relax the floor.
    text = "tiny"
    relaxed = score_text(text, pages=1, min_chars_per_page=2)
    assert not relaxed.garbled


# ---- HTML emptiness heuristic -----------------------------------------

def test_html_extract_is_empty_when_extracted_short_and_raw_huge() -> None:
    # 100 chars of extracted text from 50 KB of raw HTML — likely SPA.
    assert html_extract_is_empty(extracted_chars=100, raw_bytes_len=50_000)


def test_html_extract_is_not_empty_when_text_is_substantial() -> None:
    # Plenty of text — don't escalate even if raw is bigger.
    assert not html_extract_is_empty(extracted_chars=5_000, raw_bytes_len=50_000)


def test_html_extract_is_not_empty_when_raw_is_small() -> None:
    # Tiny page that legitimately has tiny text content.
    assert not html_extract_is_empty(extracted_chars=180, raw_bytes_len=200)


# ---- Diagnostic fields exposed for the recipe -------------------------

def test_garble_score_exposes_diagnostics() -> None:
    text = "the quick brown fox jumps over the lazy dog. " * 5
    score = score_text(text, pages=1, min_chars_per_page=1)
    assert isinstance(score, GarbleScore)
    assert score.chars > 0
    assert 0.0 <= score.cid_ratio <= 1.0
    assert 0.0 <= score.nonprintable_ratio <= 1.0
    assert 0.0 <= score.word_shape_ratio <= 1.0
