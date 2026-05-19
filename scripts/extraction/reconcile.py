"""Cross-check + reconciliation for opt-in extractor disagreement detection.

The cascade's normal flow is "first-non-garbled-wins": tier 0 runs,
each page is scored by ``garble.score_text``, garbled pages escalate
to the next tier, and the result is merged. That works when the
existing garble signals catch the failure mode.

Sometimes they don't. Homoglyph substitution defeated every signal
until ``english_token_ratio`` was added; another novel poisoning
technique could slip past the next one. ``reconcile`` is the
belt-and-suspenders second pass: when the caller passes
``cross_check=True`` to :func:`scripts.extraction.cascade.extract`,
the cascade runs tier-3 tesseract as a *shadow* extractor on every
page that already succeeded at tier 0, computes a per-page token-F1
between the two outputs, and flags any page below an agreement floor
for human review. The reconciled output picks the higher-quality
candidate page-by-page using the existing garble diagnostics as a
quality score.

This module deliberately does **not** import the runtime scoring
from `pdf_plaintext_extraction.benchmark.score` — that's a test-only
dependency. The token-F1 implementation here is small and stays
inside the base runtime.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .garble import english_token_ratio
from .result import PageResult

DEFAULT_AGREEMENT_FLOOR = 0.85


def token_f1(predicted: str, reference: str) -> float:
    """Multiset token F1 over whitespace-split tokens.

    Returns 1.0 if both inputs are empty, 0.0 if exactly one is
    empty. Same metric as the synthetic benchmark uses for ground-
    truth scoring — keeping the runtime version locally avoids a
    dependency on the test-only benchmark scoring code.
    """
    pred = predicted.split()
    ref = reference.split()
    if not pred and not ref:
        return 1.0
    if not pred or not ref:
        return 0.0
    pred_c = Counter(pred)
    ref_c = Counter(ref)
    overlap = sum((pred_c & ref_c).values())
    if overlap == 0:
        return 0.0
    precision = overlap / sum(pred_c.values())
    recall = overlap / sum(ref_c.values())
    return 2 * precision * recall / (precision + recall)


def quality_score(text: str) -> float:
    """Rough "how readable is this" score in [0, 2].

    Sum of word_shape_ratio and english_token_ratio. Used as a
    tie-breaker when two extractors disagree on a page: we prefer
    the candidate whose text reads as actual English. Catches both:
      - tier-3 OCR producing fragmented per-glyph tokens
        (low word_shape_ratio); and
      - tier-0 text-layer returning homoglyphed Cyrillic
        (low english_token_ratio).
    """
    from .garble import _TOKEN_RE, _WORD_RE  # local import: tight coupling

    nfc_tokens = _TOKEN_RE.findall(text)
    if not nfc_tokens:
        return 0.0
    word_like = sum(1 for tok in nfc_tokens if _WORD_RE.search(tok))
    word_shape = word_like / len(nfc_tokens)
    return word_shape + english_token_ratio(text)


@dataclass
class PageDisagreement:
    """One per-page disagreement found during reconciliation."""

    page_number: int
    f1: float
    primary_method: str
    shadow_method: str
    primary_snippet: str
    shadow_snippet: str
    winner: str  # "primary" or "shadow"


def reconcile_pages(
    primary: list[PageResult],
    shadow: list[PageResult],
    *,
    agreement_floor: float = DEFAULT_AGREEMENT_FLOOR,
) -> tuple[list[PageResult], list[PageDisagreement]]:
    """Reconcile two extractor outputs page-by-page.

    For each page present in *primary*:
      - If a shadow page exists and its token-F1 against the primary
        page is below ``agreement_floor``, record a
        :class:`PageDisagreement` and pick the higher-quality
        candidate via :func:`quality_score`. If the shadow wins, the
        merged page carries the shadow's text / method / tier but
        keeps the original page number.
      - Otherwise the primary page passes through unchanged.

    Returns ``(reconciled_pages, disagreements)``. The disagreements
    list is meant to surface to the user / to the recipe sidecar so
    a reviewer can audit which pages the cascade had to arbitrate.
    """
    shadow_by_page = {p.page_number: p for p in shadow}
    reconciled: list[PageResult] = []
    disagreements: list[PageDisagreement] = []

    for primary_page in primary:
        shadow_page = shadow_by_page.get(primary_page.page_number)
        if shadow_page is None or not shadow_page.text.strip():
            reconciled.append(primary_page)
            continue

        f1 = token_f1(primary_page.text, shadow_page.text)
        if f1 >= agreement_floor:
            reconciled.append(primary_page)
            continue

        primary_q = quality_score(primary_page.text)
        shadow_q = quality_score(shadow_page.text)
        if shadow_q > primary_q:
            winner = "shadow"
            chosen = PageResult(
                page_number=primary_page.page_number,
                text=shadow_page.text,
                method=shadow_page.method,
                tier=shadow_page.tier,
                garbled=shadow_page.garbled,
                garble_reasons=list(shadow_page.garble_reasons),
                notes=list(primary_page.notes) + list(shadow_page.notes),
            )
        else:
            winner = "primary"
            chosen = primary_page

        disagreements.append(
            PageDisagreement(
                page_number=primary_page.page_number,
                f1=f1,
                primary_method=primary_page.method,
                shadow_method=shadow_page.method,
                primary_snippet=_snippet(primary_page.text),
                shadow_snippet=_snippet(shadow_page.text),
                winner=winner,
            )
        )
        chosen.notes.append(
            f"cross-check disagreement F1={f1:.2f} winner={winner}"
        )
        reconciled.append(chosen)

    return reconciled, disagreements


def _snippet(text: str, length: int = 80) -> str:
    flat = " ".join(text.split())
    return flat[:length]
