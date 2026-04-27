"""Shared PDF helpers for ingest pipelines.

Centralizes the OCR + text-extraction primitives that were previously
private to ``scripts.packet.compile_reference``. The packet's reference
compiler and the ``pdf_to_text`` ingester both need the same three
operations:

  - decide whether a PDF already has an extractable text layer,
  - run ``ocrmypdf`` on it if not (with a graceful fallback when the
    binary isn't installed),
  - extract plaintext via pypdf.

``ocrmypdf`` stays an optional system binary, never a Python dependency.
A missing binary is a stderr warning, not a hard failure — image-only
PDFs simply pass through without OCR'd text. The ingester records this
as ``ocr_applied: false`` so a reviewer can spot the gap.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def pdf_has_text_layer(pdf: Path) -> bool:
    """Return True if `pdf` has any extractable text on any page."""
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return True  # Can't inspect; assume yes and skip OCR.
    try:
        reader = PdfReader(str(pdf))
    except Exception:
        return True
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            continue
        if text.strip():
            return True
    return False


def ocrmypdf_version() -> str | None:
    """Return the installed ocrmypdf version string, or None if absent."""
    binary = shutil.which("ocrmypdf")
    if not binary:
        return None
    try:
        result = subprocess.run(
            [binary, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def ocr_pdf(src: Path, workdir: Path) -> tuple[Path, bool]:
    """Run `ocrmypdf` on `src`; return (path, ocr_applied).

    Returns the OCR'd path if OCR ran successfully, else `src`. The
    boolean is True only when OCR actually produced a new artifact.

    If `ocrmypdf` is not on PATH, emits a stderr warning and returns
    (src, False). Never raises for a missing binary — OCR is a
    nice-to-have, not a build prerequisite.
    """
    if pdf_has_text_layer(src):
        return src, False
    binary = shutil.which("ocrmypdf")
    if not binary:
        print(
            f"warning: {src.name} appears to be an image-only PDF and "
            "ocrmypdf is not on PATH; skipping OCR.",
            file=sys.stderr,
        )
        return src, False
    workdir.mkdir(parents=True, exist_ok=True)
    out = workdir / f"ocr-{src.stem}.pdf"
    result = subprocess.run(
        [binary, "--skip-text", str(src), str(out)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not out.is_file():
        print(
            f"warning: ocrmypdf failed on {src.name}; using original. "
            f"stderr: {result.stderr.strip()[:200]}",
            file=sys.stderr,
        )
        return src, False
    return out, True


def extract_text(pdf: Path) -> str:
    """Concatenate `extract_text()` from every page of `pdf`.

    Returns an empty string on any error (missing pypdf, unreadable
    file, encrypted document). Pages with whitespace-only text are
    dropped; the remaining chunks are joined with a blank line.
    """
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return ""
    try:
        reader = PdfReader(str(pdf))
    except Exception:
        return ""
    chunks: list[str] = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        if t.strip():
            chunks.append(t.strip())
    return "\n\n".join(chunks)


def page_count(pdf: Path) -> int:
    """Return the number of pages in `pdf`, or 0 if unreadable."""
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return 0
    try:
        reader = PdfReader(str(pdf))
    except Exception:
        return 0
    return len(reader.pages)
