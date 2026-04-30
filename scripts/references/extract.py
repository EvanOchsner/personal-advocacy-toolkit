"""Plaintext extraction for trusted-source documents.

Dispatches by content type to the existing project ingesters where one
exists, and falls back to small in-module helpers otherwise. The output
is plain UTF-8 text written to ``references/readable/<slug>.txt`` with
no further processing — section/citation parsing is deferred to a
later iteration.

Supported types (v1):

    text/html, application/xhtml+xml  → scripts.ingest.html_to_text
    application/pdf                   → scripts.ingest._pdf
    text/plain, text/markdown         → identity (decode)
    application/vnd.openxmlformats-
        officedocument.wordprocessingml.document   → python-docx
    application/msword                → unsupported (warning only)

Anything else is recorded as ``method: "no-extractor"`` with a warning.
The raw bytes are still preserved under ``references/raw/`` so the
agent can fall back to manual review.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from scripts.ingest.html_to_text import render_html


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
    """Return the best content-type guess: declared if recognized, else by suffix."""
    if declared:
        ct = declared.split(";", 1)[0].strip().lower()
        if ct in _HTML_TYPES | _TEXT_TYPES | _PDF_TYPES | _DOCX_TYPES | _DOC_TYPES:
            return ct
    return _content_type_from_suffix(path)


def extract(raw_bytes: bytes, content_type: str, *, source_path: Path | None = None) -> ExtractionResult:
    """Extract plaintext from ``raw_bytes`` using the best available method."""
    if content_type in _HTML_TYPES:
        text, title, _charset = render_html(raw_bytes)
        return ExtractionResult(text=text, method="html-to-text", title=title)

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


def _extract_pdf(raw_bytes: bytes) -> ExtractionResult:
    """Extract text from a PDF.

    Reuses ``scripts.ingest._pdf.extract_text`` (which sits on top of
    pypdf). Does not run OCR — image-only PDFs return empty text with a
    warning. The user can run the evidence ``pdf_to_text`` ingester
    separately for OCR if needed; reference docs from ``.gov`` sources
    almost always have a real text layer.
    """
    from scripts.ingest._pdf import extract_text, pdf_has_text_layer

    warnings: list[str] = []
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
        fh.write(raw_bytes)
        tmp_path = Path(fh.name)
    try:
        if not pdf_has_text_layer(tmp_path):
            warnings.append(
                "PDF has no text layer — extracted text will be empty. "
                "Try fetching the HTML version instead, or run the evidence "
                "pdf_to_text ingester (which can OCR via ocrmypdf)."
            )
            text = ""
        else:
            text = extract_text(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return ExtractionResult(text=text, method="pdf-to-text", warnings=warnings)


def _extract_docx(raw_bytes: bytes) -> ExtractionResult:
    """Extract text from a .docx using python-docx (already a project dep)."""
    try:
        import docx  # type: ignore  # python-docx
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
    return ExtractionResult(text=text, method="docx-to-text", title=title)
