"""Stdlib HTTP fetcher with allowlist enforcement.

Used by ``scripts.references.ingest`` to pull bytes from a URL when the
user has chosen Path B (project-known trusted source) or Path C
(constrained web search). The fetcher:

  - Refuses URLs whose host is on the denylist.
  - Refuses URLs whose host is unknown to the allow/denylist (the
    caller can override with ``allow_unknown=True`` after explicit
    user confirmation, but the default is conservative).
  - Sets a descriptive User-Agent identifying the toolkit so the
    fetched-from server can attribute the traffic.
  - Follows up to 5 redirects (urllib default).
  - Returns raw bytes plus the final URL and content-type. No parsing.

The fetcher is intentionally simple — no retries, no streaming,
no JS rendering. If a target page requires JS, the user can save
the rendered HTML manually (browser → Save Page As) and switch to
Path A (file ingest).
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scripts.references._allowlist import HostClassification, classify_url

USER_AGENT = (
    "personal-advocacy-toolkit/0.0 "
    "(trusted-sources fetcher; "
    "https://github.com/EvanOchsner/personal-advocacy-toolkit)"
)

# Hard cap on response size to protect against runaway downloads.
# 50 MB is generous for a statute or regulation; anything larger is
# likely the wrong target.
DEFAULT_MAX_BYTES = 50 * 1024 * 1024


class FetchError(RuntimeError):
    """Raised for any fetch-side failure the caller should surface."""


class FetchRefused(FetchError):
    """Raised when the allowlist refuses the fetch."""


@dataclass
class FetchResult:
    url: str
    final_url: str
    host: str
    content_type: str
    raw_bytes: bytes
    classification: HostClassification


def fetch(
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    allow_unknown: bool = False,
    timeout: float = 30.0,
    source_path: Path | None = None,
) -> FetchResult:
    """Fetch ``url`` and return its bytes + metadata.

    ``allow_unknown`` lets the caller bypass the "unknown host" refusal
    after the user has explicitly confirmed. ``denied`` hosts are
    always refused regardless.
    """
    classification = classify_url(url, source_path=source_path)
    if classification.verdict == "denied":
        raise FetchRefused(
            f"refused to fetch from {urlparse(url).hostname!r}: "
            f"matches denylist pattern {classification.matched_pattern!r} "
            f"({classification.reason})"
        )
    if classification.verdict == "unknown" and not allow_unknown:
        raise FetchRefused(
            f"refused to fetch from {urlparse(url).hostname!r}: "
            "host is not on the trusted-source allowlist. Either add it to "
            "data/reference_sources.yaml or pass --allow-unknown after "
            "confirming with the user."
        )
    if classification.verdict == "secondary-confirm" and not allow_unknown:
        raise FetchRefused(
            f"refused to fetch from {urlparse(url).hostname!r}: "
            f"host matches {classification.matched_pattern!r} which requires "
            "explicit confirmation. Re-run with --allow-unknown after "
            "confirming with the user."
        )

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(max_bytes + 1)
            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            final_url = resp.geturl()
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code} fetching {url}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise FetchError(f"network error fetching {url}: {e.reason}") from e
    except TimeoutError as e:
        raise FetchError(f"timeout fetching {url}") from e

    if len(raw) > max_bytes:
        raise FetchError(
            f"response from {url} exceeds {max_bytes} bytes; refusing to "
            "ingest. Save the file manually and use file-mode ingest instead."
        )

    return FetchResult(
        url=url,
        final_url=final_url,
        host=urlparse(final_url).hostname or "",
        content_type=content_type,
        raw_bytes=bytes(raw),
        classification=classification,
    )


def describe(result: FetchResult) -> dict[str, Any]:
    """Compact dict view of a fetch result for logging / sidecar embedding."""
    return {
        "url": result.url,
        "final_url": result.final_url,
        "host": result.host,
        "content_type": result.content_type,
        "size_bytes": len(result.raw_bytes),
        "trust": result.classification.verdict,
        "matched_pattern": result.classification.matched_pattern,
    }
