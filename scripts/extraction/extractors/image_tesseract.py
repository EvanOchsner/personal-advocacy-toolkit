"""Standalone image OCR via Tesseract.

The cascade routes raw images (``.png`` / ``.jpg`` / ``.jpeg`` /
``.tiff``) directly here. Internally the cascade can also call this
to OCR a rasterized PDF page — that path lives in
``pdf_tier3_tesseract``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..result import ExtractionResult


class TesseractUnavailable(Exception):
    pass


def extract(
    image: Path,
    *,
    lang: str = "eng",
    settings: dict[str, Any] | None = None,
) -> ExtractionResult:
    try:
        import pytesseract  # type: ignore[import-untyped]
        from PIL import Image  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:
        raise TesseractUnavailable(
            "pytesseract / Pillow not installed. Run: uv sync --extra extraction"
        ) from exc

    img = Image.open(str(image))
    text = pytesseract.image_to_string(img, lang=lang) or ""
    return ExtractionResult(
        text=text,
        method=f"tesseract:{lang}",
        tier=1,
        settings={"lang": lang, **(settings or {})},
    )
