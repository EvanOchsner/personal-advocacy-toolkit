"""Plaintext extraction for trusted-source documents.

Delegates to ``scripts.extraction`` for HTML and PDF (so the cascade's
garble detection + tier-1+ fallbacks apply to reference docs too) and
keeps small in-module helpers for plain text and ``.docx``.

Returns the project-local ``ExtractionResult`` — a flatter type than
``scripts.extraction.result.ExtractionResult`` that carries just what
``scripts.references.ingest`` needs (text, method label, optional title,
warnings). The cascade's per-page detail is collapsed away here; the
references pipeline doesn't paginate.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from scripts.extraction import cascade
from scripts.extraction.extractors import html_tier0_stdlib, pdf_tier0_pypdf


@dataclass
class ExtractionResult:
    text: str
    method: str
    title: str | None = None
    warnings: list[str] = field(default_factory=list)


_HTML_TYPES = {"text/html", "application/xhtml+xml"}
_TEXT_TYPES = {"text/plain", "text/markdown"}
_PDF_TYPES = {"application/pdf"}
_DOCX_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_DOC_TYPES = {"application/msword"}


def _content_type_from_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".html": "text/html",
        ".htm": "text/html",
        ".xhtml": "application/xhtml+xml",
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
    }.get(suffix, "application/octet-stream")


def normalize_content_type(declared: str | None, path: Path) -> str:
    """Best content-type guess: declared if recognized, else by suffix."""
    if declared:
        ct = declared.split(";", 1)[0].strip().lower()
        if ct in _HTML_TYPES | _TEXT_TYPES | _PDF_TYPES | _DOCX_TYPES | _DOC_TYPES:
            return ct
    return _content_type_from_suffix(path)


def extract(
    raw_bytes: bytes,
    content_type: str,
    *,
    source_path: Path | None = None,
) -> ExtractionResult:
    """Extract plaintext from `raw_bytes` using the best available method."""
    if content_type in _HTML_TYPES:
        return _extract_html(raw_bytes)

    if content_type in _TEXT_TYPES:
        decoded = raw_bytes.decode("utf-8", errors="replace")
        return ExtractionResult(text=decoded, method="identity")

    if content_type in _PDF_TYPES:
        return _extract_pdf(raw_bytes)

    if content_type in _DOCX_TYPES:
        return _extract_docx(raw_bytes)

    if content_type in _DOC_TYPES:
        return ExtractionResult(
            text="",
            method="no-extractor",
            warnings=[
                "legacy .doc format is not supported; convert to .docx or PDF "
                "and re-ingest. Raw bytes are preserved for manual review."
            ],
        )

    return ExtractionResult(
        text="",
        method="no-extractor",
        warnings=[
            f"no plaintext extractor for content-type {content_type!r}; "
            "raw bytes are preserved for manual review."
        ],
    )


def _extract_html(raw_bytes: bytes) -> ExtractionResult:
    """Reference HTML extraction.

    For references we stay on the cheap path by default — most ``.gov``
    HTML is well-formed and Trafilatura's main-content guess sometimes
    drops the very legal text we care about. Callers that hit a
    JS-rendered statute page should ingest via the evidence
    ``document-extraction`` skill instead, which runs the full cascade.
    """
    text, title, _charset = html_tier0_stdlib.render_html(raw_bytes)
    return ExtractionResult(text=text, method="html.parser", title=title)


def _extract_pdf(raw_bytes: bytes) -> ExtractionResult:
    """Reference PDF extraction via the cascade's PDF tier 0.

    We do *not* run OCR for references: ``.gov`` source PDFs almost
    always have a real text layer, and a missing layer is itself
    diagnostic — the user should re-fetch the HTML version.
    """
    warnings: list[str] = []
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
        fh.write(raw_bytes)
        tmp_path = Path(fh.name)
    try:
        if not pdf_tier0_pypdf.pdf_has_text_layer(tmp_path):
            warnings.append(
                "PDF has no text layer — extracted text will be empty. "
                "Try fetching the HTML version instead, or ingest as evidence "
                "via `python -m scripts.extraction` to run OCR / VLM fallback."
            )
            text = ""
        else:
            text = pdf_tier0_pypdf.extract_text(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return ExtractionResult(text=text, method="pypdf", warnings=warnings)


def _extract_docx(raw_bytes: bytes) -> ExtractionResult:
    """Extract text from a .docx using python-docx (already a project dep)."""
    try:
        import docx  # type: ignore[import-untyped]
    except ImportError:
        return ExtractionResult(
            text="",
            method="no-extractor",
            warnings=["python-docx not installed; cannot extract .docx plaintext."],
        )
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as fh:
        fh.write(raw_bytes)
        tmp_path = Path(fh.name)
    try:
        document = docx.Document(str(tmp_path))
        paragraphs = [p.text for p in document.paragraphs]
        title = paragraphs[0].strip() if paragraphs and paragraphs[0].strip() else None
        text = "\n".join(paragraphs)
    finally:
        tmp_path.unlink(missing_ok=True)
    return ExtractionResult(text=text, method="python-docx", title=title)


__all__ = [
    "ExtractionResult",
    "extract",
    "normalize_content_type",
    # Re-export so callers wanting full cascade access don't have to
    # know the internal package layout.
    "cascade",
]
