"""Privacy gate — network providers can't run without per-case consent.

The cascade calls into a small set of helpers: ``_maybe_consent``
checks whether a network provider may run; when it can't (no consent,
no case_root, non-interactive mode), the cascade records a warning
and falls through. These tests pin that contract directly so the
guardrail can't accidentally regress.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.extraction import cascade, consent
from scripts.extraction.cascade import CascadeContext


def test_local_providers_pass_consent_check(case_root) -> None:
    ctx = CascadeContext(file=case_root / "x.pdf", case_root=case_root)
    # tesseract has requires_consent=False — always allowed.
    assert cascade._maybe_consent(ctx, "tesseract", description={}) is True
    # olmocr also local.
    assert cascade._maybe_consent(ctx, "olmocr", description={}) is True


def test_network_provider_blocked_in_non_interactive_mode(case_root) -> None:
    ctx = CascadeContext(
        file=case_root / "x.pdf",
        case_root=case_root,
        interactive=False,
    )
    assert cascade._maybe_consent(ctx, "claude", description={}) is False
    # Did NOT silently grant consent.
    assert not consent.has_consent(case_root, "claude")


def test_network_provider_blocked_when_no_case_root() -> None:
    """No case_root means we can't record consent — refuse, don't ship data."""
    ctx = CascadeContext(file=Path("/tmp/x.pdf"), case_root=None, interactive=True)
    assert cascade._maybe_consent(ctx, "claude", description={}) is False


def test_network_provider_allowed_after_recorded_consent(case_root) -> None:
    consent.record_consent(case_root, "claude", granted=True)
    ctx = CascadeContext(file=case_root / "x.pdf", case_root=case_root, interactive=False)
    # interactive=False normally blocks, but explicit recorded consent overrides.
    assert cascade._maybe_consent(ctx, "claude", description={}) is True


def test_network_provider_re_blocked_after_denial_recorded(case_root) -> None:
    consent.record_consent(case_root, "openai", granted=False)
    ctx = CascadeContext(file=case_root / "x.pdf", case_root=case_root, interactive=False)
    assert cascade._maybe_consent(ctx, "openai", description={}) is False


def test_consent_is_per_provider_not_global(case_root) -> None:
    consent.record_consent(case_root, "claude", granted=True)
    ctx = CascadeContext(file=case_root / "x.pdf", case_root=case_root, interactive=False)
    assert cascade._maybe_consent(ctx, "claude", description={}) is True
    assert cascade._maybe_consent(ctx, "openai", description={}) is False


def test_unknown_provider_returns_false(case_root) -> None:
    """A misconfigured override pointing at an unknown provider should
    not crash the cascade — it should return False so we fall through."""
    ctx = CascadeContext(file=case_root / "x.pdf", case_root=case_root, interactive=True)
    assert cascade._maybe_consent(ctx, "no-such-provider", description={}) is False


def test_external_processing_recorded_when_network_provider_runs(
    case_root, make_simple_pdf, monkeypatch
) -> None:
    """Smoke test: when a network VLM provider successfully transcribes
    a page, the cascade should append a row to vlm-consent.yaml's
    externally_processed list. We simulate by force_tier=2 and a
    mocked network provider."""
    pytest.importorskip("pypdf")

    # Pre-grant consent so the gate doesn't block.
    consent.record_consent(case_root, "claude", granted=True)

    pdf = make_simple_pdf(pages=["x"])  # tier 0 will be garbled

    # Mock get_provider to return a simple recording network provider.
    from scripts.extraction.vlm.base import VLMProvider

    class _FakeNetworkProvider(VLMProvider):
        name = "claude"
        requires_network = True
        requires_consent = True

        def transcribe_page(self, png_bytes, *, hints):
            return "VLM transcribed text " * 20

    # Stub tier-2 to return a clean page result so external processing
    # gets recorded.
    from scripts.extraction.extractors import pdf_tier2_vlm
    from scripts.extraction.result import ExtractionResult, PageResult

    def fake_extract(pdf_, *, provider, pages, **kwargs):
        text = "VLM transcribed text " * 20
        return ExtractionResult(
            text=text,
            method="vlm:claude",
            tier=2,
            page_results=[
                PageResult(page_number=p, text=text, method="vlm:claude", tier=2)
                for p in (pages or [])
            ],
            vlm_provider="claude",
        )

    monkeypatch.setattr(pdf_tier2_vlm, "extract", fake_extract)
    monkeypatch.setattr(
        cascade, "get_provider", lambda name, **kw: _FakeNetworkProvider()
    )

    # Force tier 1 to bail so we end up at tier 2.
    from scripts.extraction.extractors import pdf_tier1_docling

    def boom(*a, **k):
        raise pdf_tier1_docling.DoclingUnavailable("test env")

    monkeypatch.setattr(pdf_tier1_docling, "extract", boom)

    cascade.extract(pdf, case_root=case_root, vlm_provider="claude")

    rows = consent.list_externally_processed_files(case_root)
    assert len(rows) == 1
    assert rows[0]["provider"] == "claude"
    assert rows[0]["pages"]  # at least one page was sent
