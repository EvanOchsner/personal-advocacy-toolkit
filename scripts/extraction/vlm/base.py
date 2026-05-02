"""Provider ABC for the tier-2 VLM extractor.

A provider is a small object with a single hot method:
``transcribe_page(png_bytes, *, hints) -> str``. The cascade owns
batching across pages; providers operate one page at a time so the
abstraction stays simple and testable.

The ``requires_network`` flag drives the privacy guardrail: any
provider with ``requires_network=True`` triggers a per-case consent
check before its first use, recorded in
``<case>/extraction/vlm-consent.yaml``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class VLMProviderError(RuntimeError):
    pass


class VLMProvider(ABC):
    name: str  # short stable identifier — used in the recipe
    requires_network: bool = False  # True => privacy guardrail kicks in
    requires_consent: bool = False   # alias of requires_network for callers

    @abstractmethod
    def transcribe_page(self, png_bytes: bytes, *, hints: dict[str, Any]) -> str:
        """Return markdown / plaintext for the given page image."""

    def describe(self) -> dict[str, Any]:
        """Recipe-friendly description of how this provider was configured."""
        return {
            "name": self.name,
            "requires_network": self.requires_network,
        }
