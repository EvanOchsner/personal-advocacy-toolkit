"""Default VLM provider: local Tesseract OCR.

Not technically a "VLM" — Tesseract is plain OCR — but it slots into
the same interface so the cascade can treat it as the no-network
fallback. Pick this unless quality demonstrably blocks the case.
"""
from __future__ import annotations

import io
from typing import Any

from .base import VLMProvider, VLMProviderError


class TesseractProvider(VLMProvider):
    name = "tesseract"
    requires_network = False
    requires_consent = False

    def __init__(self, *, lang: str = "eng") -> None:
        self.lang = lang

    def transcribe_page(self, png_bytes: bytes, *, hints: dict[str, Any]) -> str:
        try:
            import pytesseract  # type: ignore[import-untyped]
            from PIL import Image  # type: ignore[import-untyped]
        except ModuleNotFoundError as exc:
            raise VLMProviderError(
                "tesseract provider needs pytesseract + Pillow. "
                "Run: uv sync --extra extraction"
            ) from exc
        img = Image.open(io.BytesIO(png_bytes))
        try:
            return pytesseract.image_to_string(img, lang=self.lang) or ""
        except Exception as exc:
            raise VLMProviderError(f"tesseract failed: {exc}") from exc

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "lang": self.lang}
