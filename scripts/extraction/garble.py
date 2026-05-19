"""Garble detection — does the cheap extractor's output look real?

Cheap, deterministic signals only. No language models, no perplexity
scoring; we want this to be auditable and reproducible. The cascade
calls ``score_text`` per page (PDFs) or per document (HTML) and
escalates to the next tier when ``garbled`` is True.

Tunable thresholds are kept module-level so a case author can override
them in a manual ``overrides.yaml`` if they're working with a corpus
where the defaults misfire (e.g. a deliberately short cover page).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Pattern for the (cid:NNN) glyph fallback that pypdf emits when it
# can't map a glyph back to a unicode codepoint — a strong signal that
# the PDF is using subset fonts or bezier-curve glyph approximations.
_CID_PATTERN = re.compile(r"\(cid:\d+\)")
# Replacement-char-heavy text usually means a charset failure or
# garbage glyph mapping.
_REPLACEMENT_CHAR = "�"
# A "word-like token" for the word-shape check.
_WORD_RE = re.compile(r"[A-Za-z]{2,}")
_TOKEN_RE = re.compile(r"\S+")
# Per-codepoint ASCII Latin gate for the english_token_ratio check.
_LATIN_LETTER = re.compile(r"[A-Za-z]")
# Punctuation we strip from token edges before scoring. Includes ASCII
# punctuation + a few Unicode dashes that show up in real-world text.
_TOKEN_EDGE_PUNCT = "\"'`.,;:!?()[]{}<>—–-_/\\|*&^%$#@~"


# ---- Defaults ----------------------------------------------------------

DEFAULT_MIN_CHARS_PER_PAGE = 50
DEFAULT_MIN_CHARS_DOC = 200
DEFAULT_MAX_CID_RATIO = 0.02  # any nontrivial CID-glyph density is bad
DEFAULT_MAX_NONPRINTABLE_RATIO = 0.05
DEFAULT_MIN_WORD_SHAPE_RATIO = 0.40
# Minimum fraction of word-like tokens whose letters are all ASCII
# Latin (post-NFC). Trips homoglyph-substituted text: Cyrillic
# lookalikes (а, е, о, р, с, х) survive NFC unchanged and fall outside
# [A-Za-z], so even partial substitution lands well below this floor.
# Tunable per-case in overrides.yaml.
DEFAULT_MIN_ENGLISH_TOKEN_RATIO = 0.85
# HTML-specific: tier 1 (Trafilatura) is considered "empty" if the
# extracted text is < N chars while the raw bytes are > 10x that. This
# is the JS-rendered-only signal.
DEFAULT_HTML_RAW_OVER_TEXT_RATIO = 10.0
DEFAULT_HTML_MIN_CHARS_FOR_NON_EMPTY = 200


@dataclass
class GarbleScore:
    """Result of running ``score_text`` on a string."""

    garbled: bool
    reasons: list[str] = field(default_factory=list)
    # Useful diagnostics for the cascade to log / stash in the recipe.
    chars: int = 0
    cid_ratio: float = 0.0
    nonprintable_ratio: float = 0.0
    word_shape_ratio: float = 0.0
    english_token_ratio: float = 1.0


def english_token_ratio(text: str) -> float:
    """Fraction of word-like tokens whose letters are all ASCII Latin.

    A token *qualifies* if it contains at least one alphabetic
    codepoint (so standalone numbers or pure punctuation are
    excluded). It *passes* if every alphabetic codepoint in it lies
    in ``[A-Za-z]``.

    Returns 1.0 when no qualifying tokens exist — i.e. the signal is
    silent on degenerate input. Returns 0.0 when qualifying tokens
    exist but none of them are pure Latin (heavy homoglyph
    substitution, or genuine non-English text). Catches the homoglyph
    case where the *first* Latin run inside a token still matches
    ``[A-Za-z]{2,}`` (so word_shape_ratio doesn't fire) but the token
    as a whole is mixed-script.
    """
    nfc = unicodedata.normalize("NFC", text)
    qualifying = 0
    pure_latin = 0
    for raw in _TOKEN_RE.findall(nfc):
        stripped = raw.strip(_TOKEN_EDGE_PUNCT)
        if not stripped:
            continue
        has_letter = False
        has_non_latin_letter = False
        for ch in stripped:
            if ch.isalpha():
                has_letter = True
                if not _LATIN_LETTER.match(ch):
                    has_non_latin_letter = True
                    break
        if not has_letter:
            continue
        qualifying += 1
        if not has_non_latin_letter:
            pure_latin += 1
    if qualifying == 0:
        return 1.0
    return pure_latin / qualifying


def score_text(
    text: str,
    *,
    pages: int | None = None,
    min_chars_per_page: int = DEFAULT_MIN_CHARS_PER_PAGE,
    min_chars_doc: int = DEFAULT_MIN_CHARS_DOC,
    max_cid_ratio: float = DEFAULT_MAX_CID_RATIO,
    max_nonprintable_ratio: float = DEFAULT_MAX_NONPRINTABLE_RATIO,
    min_word_shape_ratio: float = DEFAULT_MIN_WORD_SHAPE_RATIO,
    min_english_token_ratio: float = DEFAULT_MIN_ENGLISH_TOKEN_RATIO,
) -> GarbleScore:
    """Score `text` for "did the cheap extractor lie to us?".

    `pages` is the originating page count when scoring a whole PDF
    (used for the chars/page floor); pass None when scoring a single
    page or a non-paginated document like HTML.
    """
    score = GarbleScore(garbled=False)
    score.chars = len(text)

    if score.chars == 0:
        score.garbled = True
        score.reasons.append("empty extraction")
        return score

    # CID-glyph density — small numerator, but the *presence* of any
    # CID glyphs at all is suspicious past a tiny absolute count.
    cid_chars = sum(len(m.group(0)) for m in _CID_PATTERN.finditer(text))
    score.cid_ratio = cid_chars / max(1, score.chars)
    if score.cid_ratio > max_cid_ratio:
        score.garbled = True
        score.reasons.append(
            f"cid-glyph ratio {score.cid_ratio:.3f} > {max_cid_ratio:.3f}"
        )

    # Non-printable / replacement-char ratio.
    bad = sum(
        1
        for ch in text
        if ch == _REPLACEMENT_CHAR
        or (ord(ch) < 0x20 and ch not in "\t\n\r")
    )
    score.nonprintable_ratio = bad / max(1, score.chars)
    if score.nonprintable_ratio > max_nonprintable_ratio:
        score.garbled = True
        score.reasons.append(
            f"non-printable ratio {score.nonprintable_ratio:.3f} > {max_nonprintable_ratio:.3f}"
        )

    # Word-shape ratio: tokens that look like real words / total
    # tokens. Defeats glyph-substitution PDFs that produce random-
    # letter blobs ("J6n4mTpQbFc").
    tokens = _TOKEN_RE.findall(text)
    if tokens:
        word_like = sum(1 for tok in tokens if _WORD_RE.search(tok))
        score.word_shape_ratio = word_like / len(tokens)
        if score.word_shape_ratio < min_word_shape_ratio:
            score.garbled = True
            score.reasons.append(
                f"word-shape ratio {score.word_shape_ratio:.3f} < {min_word_shape_ratio:.3f}"
            )

    # English-token ratio: catches semantic-level corruption
    # (homoglyph substitution) where the extracted bytes look fine to
    # every other signal but words contain Cyrillic / Greek lookalike
    # letters. The right escalation when this fires is OCR (tier 2 or
    # 3), NOT another text-layer extractor — Docling reads the same
    # glyph stream and produces the same homoglyphed output.
    score.english_token_ratio = english_token_ratio(text)
    if score.english_token_ratio < min_english_token_ratio:
        score.garbled = True
        score.reasons.append(
            f"english-token ratio {score.english_token_ratio:.3f} < "
            f"{min_english_token_ratio:.3f} (homoglyph signal — escalate to OCR)"
        )

    # Char-count floors.
    if pages is not None and pages > 0:
        per_page = score.chars / pages
        if per_page < min_chars_per_page:
            score.garbled = True
            score.reasons.append(
                f"chars/page {per_page:.1f} < {min_chars_per_page}"
            )
    else:
        if score.chars < min_chars_doc:
            score.garbled = True
            score.reasons.append(
                f"document length {score.chars} < {min_chars_doc}"
            )

    return score


def html_extract_is_empty(
    extracted_chars: int,
    raw_bytes_len: int,
    *,
    min_chars: int = DEFAULT_HTML_MIN_CHARS_FOR_NON_EMPTY,
    raw_over_text_ratio: float = DEFAULT_HTML_RAW_OVER_TEXT_RATIO,
) -> bool:
    """True when the HTML extractor probably needs a JS-rendered fallback.

    Heuristic: extracted text is short AND the raw bytes are much
    larger. SPAs ship a tiny static body and inject content via JS,
    so the raw payload is dominated by ``<script>`` content.
    """
    if extracted_chars >= min_chars:
        return False
    if raw_bytes_len <= 0:
        return True
    return raw_bytes_len / max(1, extracted_chars) > raw_over_text_ratio
