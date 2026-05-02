"""Cascade orchestrator: try cheap → expensive, garble-check, escalate.

The cascade is the public API of this package. Callers hand it a
file path (and optionally a case root for overrides + consent), it
returns a single ``ExtractionResult`` and writes the per-source
recipe + reproducibility script as a side effect.

Tier ordering by document type:

    PDF:     0 (pypdf) → 1 (Docling) → 2 (VLM provider) → 3 (Tesseract)
    HTML:    0 (stdlib) → 1 (Trafilatura) → 2 (Playwright + Trafilatura)
    Email:   0 (stdlib only — single tier)
    Image:   1 (Tesseract direct)

Garble detection is always on. ``ExtractionOverrides.force_tier``
short-circuits the cascade to the requested tier.
"""
from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import consent, garble, overrides
from .extractors import (
    email_stdlib,
    html_tier0_stdlib,
    image_tesseract,
    pdf_tier0_pypdf,
)
from .result import ExtractionResult, PageResult
from .vlm import VLMProviderError, get_provider


@dataclass
class CascadeContext:
    """Per-call context: paths, overrides, provider preferences."""

    file: Path
    case_root: Path | None = None
    overrides: overrides.ExtractionOverrides | None = None
    vlm_provider_name: str | None = None  # default: tesseract
    interactive: bool = True
    verbose: bool = False

    def log(self, msg: str) -> None:
        if self.verbose:
            print(f"  [extraction] {msg}", file=sys.stderr)


