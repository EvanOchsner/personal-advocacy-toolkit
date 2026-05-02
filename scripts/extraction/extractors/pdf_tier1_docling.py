"""Tier-1 PDF extractor: Docling.

Docling (MIT) does layout-aware PDF parsing — it handles bezier-glyph
PDFs, multi-column reflow, and tables much better than pypdf. The
cascade reaches for it when tier-0's text trips the garble detector.

Lazy-imports the dependency: a base install (no ``[extraction]``
extra) just sees ``DoclingUnavailable`` from ``probe()`` and the
cascade prints an actionable hint.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..result import ExtractionResult, PageResult


class DoclingUnavailable(Exception):
    """Raised when the cascade asks for Docling and it isn't installed."""


def probe() -> str | None:
    """Return Docling version string if importable, else None."""
    try:
        import docling  # type: ignore[import-untyped]
    except ModuleNotFoundError:
        return None
    return getattr(docling, "__version__", "unknown")


def extract(pdf: Path, *, settings: dict[str, Any] | None = None) -> ExtractionResult:
    """Run Docling on a PDF and return ExtractionResult with per-page text."""
    try:
        from docling.document_converter import DocumentConverter  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:
        raise DoclingUnavailable(
            "Docling is not installed. Run: uv sync --extra extraction"
        ) from exc

    pdf = Path(pdf)
    converter = DocumentConverter()
    result = converter.convert(str(pdf))

    # Docling exposes a ``DoclingDocument`` on the result. The exact
    # accessor names have shifted between releases; we try the
    # markdown export first (stable across recent versions) and fall
    # back to per-page text iteration where possible.
    document = getattr(result, "document", None)
    full_text = ""
    page_texts: list[str] = []
    if document is not None:
        try:
            full_text = document.export_to_markdown()
        except (AttributeError, TypeError):
            full_text = ""
        # Per-page text — best-effort. If the API doesn't expose
        # paginated access, leave the page list empty and let the
        # cascade treat the whole-document text as a single block.
        try:
            for i, page in enumerate(document.pages or [], start=1):  # type: ignore[union-attr]
                try:
                    page_texts.append(page.export_to_markdown())  # type: ignore[union-attr]
                except (AttributeError, TypeError):
                    page_texts.append("")
        except (AttributeError, TypeError):
            page_texts = []

    page_results = [
        PageResult(
            page_number=i + 1,
            text=t,
            method="docling",
            tier=1,
        )
        for i, t in enumerate(page_texts)
    ]

    method = f"docling@{probe() or 'unknown'}"
    return ExtractionResult(
        text=full_text,
        method=method,
        tier=1,
        settings={"page_count": len(page_texts) or None, **(settings or {})},
        page_results=page_results or None,
    )
