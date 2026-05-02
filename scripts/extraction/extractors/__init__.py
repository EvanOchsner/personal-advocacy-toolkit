"""Per-tier extractor implementations.

Each module exposes a small functional interface so the cascade can
chain tiers without instantiating heavy objects until they're needed:

    pdf_tier0_pypdf.extract(pdf_path, *, settings) -> ExtractionResult
    pdf_tier1_docling.extract(pdf_path, *, settings) -> ExtractionResult
    pdf_tier2_vlm.extract(pdf_path, *, provider, settings) -> ExtractionResult
    pdf_tier3_tesseract.extract(pdf_path, *, settings) -> ExtractionResult
    html_tier0_stdlib.extract(raw_bytes, *, settings) -> ExtractionResult
    html_tier1_trafilatura.extract(raw_bytes, *, settings) -> ExtractionResult
    html_tier2_playwright.extract(url_or_path, *, settings) -> ExtractionResult
    image_tesseract.extract(image_path, *, settings) -> ExtractionResult
    email_stdlib.parse(eml_path, *, attach_dir=...) -> dict + render_text(record)

All optional-dependency tiers do their imports inside the function
body so a base install (without `[extraction]` / `[extraction-vlm]`)
still imports this package without crashing.
"""
from __future__ import annotations
