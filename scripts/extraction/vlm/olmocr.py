"""Local-VLM provider — reference implementation against olmOCR.

olmOCR (Apache 2.0) ships a 7B vision-language model fine-tuned for
document transcription. GPU recommended; will be slow on CPU.

This provider is the **recommended escalation** when Tesseract isn't
enough AND privacy matters: nothing leaves the user's machine.

The integration is intentionally minimal — the same shape can be
re-pointed at Qwen2-VL or any other local VLM by subclassing this
class and overriding ``_load`` / ``transcribe_page``.
"""
from __future__ import annotations

import io
from typing import Any

from .base import VLMProvider, VLMProviderError


class OlmOCRProvider(VLMProvider):
    name = "olmocr"
    requires_network = False
    requires_consent = False

    def __init__(self, *, model: str | None = None, device: str | None = None) -> None:
        self.model = model
        self.device = device
        self._pipeline = None

    def _load(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        try:
            import olmocr  # type: ignore[import-untyped]
        except ModuleNotFoundError as exc:
            raise VLMProviderError(
                "olmocr provider requires the [extraction-vlm] extra. "
                "Run: uv sync --extra extraction-vlm"
            ) from exc
        # The exact entry point in olmocr's API has shifted between
        # releases. We probe a few common shapes; if none fit, the
        # provider raises and the cascade can fall back to tesseract.
        loader = (
            getattr(olmocr, "load_pipeline", None)
            or getattr(olmocr, "Pipeline", None)
            or getattr(olmocr, "load", None)
        )
        if loader is None:
            raise VLMProviderError(
                "olmocr is installed but no recognized entry point "
                "(load_pipeline / Pipeline / load) was found. Update the "
                "olmocr provider to match the installed version's API."
            )
        kwargs = {}
        if self.model:
            kwargs["model"] = self.model
        if self.device:
            kwargs["device"] = self.device
        self._pipeline = loader(**kwargs) if kwargs else loader()
        return self._pipeline

    def transcribe_page(self, png_bytes: bytes, *, hints: dict[str, Any]) -> str:
        pipeline = self._load()
        try:
            from PIL import Image  # type: ignore[import-untyped]
        except ModuleNotFoundError as exc:
            raise VLMProviderError(
                "Pillow is required for olmocr provider. "
                "Run: uv sync --extra extraction"
            ) from exc
        img = Image.open(io.BytesIO(png_bytes))
        # Best-effort calling convention. olmocr versions have shipped
        # callable pipelines and methods named .run / .__call__ /
        # .transcribe. Try them in turn.
        for attr in ("transcribe", "run", "__call__"):
            fn = getattr(pipeline, attr, None)
            if callable(fn):
                try:
                    out = fn(img)
                except Exception as exc:
                    raise VLMProviderError(f"olmocr.{attr} failed: {exc}") from exc
                if isinstance(out, str):
                    return out
                if isinstance(out, dict):
                    return str(out.get("text") or out.get("markdown") or "")
                return str(out)
        raise VLMProviderError(
            "olmocr pipeline has no recognized transcribe method"
        )

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "model": self.model, "device": self.device}
