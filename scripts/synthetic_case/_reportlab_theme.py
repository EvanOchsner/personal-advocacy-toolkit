"""Shared reportlab styling for synthetic-case regenerators.

Centralises page size, margins, fonts, the SYNTHETIC watermark, and
the common footer so all PDFs produced by this package share a single
visual theme. Kept small on purpose — the goal is consistency, not
beauty. The SYNTHETIC stamp is the load-bearing piece.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate


SYNTHETIC_STAMP = "SYNTHETIC -- NOT A REAL CASE"
# The markdown sources use an em dash (U+2014). reportlab's default
# Helvetica handles it as a WinAnsi glyph, but to avoid any
# cross-platform surprise we normalise the stamp to ASCII double-dash.


@dataclass(frozen=True)
class Theme:
    page_size: tuple[float, float] = LETTER
    left_margin: float = 0.9 * inch
    right_margin: float = 0.9 * inch
    top_margin: float = 1.0 * inch
    bottom_margin: float = 1.0 * inch
    header_font: str = "Helvetica-Bold"
    header_size: int = 11
    body_font: str = "Helvetica"
    body_size: int = 10
    footer_font: str = "Helvetica-Oblique"
    footer_size: int = 8


THEME = Theme()


def paragraph_styles() -> dict[str, ParagraphStyle]:
    """Return a small named-style dict used by the regenerators."""
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontName=THEME.header_font,
            fontSize=18,
            leading=22,
            spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName=THEME.header_font,
            fontSize=13,
            leading=16,
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["BodyText"],
            fontName=THEME.body_font,
            fontSize=THEME.body_size,
            leading=13,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["BodyText"],
            fontName=THEME.body_font,
            fontSize=9,
            leading=11,
            textColor=(0.3, 0.3, 0.3),
        ),
    }


def draw_synthetic_chrome(c: canvas.Canvas, *, header_title: str) -> None:
    """Draw header, footer, and diagonal watermark on the current page.

    Called from a ``PageTemplate.onPage`` callback; do not call
    ``showPage`` or ``save``.
    """
    w, h = THEME.page_size

    # Watermark (diagonal, light gray).
    c.saveState()
    c.setFont("Helvetica-Bold", 54)
    c.setFillGray(0.88)
    c.translate(w / 2, h / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, SYNTHETIC_STAMP)
    c.restoreState()

    # Header (left: title, right: synthetic stamp).
    c.saveState()
    c.setFont(THEME.header_font, THEME.header_size)
    c.setFillGray(0.1)
    c.drawString(THEME.left_margin, h - 0.55 * inch, header_title)
    c.setFont(THEME.footer_font, THEME.footer_size)
    c.setFillGray(0.3)
    c.drawRightString(w - THEME.right_margin, h - 0.55 * inch, SYNTHETIC_STAMP)
    c.setStrokeGray(0.6)
    c.setLineWidth(0.5)
    c.line(
        THEME.left_margin,
        h - 0.65 * inch,
        w - THEME.right_margin,
        h - 0.65 * inch,
    )
    c.restoreState()

    # Footer.
    c.saveState()
    c.setFont(THEME.footer_font, THEME.footer_size)
    c.setFillGray(0.3)
    c.drawString(
        THEME.left_margin,
        0.55 * inch,
        f"{SYNTHETIC_STAMP} -- The Maryland Mustang teaching example.",
    )
    page_no = c.getPageNumber()
    c.drawRightString(w - THEME.right_margin, 0.55 * inch, f"Page {page_no}")
    c.restoreState()


def make_doc(output: Path, *, title: str, header_title: str) -> BaseDocTemplate:
    """Return a BaseDocTemplate with one full-page frame and the
    synthetic header/footer/watermark drawn on every page.

    Also stamps the SYNTHETIC marker into the PDF /Info dict via
    ``title`` + ``subject`` + ``author``. Author and producer are set
    to non-identifying values; no real person or company appears.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    w, h = THEME.page_size
    frame = Frame(
        THEME.left_margin,
        THEME.bottom_margin,
        w - THEME.left_margin - THEME.right_margin,
        h - THEME.top_margin - THEME.bottom_margin,
        id="body",
        showBoundary=0,
    )

    def _on_page(c: canvas.Canvas, _doc: object) -> None:
        draw_synthetic_chrome(c, header_title=header_title)

    doc = BaseDocTemplate(
        str(output),
        pagesize=THEME.page_size,
        leftMargin=THEME.left_margin,
        rightMargin=THEME.right_margin,
        topMargin=THEME.top_margin,
        bottomMargin=THEME.bottom_margin,
        title=f"{title} ({SYNTHETIC_STAMP})",
        author="advocacy-toolkit synthetic-case regenerator",
        subject=SYNTHETIC_STAMP,
        creator="advocacy-toolkit",
        producer="advocacy-toolkit synthetic-case",
    )
    doc.addPageTemplates([PageTemplate(id="synthetic", frames=[frame], onPage=_on_page)])
    return doc
