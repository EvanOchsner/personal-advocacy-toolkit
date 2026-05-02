"""Vision-language-model providers for tier-2 PDF extraction.

The cascade hands a rendered page (PNG bytes) to a ``VLMProvider``
and expects markdown / plaintext back. Provider selection follows
the project's recommended order:

  1. ``tesseract``  — local OCR, no GPU, no network. Default.
  2. ``olmocr``     — local 7B VLM, GPU recommended. Use when
                      tesseract isn't enough AND privacy matters.
  3. ``claude`` / ``openai`` / ``http`` — cloud / generic-HTTP VLMs.
                      Powerful, but page images leave the machine.
                      Per-case opt-in required (see ``consent.py``).

This module exposes ``VLMProvider`` and ``get_provider(name)``.
"""
from __future__ import annotations

from .base import VLMProvider, VLMProviderError
from .registry import available_providers, get_provider

__all__ = [
    "VLMProvider",
    "VLMProviderError",
    "get_provider",
    "available_providers",
]
