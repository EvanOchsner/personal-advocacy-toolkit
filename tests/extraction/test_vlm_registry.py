"""VLM provider registry — name → instance, availability reporting.

We don't exercise the actual provider .transcribe_page() here (those
each depend on optional extras and external services). We do pin
the registry's contract: get_provider returns the right type,
unknown names raise, and available_providers reports a row per
provider with the privacy flag set correctly.
"""
from __future__ import annotations

import pytest

from scripts.extraction.vlm import VLMProviderError, available_providers, get_provider
from scripts.extraction.vlm.tesseract import TesseractProvider


def test_default_provider_is_tesseract() -> None:
    p = get_provider(None)
    assert isinstance(p, TesseractProvider)
    assert p.name == "tesseract"
    assert p.requires_network is False
    assert p.requires_consent is False


def test_explicit_tesseract() -> None:
    p = get_provider("tesseract")
    assert p.name == "tesseract"


def test_get_provider_routes_by_name() -> None:
    assert get_provider("olmocr").name == "olmocr"
    assert get_provider("claude").name == "claude"
    assert get_provider("openai").name == "openai"
    assert get_provider("http").name == "http"


def test_unknown_provider_raises() -> None:
    with pytest.raises(VLMProviderError, match="unknown VLM provider"):
        get_provider("definitely-not-a-provider")


def test_network_providers_set_consent_flag() -> None:
    for name in ("claude", "openai", "http"):
        p = get_provider(name)
        assert p.requires_network is True, name
        assert p.requires_consent is True, name


def test_local_providers_do_not_require_consent() -> None:
    for name in ("tesseract", "olmocr"):
        p = get_provider(name)
        assert p.requires_network is False, name
        assert p.requires_consent is False, name


def test_available_providers_returns_all_known() -> None:
    rows = {row["name"]: row for row in available_providers()}
    for name in ("tesseract", "olmocr", "claude", "openai", "http"):
        assert name in rows, f"missing {name}"
        assert "available" in rows[name]
        assert "requires_network" in rows[name]


def test_unavailable_providers_carry_install_hint() -> None:
    # Whatever the local environment looks like, any provider that
    # reports available=False should also include an install hint
    # (except `http`, which has no extra to install).
    for row in available_providers():
        if row["name"] == "http":
            continue
        if not row.get("available"):
            assert "hint" in row, f"{row['name']} missing install hint"