def _classify(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in (".html", ".htm", ".xhtml"):
        return "html"
    if suffix == ".eml":
        return "email"
    if suffix in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif"):
        return "image"
    return "unknown"


def _provider_for(ctx: CascadeContext) -> str:
    """Resolve the VLM provider name for this context."""
    if ctx.overrides and ctx.overrides.vlm_provider:
        return ctx.overrides.vlm_provider
    return ctx.vlm_provider_name or "tesseract"


def _maybe_consent(ctx: CascadeContext, provider_name: str, description: dict[str, Any]) -> bool:
    """Privacy guardrail; returns True if the provider may run."""
    from .vlm import get_provider as _get  # local import: keep top clean

    try:
        prov = _get(provider_name)
    except VLMProviderError:
        return False

    if not prov.requires_consent:
        return True

    if ctx.case_root is None:
        # No case root => can't record consent; refuse network providers
        # rather than silently shipping data.
        ctx.log(
            f"refusing network provider {provider_name!r}: no case root, "
            "can't record consent"
        )
        return False

    if consent.has_consent(ctx.case_root, provider_name):
        return True

    if not ctx.interactive:
        ctx.log(
            f"network provider {provider_name!r} not consented for this "
            "case; non-interactive mode — refusing"
        )
        return False

    return consent.prompt_consent_interactive(
        ctx.case_root,
        provider_name,
        description=description,
        file_label=str(ctx.file),
    )


# -----------------------------------------------------------------------------
# Per-format orchestrators
# -----------------------------------------------------------------------------

def extract_pdf(ctx: CascadeContext) -> ExtractionResult:
    """Run the PDF cascade with garble checks per page."""
    ovr = ctx.overrides or overrides.ExtractionOverrides()

    # Tier 0 — pypdf (always run unless force_tier > 0).
    if ovr.force_tier in (None, 0):
        ctx.log("PDF tier 0 — pypdf")
        result = pdf_tier0_pypdf.extract(ctx.file)
        _annotate_pages_with_garble(result, ovr.garble_thresholds)
        if not _has_garbled_pages(result) and ovr.force_tier is None:
            return _finalize(result, ovr)
        if ovr.force_tier == 0:
            return _finalize(result, ovr)
    else:
        result = ExtractionResult(text="", method="skipped", tier=0)

    # Tier 1 — Docling.
    if ovr.force_tier in (None, 1) or _has_garbled_pages(result):
        ctx.log("PDF tier 1 — Docling")
        try:
            from .extractors import pdf_tier1_docling

            tier1 = pdf_tier1_docling.extract(ctx.file)
            _annotate_pages_with_garble(tier1, ovr.garble_thresholds)
            result = _merge_pdf_results(result, tier1)
            if not _has_garbled_pages(result) and ovr.force_tier is None:
                return _finalize(result, ovr)
            if ovr.force_tier == 1:
                return _finalize(result, ovr)
        except Exception as exc:
            result.warnings.append(f"tier 1 (Docling) unavailable: {exc}")

    # Tier 2 — VLM provider.
    if ovr.force_tier in (None, 2) or _has_garbled_pages(result):
        provider_name = _provider_for(ctx)
        garbled_pages = _garbled_page_numbers(result)
        if garbled_pages or ovr.force_tier == 2:
            description = {"force_tier": ovr.force_tier, "pages": garbled_pages}
            if not _maybe_consent(ctx, provider_name, description):
                result.warnings.append(
                    f"tier 2: provider {provider_name!r} blocked by consent / "
                    "availability; falling through"
                )
            else:
                ctx.log(f"PDF tier 2 — VLM:{provider_name} on pages {garbled_pages}")
                try:
                    from .extractors import pdf_tier2_vlm

                    provider = get_provider(provider_name)
                    tier2 = pdf_tier2_vlm.extract(
                        ctx.file,
                        provider=provider,
                        pages=garbled_pages or None,
                    )
                    _annotate_pages_with_garble(tier2, ovr.garble_thresholds)
                    result = _merge_pdf_results(result, tier2)
                    if provider.requires_network and ctx.case_root is not None:
                        consent.record_external_processing(
                            ctx.case_root,
                            source_id=_source_id(ctx.file),
                            file=str(ctx.file),
                            provider_name=provider.name,
                            pages=garbled_pages or [],
                        )
                except Exception as exc:
                    result.warnings.append(f"tier 2 (VLM) failed: {exc}")
        if not _has_garbled_pages(result) and ovr.force_tier is None:
            return _finalize(result, ovr)
        if ovr.force_tier == 2:
            return _finalize(result, ovr)

    # Tier 3 — Tesseract backstop.
    if ovr.force_tier in (None, 3) or _has_garbled_pages(result):
        ctx.log("PDF tier 3 — Tesseract backstop")
        try:
            from .extractors import pdf_tier3_tesseract

            garbled_pages = _garbled_page_numbers(result)
            tier3 = pdf_tier3_tesseract.extract(
                ctx.file,
                pages=garbled_pages or None,
            )
            _annotate_pages_with_garble(tier3, ovr.garble_thresholds)
            result = _merge_pdf_results(result, tier3)
        except Exception as exc:
            result.warnings.append(f"tier 3 (Tesseract) unavailable: {exc}")

    return _finalize(result, ovr)


def extract_html(ctx: CascadeContext, raw_bytes: bytes | None = None) -> ExtractionResult:
    """Run the HTML cascade. ``raw_bytes`` may be supplied to avoid re-reading."""
    ovr = ctx.overrides or overrides.ExtractionOverrides()
    if raw_bytes is None:
        raw_bytes = ctx.file.read_bytes()

    # Tier 0 — stdlib.
    if ovr.force_tier in (None, 0):
        ctx.log("HTML tier 0 — stdlib")
        result = html_tier0_stdlib.extract(raw_bytes)
        score = _score_doc(result, ovr)
        if not score.garbled and ovr.force_tier is None:
            return _finalize(result, ovr)
        if ovr.force_tier == 0:
            return _finalize(result, ovr)
    else:
        result = ExtractionResult(text="", method="skipped", tier=0)

    # Tier 1 — Trafilatura.
    if ovr.force_tier in (None, 1) or _is_doc_garbled(result, ovr):
        ctx.log("HTML tier 1 — Trafilatura")
        try:
            from .extractors import html_tier1_trafilatura

            tier1 = html_tier1_trafilatura.extract(raw_bytes)
            if len(tier1.text) > len(result.text):
                result = tier1
            score = _score_doc(result, ovr)
            empty = garble.html_extract_is_empty(
                len(result.text or ""), len(raw_bytes or b"")
            )
            if not score.garbled and not empty and ovr.force_tier is None:
                return _finalize(result, ovr)
            if ovr.force_tier == 1:
                return _finalize(result, ovr)
        except Exception as exc:
            result.warnings.append(f"tier 1 (Trafilatura) unavailable: {exc}")

    # Tier 2 — Playwright render + Trafilatura.
    if ovr.force_tier in (None, 2) or _is_doc_garbled(result, ovr):
        ctx.log("HTML tier 2 — Playwright")
        try:
            from .extractors import html_tier2_playwright

            tier2 = html_tier2_playwright.extract(raw_bytes=raw_bytes)
            if len(tier2.text) > len(result.text):
                result = tier2
        except Exception as exc:
            result.warnings.append(f"tier 2 (Playwright) unavailable: {exc}")

    return _finalize(result, ovr)


def extract_email(ctx: CascadeContext) -> ExtractionResult:
    """Email cascade is single-tier (stdlib)."""
    return _finalize(email_stdlib.extract(ctx.file), ctx.overrides or overrides.ExtractionOverrides())


def extract_image(ctx: CascadeContext) -> ExtractionResult:
    """Image cascade — Tesseract direct."""
    try:
        result = image_tesseract.extract(ctx.file)
    except image_tesseract.TesseractUnavailable as exc:
        result = ExtractionResult(
            text="",
            method="image-no-extractor",
            tier=0,
            warnings=[str(exc)],
        )
    return _finalize(result, ctx.overrides or overrides.ExtractionOverrides())


# -----------------------------------------------------------------------------
# Top-level dispatch
# -----------------------------------------------------------------------------

def extract(
    file: Path,
    *,
    case_root: Path | None = None,
    override_path: Path | None = None,
    vlm_provider: str | None = None,
    interactive: bool = True,
    verbose: bool = False,
) -> ExtractionResult:
    """Top-level entry point: classify by extension and run the cascade."""
    file = Path(file)
    ovr_path = override_path
    if ovr_path is None and case_root is not None:
        ovr_path = overrides.overrides_path(case_root, _source_id(file))
    ovr = overrides.load_overrides(ovr_path) if ovr_path else overrides.ExtractionOverrides()

    ctx = CascadeContext(
        file=file,
        case_root=case_root,
        overrides=ovr,
        vlm_provider_name=vlm_provider,
        interactive=interactive,
        verbose=verbose,
    )
    kind = _classify(file)
    if kind == "pdf":
        return extract_pdf(ctx)
    if kind == "html":
        return extract_html(ctx)
    if kind == "email":
        return extract_email(ctx)
    if kind == "image":
        return extract_image(ctx)
    raise ValueError(
        f"unknown document type for {file} (suffix {file.suffix!r}); "
        "supported: .pdf, .html/.htm, .eml, .png/.jpg/.jpeg/.tiff"
    )


# -----------------------------------------------------------------------------
# Internals
# -----------------------------------------------------------------------------

def _source_id(file: Path) -> str:
    return hashlib.sha256(Path(file).read_bytes()).hexdigest()[:16]


def _annotate_pages_with_garble(
    result: ExtractionResult,
    thresholds: dict[str, float] | None = None,
) -> None:
    """Mutate ``result.page_results`` in place with garble flags."""
    if result.page_results is None:
        return
    kwargs: dict[str, Any] = {}
    if thresholds:
        kwargs.update({k: v for k, v in thresholds.items()})
    for page in result.page_results:
        score = garble.score_text(page.text, pages=1, **kwargs)
        page.garbled = score.garbled
        page.garble_reasons = list(score.reasons)


def _has_garbled_pages(result: ExtractionResult) -> bool:
    if result.page_results is None:
        return False
    return any(p.garbled for p in result.page_results)


def _garbled_page_numbers(result: ExtractionResult) -> list[int]:
    if result.page_results is None:
        return []
    return [p.page_number for p in result.page_results if p.garbled]


def _score_doc(result: ExtractionResult, ovr: overrides.ExtractionOverrides) -> garble.GarbleScore:
    kwargs: dict[str, Any] = {}
    if ovr.garble_thresholds:
        kwargs.update({k: v for k, v in ovr.garble_thresholds.items()})
    return garble.score_text(result.text, pages=None, **kwargs)


def _is_doc_garbled(result: ExtractionResult, ovr: overrides.ExtractionOverrides) -> bool:
    return _score_doc(result, ovr).garbled


def _merge_pdf_results(base: ExtractionResult, replacement: ExtractionResult) -> ExtractionResult:
    """Stitch ``replacement`` into ``base`` for any pages where ``base`` was garbled.

    Pages that were ungarbled in ``base`` keep ``base``'s text. Pages
    that were garbled in ``base`` are replaced from ``replacement``
    if present and not garbled there. Per-page metadata (method, tier)
    is updated accordingly.
    """
    if base.page_results is None:
        # Tier 0 was skipped — replacement *is* the result.
        merged = ExtractionResult(
            text=replacement.text,
            method=replacement.method,
            tier=replacement.tier,
            settings={**base.settings, **replacement.settings},
            warnings=list(base.warnings) + list(replacement.warnings),
            page_results=replacement.page_results,
            vlm_provider=replacement.vlm_provider,
            title=replacement.title or base.title,
        )
        return merged

    if replacement.page_results is None:
        # Replacement has no per-page detail — best we can do is union
        # the texts at the doc level. Keep base's page list.
        merged_text = replacement.text or base.text
        return ExtractionResult(
            text=merged_text,
            method=f"{base.method}+{replacement.method}",
            tier=max(base.tier, replacement.tier),
            settings={**base.settings, **replacement.settings},
            warnings=list(base.warnings) + list(replacement.warnings),
            page_results=base.page_results,
            vlm_provider=replacement.vlm_provider or base.vlm_provider,
            title=base.title or replacement.title,
        )

    by_page = {p.page_number: p for p in replacement.page_results}
    new_pages: list[PageResult] = []
    for p in base.page_results:
        if p.garbled and p.page_number in by_page:
            rp = by_page[p.page_number]
            if not rp.garbled and rp.text.strip():
                new_pages.append(rp)
                continue
        new_pages.append(p)

    new_text = "\n\n".join(pp.text.strip() for pp in new_pages if pp.text.strip())
    used_replacement_method = any(
        pp.method == replacement.method for pp in new_pages
    )
    return ExtractionResult(
        text=new_text,
        method=(
            f"{base.method}+{replacement.method}"
            if used_replacement_method
            else base.method
        ),
        tier=max(base.tier, replacement.tier) if used_replacement_method else base.tier,
        settings={**base.settings, **replacement.settings},
        warnings=list(base.warnings) + list(replacement.warnings),
        page_results=new_pages,
        vlm_provider=replacement.vlm_provider if used_replacement_method else base.vlm_provider,
        title=base.title or replacement.title,
    )


def _finalize(result: ExtractionResult, ovr: overrides.ExtractionOverrides) -> ExtractionResult:
    """Apply final overrides (skip_pages, strip_text_patterns) to the merged text."""
    if result.page_results is not None and ovr.skip_pages:
        kept = [p for p in result.page_results if p.page_number not in set(ovr.skip_pages)]
        result.page_results = kept
        result.text = "\n\n".join(p.text.strip() for p in kept if p.text.strip())
        result.overrides_applied["skip_pages"] = list(ovr.skip_pages)

    if ovr.strip_text_patterns:
        result.text = ovr.apply_text_strip(result.text)
        result.overrides_applied["strip_text_patterns"] = list(ovr.strip_text_patterns)

    return result
