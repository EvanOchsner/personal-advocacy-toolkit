"""Convert heterogeneous exhibit source files into single PDF pages.

Supported input types:
  - .pdf    : passed through
  - .txt/.md: rendered with reportlab
  - .docx   : converted via LibreOffice (`soffice --headless`) if
              available; otherwise raises.
  - .png/.jpg/.jpeg: wrapped as a single-image PDF page.

Each conversion returns a Path to a PDF in `workdir`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ._pdfutil import render_text_to_pdf


TEXT_SUFFIXES = {".txt", ".md", ".markdown"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


class ConversionError(RuntimeError):
    pass


def to_pdf(src: Path, workdir: Path, *, title: str | None = None) -> Path:
    """Return a PDF path for `src`, converting into `workdir` if needed."""
    if not src.is_file():
        raise FileNotFoundError(f"Exhibit source missing: {src}")
    suffix = src.suffix.lower()
    workdir.mkdir(parents=True, exist_ok=True)

    if suffix == ".pdf":
        return src

    if suffix in TEXT_SUFFIXES:
        out = workdir / f"{src.stem}.pdf"
        render_text_to_pdf(
            src.read_text(encoding="utf-8", errors="replace"),
            out,
            title=title,
            monospace=True,
        )
        return out

    if suffix == ".docx":
        return _docx_to_pdf(src, workdir)

    if suffix in IMAGE_SUFFIXES:
        return _image_to_pdf(src, workdir)

    raise ConversionError(f"Unsupported exhibit type: {src.suffix} ({src})")


def _docx_to_pdf(src: Path, workdir: Path) -> Path:
    """Use LibreOffice/soffice in headless mode to produce a PDF."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise ConversionError(
            f"Cannot convert {src.name}: LibreOffice (`soffice`) not found "
            "on PATH. Install it, or convert the .docx to PDF by hand and "
            "point the manifest at the PDF."
        )
    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(workdir), str(src)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ConversionError(
            f"soffice failed on {src}: {result.stderr.strip() or result.stdout.strip()}"
        )
    out = workdir / f"{src.stem}.pdf"
    if not out.is_file():
        raise ConversionError(f"soffice did not produce expected PDF at {out}")
    return out


def _image_to_pdf(src: Path, workdir: Path) -> Path:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    out = workdir / f"{src.stem}.pdf"
    c = canvas.Canvas(str(out), pagesize=LETTER)
    w, h = LETTER
    margin = 0.5 * inch
    c.drawImage(
        str(src),
        margin,
        margin,
        width=w - 2 * margin,
        height=h - 2 * margin,
        preserveAspectRatio=True,
        anchor="c",
    )
    c.showPage()
    c.save()
    return out
