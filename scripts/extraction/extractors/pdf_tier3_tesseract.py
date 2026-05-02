"""Tier-3 PDF extractor: rasterize pages and run Tesseract directly.

Tier-3 is the no-VLM backstop — used when tier-0 produced garbage,
tier-1 (Docling) and tier-2 (VLM) are both unavailable, and we still
need *something* searchable. Equivalent to running ``ocrmypdf`` but
without writing a new PDF; we just want the text.

Same rasterizer as tier-2 (pdf2image / poppler). Same lazy-import
pattern.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..result import ExtractionResult, PageResult


class TesseractUnavailable(Exception):
    pass


def probe() -> str | None:
    """Return tesseract binary version if present, else None."""
    import shutil
    import subprocess

    binary = shutil.which("tesseract")
    if not binary:
        return None
    try:
        r = subprocess.run(
            [binary, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    line = (r.stdout or r.stderr).strip().splitlines()
    return line[0] if line else None


def extract(
    pdf: Path,
    *,
    pages: list[int] | None = None,
    dpi: int = 300,
    lang: str = "eng",
    settings: dict[str, Any] | None = None,
) -> ExtractionResult:
    """Run pdf2image + Tesseract over `pages` (or all pages)."""
    try:
        from pdf2image import convert_from_path  # type: ignore[import-untyped]
        import pytesseract  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:
        raise TesseractUnavailable(
            "pdf2image and pytesseract are required. "
            "Run: uv sync --extra extraction"
        ) from exc

    if probe() is None:
        raise TesseractUnavailable(
            "tesseract binary not found on PATH. Install via your package "
            "manager (e.g. brew install tesseract)."
        )

    pdf = Path(pdf)
    if pages is None:
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(pdf))
            pages = list(range(1, len(reader.pages) + 1))
        except Exception:
            pages = []

    page_results: list[PageResult] = []
    chunks: list[str] = []
    warnings: list[str] = []
    for page_no in pages:
        try:
            images = convert_from_path(
                str(pdf), dpi=dpi, first_page=page_no, last_page=page_no
            )
        except Exception as exc:
            warnings.append(f"page {page_no}: rasterization failed: {exc}")
            page_results.append(
                PageResult(
                    page_number=page_no,
                    text="",
                    method="tesseract",
                    tier=3,
                    garbled=True,
                    garble_reasons=["rasterization failed"],
                )
            )
            continue
        if not images:
            continue
        try:
            text = pytesseract.image_to_string(images[0], lang=lang) or ""
        except Exception as exc:
            warnings.append(f"page {page_no}: tesseract failed: {exc}")
            text = ""
        chunks.append(text)
        page_results.append(
            PageResult(
                page_number=page_no,
                text=text,
                method="tesseract",
                tier=3,
            )
        )

    full = "\n\n".join(c.strip() for c in chunks if c.strip())
    return ExtractionResult(
        text=full,
        method=f"tesseract:{lang}",
        tier=3,
        settings={"dpi": dpi, "lang": lang, "pages": list(pages), **(settings or {})},
        warnings=warnings,
        page_results=page_results,
    )
