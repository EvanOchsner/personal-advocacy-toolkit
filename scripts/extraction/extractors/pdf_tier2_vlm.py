"""Tier-2 PDF extractor: rasterize garbled pages and run a VLM provider.

This tier is reached only when tier-0 (pypdf) and tier-1 (Docling)
both produce text that fails the garble check on one or more pages.
Rather than re-extracting the entire document, the cascade calls this
extractor with the *list of garbled pages*; the rasterizer turns each
into a PNG and the VLM provider transcribes it.

Provider selection follows the project's recommended order:
``tesseract`` (default, local, no network) → ``olmocr`` (local VLM,
GPU) → cloud providers (Claude / OpenAI / generic HTTP) only with
explicit per-case consent.

Page rasterization uses ``pdf2image`` (which itself depends on the
``poppler`` system binary's ``pdftoppm``). When the dep or binary is
missing, this tier raises ``RasterizationUnavailable`` and the
cascade falls through to tier 3 (Tesseract on the rasterized full
PDF, when possible).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..result import ExtractionResult, PageResult
from ..vlm import VLMProvider


class RasterizationUnavailable(Exception):
    """Raised when ``pdf2image``/poppler aren't available."""


def _rasterize_pages(pdf: Path, pages: list[int], *, dpi: int = 200) -> dict[int, bytes]:
    """Convert specific pages of `pdf` to PNG bytes, keyed by page number (1-based)."""
    try:
        from pdf2image import convert_from_path  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:
        raise RasterizationUnavailable(
            "pdf2image is not installed. Run: uv sync --extra extraction"
        ) from exc

    out: dict[int, bytes] = {}
    # pdf2image expects 1-based page indices via first_page/last_page;
    # render one page at a time so a hostile PDF can't blow up memory
    # on a large page range we mostly don't care about.
    import io  # local import — only needed in the rasterize path

    for page_no in pages:
        try:
            images = convert_from_path(
                str(pdf),
                dpi=dpi,
                first_page=page_no,
                last_page=page_no,
            )
        except Exception:
            # Treat any pdf2image failure as "no raster for this page"
            # — the cascade will mark the page as garbled and move on.
            continue
        if not images:
            continue
        buf = io.BytesIO()
        images[0].save(buf, format="PNG")
        out[page_no] = buf.getvalue()
    return out


def extract(
    pdf: Path,
    *,
    provider: VLMProvider,
    pages: list[int] | None = None,
    dpi: int = 200,
    settings: dict[str, Any] | None = None,
) -> ExtractionResult:
    """Transcribe ``pages`` of ``pdf`` with the given ``provider``.

    If ``pages`` is None, the entire document is rasterized — usually
    not what you want; the cascade computes a targeted page list from
    tier-0/1 garble results and passes it explicitly.
    """
    pdf = Path(pdf)
    if pages is None:
        # Full-document fallback. Open with pypdf to count pages so
        # we can hand the rasterizer an explicit list.
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(pdf))
            pages = list(range(1, len(reader.pages) + 1))
        except Exception:
            pages = []

    page_pngs = _rasterize_pages(pdf, pages, dpi=dpi)

    page_results: list[PageResult] = []
    chunks: list[str] = []
    warnings: list[str] = []
    for page_no in pages:
        png = page_pngs.get(page_no)
        if png is None:
            page_results.append(
                PageResult(
                    page_number=page_no,
                    text="",
                    method=f"vlm:{provider.name}",
                    tier=2,
                    garbled=True,
                    garble_reasons=["rasterization failed"],
                )
            )
            warnings.append(f"page {page_no}: rasterization failed")
            continue
        try:
            text = provider.transcribe_page(png, hints={"page_number": page_no})
        except Exception as exc:
            warnings.append(f"page {page_no}: {provider.name} provider error: {exc}")
            text = ""
        chunks.append(text)
        page_results.append(
            PageResult(
                page_number=page_no,
                text=text,
                method=f"vlm:{provider.name}",
                tier=2,
            )
        )

    full = "\n\n".join(c.strip() for c in chunks if c.strip())
    return ExtractionResult(
        text=full,
        method=f"vlm:{provider.name}",
        tier=2,
        settings={"dpi": dpi, "pages": list(pages), **(settings or {})},
        warnings=warnings,
        page_results=page_results,
        vlm_provider=provider.name,
    )
