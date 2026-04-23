#!/usr/bin/env python3
"""Tamper-evident web-page capture: PDF + DOM snapshot + manifest entry.

Format-support / backend matrix:

    +-------------------------+-----------+--------------------------------+
    | Backend                 | Status    | Notes                           |
    +-------------------------+-----------+--------------------------------+
    | playwright (chromium)   | PROTOTYPE | Used when the `playwright`     |
    |                         |           | package is importable AND a    |
    |                         |           | browser is installed.          |
    | chrome --headless       | FALLBACK  | Used when a chrome / chromium  |
    |                         |           | binary is on PATH.             |
    | (none available)        | STUB      | Emits a placeholder PDF + DOM  |
    |                         |           | so the pipeline still records  |
    |                         |           | capture metadata; pipeline     |
    |                         |           | callers should treat these as  |
    |                         |           | NON-EVIDENCE-GRADE.            |
    +-------------------------+-----------+--------------------------------+

What gets recorded in the evidence manifest, regardless of backend:

    - captured URL (as requested)
    - retrieval timestamp (UTC ISO-8601)
    - backend used
    - sha256 of the saved PDF
    - sha256 of the saved DOM snapshot
    - HTTP status from the fetch (when the backend exposes it)

Scope note (prototype): playwright is NOT declared in pyproject.toml
because the browser binaries are heavy (~200MB) and most users of this
toolkit won't need screenshot capture. We degrade gracefully when it's
absent. Users who need evidence-grade web capture should:

    pip install playwright
    playwright install chromium

Usage:
    uv run python -m scripts.ingest.screenshot_capture URL \
        --out-dir data/screenshots/ \
        [--manifest data/screenshots/manifest.yaml] \
        [--backend auto|playwright|chrome|stub] \
        [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.ingest._manifest import append_entry


# --------------------------------------------------------------------------- #
# Backend detection
# --------------------------------------------------------------------------- #


def _have_playwright() -> bool:
    try:
        import playwright  # type: ignore  # noqa: F401
    except ImportError:
        return False
    return True


def _chrome_binary() -> str | None:
    for name in (
        "google-chrome",
        "chromium",
        "chromium-browser",
        "chrome",
    ):
        path = shutil.which(name)
        if path:
            return path
    # macOS default install path
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if Path(mac).exists():
        return mac
    return None


def select_backend(requested: str = "auto") -> str:
    if requested != "auto":
        return requested
    if _have_playwright():
        return "playwright"
    if _chrome_binary() is not None:
        return "chrome"
    return "stub"


# --------------------------------------------------------------------------- #
# Backends
# --------------------------------------------------------------------------- #


def _capture_playwright(url: str, pdf_out: Path, dom_out: Path) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright  # type: ignore

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        response = page.goto(url, wait_until="networkidle")
        status = response.status if response is not None else None
        dom = page.content()
        dom_out.write_text(dom, encoding="utf-8")
        page.emulate_media(media="screen")
        page.pdf(path=str(pdf_out), print_background=True)
        browser.close()
    return {"backend": "playwright", "http_status": status}


def _capture_chrome(url: str, pdf_out: Path, dom_out: Path) -> dict[str, Any]:
    binary = _chrome_binary()
    if binary is None:
        raise RuntimeError("chrome binary not found")
    # PDF via chrome headless.
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(
            [
                binary,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                f"--user-data-dir={td}",
                f"--print-to-pdf={pdf_out}",
                url,
            ],
            check=True,
            timeout=60,
        )
    # DOM via a best-effort urllib fetch. This is NOT a true rendered-DOM
    # snapshot — it's the raw HTML as served — but for the chrome-headless
    # fallback path we don't have an easy way to extract the post-JS DOM.
    # Callers needing true DOM fidelity should use the playwright backend.
    status: int | None = None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "advocacy-toolkit/0.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            dom_out.write_bytes(resp.read())
    except Exception as e:  # noqa: BLE001 - fallback must not crash the capture
        dom_out.write_text(f"[urllib fetch failed: {e}]\n", encoding="utf-8")
    return {"backend": "chrome", "http_status": status}


def _capture_stub(url: str, pdf_out: Path, dom_out: Path) -> dict[str, Any]:
    """Emit placeholder artifacts so the pipeline still records metadata.

    These are NOT evidence-grade. The manifest will carry
    `backend: stub` so downstream tools can filter them out of
    evidence packets.
    """
    pdf_out.write_bytes(
        b"%PDF-1.4\n% advocacy-toolkit placeholder (no browser available)\n"
        b"% url=" + url.encode("utf-8") + b"\n"
    )
    dom_out.write_text(
        f"<!-- advocacy-toolkit placeholder DOM for {url} -->\n"
        f"<!-- no browser backend was available at capture time -->\n",
        encoding="utf-8",
    )
    return {"backend": "stub", "http_status": None}


BACKENDS = {
    "playwright": _capture_playwright,
    "chrome": _capture_chrome,
    "stub": _capture_stub,
}


# --------------------------------------------------------------------------- #
# Main capture flow
# --------------------------------------------------------------------------- #


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _url_slug(url: str, max_len: int = 60) -> str:
    import re

    s = re.sub(r"[^A-Za-z0-9._-]+", "-", url).strip("-")
    return (s or "capture")[:max_len]


def capture(
    url: str,
    out_dir: Path,
    backend: str = "auto",
) -> dict[str, Any]:
    """Capture `url` into out_dir. Returns a full manifest entry dict."""
    backend = select_backend(backend)
    if backend not in BACKENDS:
        raise ValueError(f"unknown backend: {backend}")

    timestamp = datetime.now(timezone.utc)
    ts_compact = timestamp.strftime("%Y%m%dT%H%M%SZ")
    slug = _url_slug(url)
    stem = f"{ts_compact}_{slug}"

    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_out = out_dir / f"{stem}.pdf"
    dom_out = out_dir / f"{stem}.dom.html"

    backend_info = BACKENDS[backend](url, pdf_out, dom_out)

    pdf_sha = _sha256_file(pdf_out)
    dom_sha = _sha256_file(dom_out)
    # source_id: stable across same URL + second, to detect dup captures.
    source_id = hashlib.sha256(f"{url}|{ts_compact}".encode("utf-8")).hexdigest()[:16]

    return {
        "source_id": source_id,
        "kind": "screenshot_capture",
        "url": url,
        "retrieved_at": timestamp.isoformat(),
        "backend": backend_info["backend"],
        "http_status": backend_info.get("http_status"),
        "pdf_path": str(pdf_out),
        "pdf_sha256": pdf_sha,
        "dom_path": str(dom_out),
        "dom_sha256": dom_sha,
        "evidence_grade": backend_info["backend"] != "stub",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("url")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument(
        "--backend",
        default="auto",
        choices=["auto", "playwright", "chrome", "stub"],
    )
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    entry = capture(args.url, args.out_dir, backend=args.backend)

    if args.manifest is not None:
        try:
            append_entry(args.manifest, entry, force=args.force)
        except FileExistsError as e:
            print(str(e), file=sys.stderr)
            return 3

    print(
        f"captured {args.url} -> {entry['pdf_path']} "
        f"(backend={entry['backend']}, evidence_grade={entry['evidence_grade']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
