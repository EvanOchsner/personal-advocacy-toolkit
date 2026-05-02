"""Tier-1 HTML extractor: Trafilatura.

Trafilatura (Apache 2.0) is far better than the stdlib at digging
out main-content text from messy / template-heavy HTML, and it
exposes structural hints we can carry into the readable text.
"""
from __future__ import annotations

from typing import Any

from ..result import ExtractionResult


class TrafilaturaUnavailable(Exception):
    pass


def probe() -> str | None:
    try:
        import trafilatura  # type: ignore[import-untyped]
    except ModuleNotFoundError:
        return None
    return getattr(trafilatura, "__version__", "unknown")


def extract(raw_bytes: bytes, *, settings: dict[str, Any] | None = None) -> ExtractionResult:
    try:
        import trafilatura  # type: ignore[import-untyped]
    except ModuleNotFoundError as exc:
        raise TrafilaturaUnavailable(
            "trafilatura not installed. Run: uv sync --extra extraction"
        ) from exc

    # Decode for trafilatura — it accepts str input.
    decoded = raw_bytes.decode("utf-8", errors="replace")
    text = trafilatura.extract(
        decoded,
        include_comments=False,
        include_tables=True,
        favor_recall=True,
        with_metadata=False,
    ) or ""

    # Best-effort title via metadata.
    title = None
    try:
        meta = trafilatura.extract_metadata(decoded)
        if meta is not None:
            title = getattr(meta, "title", None)
    except Exception:
        title = None

    return ExtractionResult(
        text=text,
        method=f"trafilatura@{probe() or 'unknown'}",
        tier=1,
        settings={**(settings or {})},
        title=title,
    )
