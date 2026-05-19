"""Tests for scripts.extraction.reconcile (cross-check + arbitration)."""
from __future__ import annotations

from scripts.extraction.reconcile import (
    PageDisagreement,
    quality_score,
    reconcile_pages,
    token_f1,
)
from scripts.extraction.result import PageResult


# ---- token_f1 ---------------------------------------------------------

def test_token_f1_identical_text_is_one() -> None:
    assert token_f1("hello world", "hello world") == 1.0


def test_token_f1_disjoint_text_is_zero() -> None:
    assert token_f1("alpha beta", "gamma delta") == 0.0


def test_token_f1_empty_both_is_one() -> None:
    assert token_f1("", "") == 1.0


def test_token_f1_empty_one_side_is_zero() -> None:
    assert token_f1("", "hello") == 0.0
    assert token_f1("hello", "") == 0.0


def test_token_f1_partial_overlap_is_between_zero_and_one() -> None:
    # 2 of 3 tokens overlap on each side -> precision = recall = 2/3
    f1 = token_f1("alpha beta gamma", "alpha beta delta")
    assert 0.5 < f1 < 1.0


# ---- quality_score ----------------------------------------------------

def test_quality_score_clean_english_beats_homoglyph() -> None:
    clean = "the quick brown fox jumps over the lazy dog"
    homo = "thе quick brоwn fоx jumps оver the lаzy dоg"  # noqa: RUF001
    assert quality_score(clean) > quality_score(homo)


def test_quality_score_zero_for_empty_text() -> None:
    assert quality_score("") == 0.0


# ---- reconcile_pages --------------------------------------------------

def _page(n: int, text: str, method: str = "pypdf", tier: int = 0) -> PageResult:
    return PageResult(page_number=n, text=text, method=method, tier=tier)


def test_reconcile_passes_through_when_pages_agree() -> None:
    primary = [_page(1, "hello world this is a test of agreement")]
    shadow = [
        _page(1, "hello world this is a test of agreement", method="tesseract", tier=3)
    ]
    reconciled, disagreements = reconcile_pages(primary, shadow)
    assert reconciled == primary
    assert disagreements == []


def test_reconcile_picks_shadow_when_primary_is_homoglyphed() -> None:
    # Primary is homoglyphed (low english_token_ratio, low quality);
    # shadow is plain English. F1 disagreement triggers the
    # arbitration, quality_score picks the shadow.
    homo = "thе quick brоwn fоx jumps оver thе lаzy dоg ".strip()  # noqa: RUF001
    clean = "the quick brown fox jumps over the lazy dog"
    primary = [_page(1, homo)]
    shadow = [_page(1, clean, method="tesseract", tier=3)]

    reconciled, disagreements = reconcile_pages(primary, shadow)

    assert len(disagreements) == 1
    d = disagreements[0]
    assert isinstance(d, PageDisagreement)
    assert d.winner == "shadow"
    assert d.f1 < 0.85
    # The reconciled page carries the shadow's text + a note.
    assert reconciled[0].text == clean
    assert reconciled[0].method == "tesseract"
    assert any("cross-check disagreement" in note for note in reconciled[0].notes)


def test_reconcile_keeps_primary_when_shadow_is_worse() -> None:
    # Primary reads as clean English; shadow returns fragmented OCR
    # noise (low word_shape_ratio). Even though they disagree, primary
    # wins on quality_score.
    primary = [_page(1, "hello world this is a coherent sentence")]
    shadow = [_page(1, "h e l l o w o r l d", method="tesseract", tier=3)]
    reconciled, disagreements = reconcile_pages(primary, shadow)
    assert len(disagreements) == 1
    assert disagreements[0].winner == "primary"
    assert reconciled[0].text == primary[0].text


def test_reconcile_ignores_empty_shadow_page() -> None:
    primary = [_page(1, "hello world this is the primary output")]
    shadow = [_page(1, "", method="tesseract", tier=3)]
    reconciled, disagreements = reconcile_pages(primary, shadow)
    assert disagreements == []
    assert reconciled == primary


def test_reconcile_passes_through_when_shadow_missing_page() -> None:
    primary = [
        _page(1, "page one body text content"),
        _page(2, "page two body text content"),
    ]
    shadow = [_page(1, "page one body text content", method="tesseract", tier=3)]
    reconciled, disagreements = reconcile_pages(primary, shadow)
    assert disagreements == []
    assert [p.page_number for p in reconciled] == [1, 2]


def test_reconcile_agreement_floor_is_tunable() -> None:
    # With a sky-high floor, even tiny disagreements get flagged.
    primary = [_page(1, "the quick brown fox jumps over the lazy dog")]
    shadow = [
        _page(
            1,
            "the quick brown fox jumps over the lazy cat",  # one-word swap
            method="tesseract",
            tier=3,
        )
    ]
    reconciled_default, dis_default = reconcile_pages(primary, shadow)
    assert dis_default == []

    reconciled_strict, dis_strict = reconcile_pages(
        primary, shadow, agreement_floor=0.99
    )
    assert len(dis_strict) == 1
