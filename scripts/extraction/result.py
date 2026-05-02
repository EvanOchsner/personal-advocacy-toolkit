"""Common result dataclasses for the extraction cascade.

Every extractor (tier-0 stdlib, tier-1 Docling/Trafilatura, tier-2
VLM, tier-3 Tesseract backstop) returns ``ExtractionResult``. The
cascade combines per-tier results and chooses the winner (lowest tier
whose output passes the garble check, falling back as needed).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PageResult:
    """Per-page outcome for PDF extraction.

    A PDF can mix passable text-layer pages with one or two
    bezier-glyph or photo-of-text pages; the cascade re-extracts only
    the bad pages with a heavier tier and stitches the result together.
    """

    page_number: int  # 1-based
    text: str
    method: str
    tier: int
    garbled: bool = False
    garble_reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Output of any extractor or the cascade as a whole."""

    text: str
    method: str  # e.g. "pypdf@4" / "docling@2.x" / "tesseract@5.4 via vlm"
    tier: int
    settings: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    # Per-page detail, populated for PDF results. None for
    # single-document formats (HTML, email, image).
    page_results: list[PageResult] | None = None
    # Overrides actually applied during this extraction (subset of the
    # sidecar; reflects which keys were *used*, not just defined).
    overrides_applied: dict[str, Any] = field(default_factory=dict)
    # Name of the VLM provider used (if any). One of:
    # "tesseract", "claude", "openai", "olmocr", "http", or None.
    vlm_provider: str | None = None
    # Title (HTML / docx) — kept here for parity with the old
    # references/extract.py result type so call sites can migrate
    # without losing fields.
    title: str | None = None
    # Optional language hint detected/declared by the extractor.
    charset: str | None = None

    def title_or_none(self) -> str | None:
        return self.title or None

    def to_metadata_dict(self) -> dict[str, Any]:
        """Compact dict suitable for embedding in a structured JSON sidecar."""
        return {
            "method": self.method,
            "tier": self.tier,
            "settings": self.settings,
            "warnings": list(self.warnings),
            "vlm_provider": self.vlm_provider,
            "title": self.title,
            "charset": self.charset,
            "overrides_applied": dict(self.overrides_applied),
            "page_results": (
                [
                    {
                        "page_number": p.page_number,
                        "method": p.method,
                        "tier": p.tier,
                        "garbled": p.garbled,
                        "garble_reasons": p.garble_reasons,
                        "notes": p.notes,
                    }
                    for p in self.page_results
                ]
                if self.page_results is not None
                else None
            ),
        }
