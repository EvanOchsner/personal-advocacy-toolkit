"""Provider registry — string name → ``VLMProvider`` instance.

Lazy-imports each provider so a base install (no optional extras)
can still call ``available_providers()`` and discover that only
``tesseract`` is wirable.
"""
from __future__ import annotations

from typing import Any

from .base import VLMProvider, VLMProviderError


_DEFAULT_NAME = "tesseract"


def get_provider(name: str | None = None, **kwargs: Any) -> VLMProvider:
    """Return a configured provider by name.

    ``None`` falls through to the default (``tesseract``). Unknown
    names raise ``VLMProviderError``.
    """
    chosen = (name or _DEFAULT_NAME).strip().lower()
    if chosen == "tesseract":
        from .tesseract import TesseractProvider

        return TesseractProvider(**kwargs)
    if chosen == "olmocr":
        from .olmocr import OlmOCRProvider

        return OlmOCRProvider(**kwargs)
    if chosen == "claude":
        from .claude import ClaudeProvider

        return ClaudeProvider(**kwargs)
    if chosen == "openai":
        from .openai import OpenAIProvider

        return OpenAIProvider(**kwargs)
    if chosen == "http":
        from .http import HTTPProvider

        return HTTPProvider(**kwargs)
    raise VLMProviderError(
        f"unknown VLM provider {name!r}. Known: tesseract, olmocr, claude, openai, http."
    )


def available_providers() -> list[dict[str, Any]]:
    """Return a small status table — one row per provider, with 'available' flag."""
    rows: list[dict[str, Any]] = []
    # tesseract — needs pytesseract + Pillow + system tesseract.
    try:
        import importlib

        importlib.import_module("pytesseract")
        importlib.import_module("PIL")
        rows.append({"name": "tesseract", "requires_network": False, "available": True})
    except ModuleNotFoundError:
        rows.append({
            "name": "tesseract",
            "requires_network": False,
            "available": False,
            "hint": "uv sync --extra extraction (and brew install tesseract)",
        })
    # olmocr — heavy local model.
    try:
        import importlib

        importlib.import_module("olmocr")
        rows.append({"name": "olmocr", "requires_network": False, "available": True})
    except ModuleNotFoundError:
        rows.append({
            "name": "olmocr",
            "requires_network": False,
            "available": False,
            "hint": "uv sync --extra extraction-vlm",
        })
    # claude — needs anthropic SDK.
    try:
        import importlib

        importlib.import_module("anthropic")
        rows.append({"name": "claude", "requires_network": True, "available": True})
    except ModuleNotFoundError:
        rows.append({
            "name": "claude",
            "requires_network": True,
            "available": False,
            "hint": "uv sync --extra llm",
        })
    # openai
    try:
        import importlib

        importlib.import_module("openai")
        rows.append({"name": "openai", "requires_network": True, "available": True})
    except ModuleNotFoundError:
        rows.append({
            "name": "openai",
            "requires_network": True,
            "available": False,
            "hint": "uv sync --extra extraction-cloud-openai",
        })
    # http provider has no extra deps.
    rows.append({"name": "http", "requires_network": True, "available": True})
    return rows


__all__ = ["get_provider", "available_providers"]
