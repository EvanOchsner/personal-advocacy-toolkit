"""Tier-2 HTML extractor: render with Playwright, then re-extract.

For SPAs and JS-rendered pages, the static HTML body has no useful
text — Playwright (Apache 2.0) drives a real Chromium so we can wait
for ``DOMContentLoaded`` (or a longer ``networkidle``) and then dump
the rendered HTML. The dumped HTML is fed back through tier 1
(Trafilatura) so the structure-aware extraction wins on the rendered
output too.

Inputs are accepted in two modes:

  - ``url``: navigate to it
  - ``raw_bytes``: write to a temp file and load via ``file://``;
    useful for pages saved to disk before the user lost network
    access to the original.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from ..result import ExtractionResult
from . import html_tier1_trafilatura


class PlaywrightUnavailable(Exception):
    pass


def probe() -> str | None:
    try:
        import playwright  # type: ignore[import-untyped]  # noqa: F401
    except ModuleNotFoundError:
        return None
    try:
        from importlib.metadata import version

        return version("playwright")
    except Exception:
        return "unknown"


def _render(target_url: str, *, wait_until: str = "networkidle", timeout_ms: int = 15000) -> str:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:
        raise PlaywrightUnavailable(
            "playwright not installed. Run: uv sync --extra extraction "
            "&& playwright install chromium"
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(target_url, wait_until=wait_until, timeout=timeout_ms)
            return page.content()
        finally:
            browser.close()


def extract(
    *,
    url: str | None = None,
    raw_bytes: bytes | None = None,
    wait_until: str = "networkidle",
    timeout_ms: int = 15000,
    settings: dict[str, Any] | None = None,
) -> ExtractionResult:
    if not url and raw_bytes is None:
        raise ValueError("html_tier2_playwright.extract requires url= or raw_bytes=")

    tmpfile: Path | None = None
    try:
        if url is None:
            assert raw_bytes is not None
            tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
            tmp.write(raw_bytes)
            tmp.flush()
            tmp.close()
            tmpfile = Path(tmp.name)
            target_url = tmpfile.resolve().as_uri()
        else:
            target_url = url

        rendered = _render(
            target_url,
            wait_until=wait_until,
            timeout_ms=timeout_ms,
        )
    finally:
        if tmpfile is not None:
            tmpfile.unlink(missing_ok=True)

    # Run tier 1 over the rendered HTML so we keep main-content
    # extraction discipline rather than dumping every menu and footer.
    inner = html_tier1_trafilatura.extract(rendered.encode("utf-8"))

    return ExtractionResult(
        text=inner.text,
        method=f"playwright+{inner.method}",
        tier=2,
        settings={
            "wait_until": wait_until,
            "timeout_ms": timeout_ms,
            **(settings or {}),
        },
        title=inner.title,
        warnings=list(inner.warnings),
    )
