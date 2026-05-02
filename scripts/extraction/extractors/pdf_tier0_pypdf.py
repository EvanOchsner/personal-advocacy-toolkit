"""Tier-0 PDF extractor: stdlib + ``pypdf``.

Ported from the previous ``scripts/ingest/_pdf.py``. Stays the
default fast path for any PDF with a usable text layer; the cascade
only escalates to tier 1+ when garble is detected. ``ocrmypdf`` is
treated as it was before: an optional system binary, never a Python
dependency. A missing binary is a stderr warning.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from ..result import ExtractionResult, PageResult


def pdf_has_text_layer(pdf: Path) -> bool:
    """Return True if `pdf` has any extractable text on any page."""
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return True  # Can't inspect; assume yes and skip OCR.
    try:
        reader = PdfReader(str(pdf))
    except Exception:
        return True
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            continue
        if text.strip():
            return True
    return False


def ocrmypdf_version() -> str | None:
    """Return the installed ocrmypdf version string, or None if absent."""
    binary = shutil.which("ocrmypdf")
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def ocr_pdf(src: Path, workdir: Path) -> tuple[Path, bool]:
    """Run `ocrmypdf` on `src`; return (path, ocr_applied).

    Returns the OCR'd path if OCR ran successfully, else `src`. The
    boolean is True only when OCR actually produced a new artifact.

    If `ocrmypdf` is not on PATH, emits a stderr warning and returns
    (src, False). Never raises for a missing binary.
    """
    if pdf_has_text_layer(src):
        return src, False
    binary = shutil.which("ocrmypdf")
    if not binary:
        print(
            f"warning: {src.name} appears to be an image-only PDF and "
            "ocrmypdf is not on PATH; skipping OCR.",
            file=sys.stderr,
        )
        return src, False
    workdir.mkdir(parents=True, exist_ok=True)
    out = workdir / f"ocr-{src.stem}.pdf"
    result = subprocess.run(
        [binary, "--skip-text", str(src), str(out)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not out.is_file():
        print(
            f"warning: ocrmypdf failed on {src.name}; using original. "
            f"stderr: {result.stderr.strip()[:200]}",
            file=sys.stderr,
        )
        return src, False
    return out, True


def extract_text(pdf: Path) -> str:
    """Concatenate ``extract_text()`` from every page of ``pdf``."""
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return ""
    try:
        reader = PdfReader(str(pdf))
    except Exception:
        return ""
    chunks: list[str] = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        if t.strip():
            chunks.append(t.strip())
    return "\n\n".join(chunks)


def extract_pages(pdf: Path) -> list[str]:
    """Return one string per page (preserving order, including empty pages)."""
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return []
    try:
        reader = PdfReader(str(pdf))
    except Exception:
        return []
    out: list[str] = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        out.append(t)
    return out


def page_count(pdf: Path) -> int:
    """Return the number of pages in `pdf`, or 0 if unreadable."""
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return 0
    try:
        reader = PdfReader(str(pdf))
    except Exception:
        return 0
    return len(reader.pages)


def extract(pdf: Path, *, run_ocrmypdf: bool = True) -> ExtractionResult:
    """Tier-0 cascade entry point for PDFs.

    Behavior is intentionally identical to the prior
    ``scripts.ingest.pdf_to_text`` pipeline: detect text layer, run
    ``ocrmypdf --skip-text`` if missing and the binary is on PATH,
    extract text via pypdf.
    """
    pdf = Path(pdf)
    notes: list[str] = []
    ocr_applied = False
    ocr_engine: str | None = None

    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        if pdf_has_text_layer(pdf):
            working_pdf = pdf
        elif run_ocrmypdf:
            working_pdf, ocr_applied = ocr_pdf(pdf, workdir)
            if ocr_applied:
                ocr_engine = ocrmypdf_version()
            else:
                notes.append(
                    "image-only PDF; ocrmypdf unavailable or failed — "
                    "extracted text will be empty"
                )
        else:
            working_pdf = pdf
            notes.append(
                "image-only PDF; tier 0 cannot extract without ocrmypdf"
            )
        per_page = extract_pages(working_pdf)
        full_text = "\n\n".join(p.strip() for p in per_page if p.strip())

    page_results = [
        PageResult(
            page_number=i + 1,
            text=text,
            method="pypdf+ocrmypdf" if ocr_applied else "pypdf",
            tier=0,
        )
        for i, text in enumerate(per_page)
    ]

    settings: dict[str, Any] = {
        "ocr_applied": ocr_applied,
        "ocr_engine": ocr_engine,
        "page_count": len(per_page),
    }

    return ExtractionResult(
        text=full_text,
        method="pypdf+ocrmypdf" if ocr_applied else "pypdf",
        tier=0,
        settings=settings,
        warnings=list(notes),
        page_results=page_results,
    )
