"""Benchmark-gated regression tests for the PAT extraction cascade.

Pulls the synthetic-gold corpus from the sibling ``pdf-plaintext-extraction``
package: three Gutenberg excerpts × seven variants (clean + six poisoning
techniques). For each variant, runs the cascade and asserts the resulting
token-F1 / normalized-edit-distance lands inside a per-variant floor.

This module skips entirely when the ``[benchmark]`` extra isn't
installed — keeps a base CI run green for contributors who haven't
checked out the benchmark.

Floors are tuned to the current cascade behavior; variants where the
cascade has known defects (homoglyph, rasterize) are marked
``xfail(strict=True)`` so the marker auto-trips when those defects are
fixed (PR 2, PR 3).
"""

from __future__ import annotations

import json

import pytest

pdf_pte = pytest.importorskip(
    "pdf_plaintext_extraction.benchmark",
    reason="install with `uv sync --extra benchmark` to run the benchmark tests",
)

from scripts.extraction.cascade import extract  # noqa: E402


# Per-variant (min_f1, max_ned). Anything outside the window fails.
FLOORS: dict[str, tuple[float, float]] = {
    "clean": (0.98, 0.02),
    "char_spacing": (0.90, 0.10),
    "invisible_text": (0.95, 0.05),
    "metadata_swap": (0.98, 0.02),
    "watermark": (0.95, 0.05),
    "homoglyph": (0.85, 0.15),
    "rasterize": (0.90, 0.10),
}

# Variants the cascade is known to fail on today.
# ``strict=True`` would mean an unexpected pass also fails — useful
# for catching silent improvements. Empty for now: the english_token_ratio
# signal in garble.py escalates homoglyph past tier 0, OCR reads the
# visual Latin, and the variant joins the passing set.
#
# Historical: ``rasterize`` looked broken in early serff benchmark
# runs (pat-cascade F1=0), but with PAT's ``[extraction]`` extra
# installed the cascade falls through to Docling's rapid-OCR
# pipeline and recovers the text. The defect surfaces only when the
# `extraction` extra is missing.
KNOWN_FAILURES: set[str] = set()


@pytest.fixture(scope="session")
def corpus_root():
    return pdf_pte.ensure_corpus()


def _cases(corpus_root):
    """Flatten manifest into (source_id, variant_name, pdf_path, reference)."""
    out = []
    for entry in pdf_pte.iter_ground_truth(corpus_root):
        if entry.clean_pdf_path:
            out.append(
                (entry.source_id, "clean", entry.clean_pdf_path, entry.normalized_text)
            )
        for v in entry.poisoned:
            out.append(
                (entry.source_id, v.technique, v.path, entry.normalized_text)
            )
    return out


def _case_id(case):
    return f"{case[0]}|{case[1]}"


@pytest.fixture(scope="session")
def cases(corpus_root):
    return _cases(corpus_root)


def _params(corpus_root):
    """pytest collection helper: materialize the corpus eagerly so
    parametrize sees the cases. Runs at collection time."""
    return _cases(corpus_root)


def pytest_generate_tests(metafunc):
    # Parametrize ``case`` for tests that ask for it. We compute the
    # corpus at collection time so each (source, variant) pair shows up
    # as a separate test entry in pytest output.
    if "case" not in metafunc.fixturenames:
        return
    try:
        corpus_root = pdf_pte.ensure_corpus()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"could not materialize benchmark corpus: {exc}")
        return
    cases = _cases(corpus_root)
    ids = [_case_id(c) for c in cases]
    marked = []
    for c in cases:
        marks = [pytest.mark.xfail(strict=True)] if c[1] in KNOWN_FAILURES else []
        marked.append(pytest.param(c, marks=marks, id=_case_id(c)))
    metafunc.parametrize("case", marked)


def test_cascade_meets_floor(case):
    source_id, variant, pdf_path, reference = case
    min_f1, max_ned = FLOORS[variant]

    result = extract(
        pdf_path,
        vlm_provider="tesseract",
        interactive=False,
        verbose=False,
    )
    f1 = pdf_pte.token_f1(result.text, reference)
    ned = pdf_pte.normalized_edit_distance(result.text, reference)

    assert f1 >= min_f1, (
        f"{source_id}|{variant}: token_f1={f1:.3f} < floor {min_f1:.3f} "
        f"(method={result.method}, tier={result.tier})"
    )
    assert ned <= max_ned, (
        f"{source_id}|{variant}: ned={ned:.3f} > ceiling {max_ned:.3f} "
        f"(method={result.method}, tier={result.tier})"
    )


def test_no_silent_regressions(cases):
    """Record the full F1/NED matrix to a gitignored baseline file.
    Informational only — not a gate. Useful for diffing across cascade
    changes."""
    from pathlib import Path

    rows = []
    for source_id, variant, pdf_path, reference in cases:
        result = extract(
            pdf_path,
            vlm_provider="tesseract",
            interactive=False,
            verbose=False,
        )
        rows.append(
            {
                "source_id": source_id,
                "variant": variant,
                "f1": round(pdf_pte.token_f1(result.text, reference), 4),
                "ned": round(pdf_pte.normalized_edit_distance(result.text, reference), 4),
                "method": result.method,
                "tier": result.tier,
            }
        )
    baseline = Path(__file__).parent / ".benchmark-baseline.json"
    baseline.write_text(json.dumps(rows, indent=2) + "\n")
    assert len(rows) == len(cases)
