"""Small PDF helpers shared across the packet tools.

Rendering is done with reportlab (for from-scratch pages like cover
sheets and separator sheets) and pypdf (for merging). Both are widely
available and pure-Python.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


def merge_pdfs(inputs: list[Path], output: Path) -> None:
    """Concatenate the given PDFs, in order, into `output`."""
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for p in inputs:
        if not p.is_file():
            raise FileNotFoundError(f"Merge input missing: {p}")
        reader = PdfReader(str(p))
        for page in reader.pages:
            writer.add_page(page)
    with output.open("wb") as fh:
        writer.write(fh)


def render_text_to_pdf(
    text: str,
    output: Path,
    *,
    title: str | None = None,
    monospace: bool = False,
) -> None:
    """Render a block of text to a single-column PDF.

    Used for .txt / .md exhibits and generated cover/separator pages.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "body",
        parent=styles["BodyText"],
        fontName="Courier" if monospace else "Helvetica",
        fontSize=10,
        leading=13,
    )
    title_style = ParagraphStyle(
        "title",
        parent=styles["Title"],
        fontSize=16,
        leading=20,
    )
    doc = SimpleDocTemplate(
        str(output),
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title=title or output.stem,
    )
    story: list = []
    if title:
        story.append(Paragraph(_escape(title), title_style))
        story.append(Spacer(1, 0.2 * inch))
    for para in text.split("\n\n"):
        # Preserve intra-paragraph newlines for monospace content.
        if monospace:
            para = para.replace("\n", "<br/>")
        story.append(Paragraph(_escape(para, keep_tags=monospace), body_style))
        story.append(Spacer(1, 0.12 * inch))
    doc.build(story)


def render_separator_page(
    output: Path,
    *,
    label: str,
    title: str,
    description: str,
    date: str | None = None,
) -> None:
    """Render a standard exhibit-separator sheet."""
    output.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output), pagesize=LETTER)
    width, height = LETTER
    c.setFont("Helvetica-Bold", 48)
    c.drawCentredString(width / 2, height - 2.5 * inch, f"Exhibit {label}")
    c.setFont("Helvetica", 18)
    c.drawCentredString(width / 2, height - 3.4 * inch, title)
    if date:
        c.setFont("Helvetica-Oblique", 12)
        c.drawCentredString(width / 2, height - 3.9 * inch, date)
    if description:
        c.setFont("Helvetica", 11)
        _draw_wrapped(
            c,
            description,
            x=1.5 * inch,
            y=height - 5.0 * inch,
            width=width - 3.0 * inch,
            leading=14,
        )
    c.showPage()
    c.save()


def render_cover_page(
    output: Path,
    *,
    heading: str,
    subheading: str | None = None,
    lines: list[str] | None = None,
    footer: str | None = None,
    watermark: str | None = None,
) -> None:
    """Render a cover page for the complaint packet or an appendix."""
    output.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output), pagesize=LETTER)
    width, height = LETTER

    if watermark:
        c.saveState()
        c.setFont("Helvetica-Bold", 60)
        c.setFillGray(0.85)
        c.translate(width / 2, height / 2)
        c.rotate(35)
        c.drawCentredString(0, 0, watermark)
        c.restoreState()

    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(width / 2, height - 1.8 * inch, heading)
    if subheading:
        c.setFont("Helvetica", 14)
        c.drawCentredString(width / 2, height - 2.4 * inch, subheading)

    y = height - 3.5 * inch
    c.setFont("Helvetica", 12)
    for line in lines or []:
        for sub in line.split("\n"):
            c.drawString(1.0 * inch, y, sub)
            y -= 16
        y -= 6

    if footer:
        c.setFont("Helvetica-Oblique", 9)
        _draw_wrapped(
            c,
            footer,
            x=1.0 * inch,
            y=1.2 * inch,
            width=width - 2.0 * inch,
            leading=11,
        )
    c.showPage()
    c.save()


def stamp_watermark(input_pdf: Path, output_pdf: Path, text: str) -> None:
    """Stamp a diagonal watermark onto every page of `input_pdf`."""
    from io import BytesIO

    reader = PdfReader(str(input_pdf))
    # Build a watermark PDF sized to the first page.
    first = reader.pages[0]
    w = float(first.mediabox.width)
    h = float(first.mediabox.height)
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    c.saveState()
    c.setFont("Helvetica-Bold", 60)
    c.setFillGray(0.85)
    c.translate(w / 2, h / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, text)
    c.restoreState()
    c.showPage()
    c.save()
    buf.seek(0)
    stamp_reader = PdfReader(buf)
    stamp_page = stamp_reader.pages[0]

    writer = PdfWriter()
    for page in reader.pages:
        # Attach to the writer BEFORE mutating. ``merge_page`` calls
        # ``replace_contents`` internally; pypdf 6+ deprecates that for
        # pages still owned by a reader (the indirect-object plumbing
        # is unreliable without a writer's object table).
        attached = writer.add_page(page)
        attached.merge_page(stamp_page)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with output_pdf.open("wb") as fh:
        writer.write(fh)


def _escape(text: str, *, keep_tags: bool = False) -> str:
    if keep_tags:
        # Allow <br/> and similar already-inserted tags.
        safe = text.replace("&", "&amp;")
        return safe
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _draw_wrapped(
    c: "canvas.Canvas", text: str, *, x: float, y: float, width: float, leading: float
) -> None:
    """Very simple word-wrap for cover/separator page copy."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    font = c._fontname
    size = c._fontsize
    words = text.split()
    line = ""
    cy = y
    for word in words:
        candidate = f"{line} {word}".strip()
        if stringWidth(candidate, font, size) <= width:
            line = candidate
        else:
            c.drawString(x, cy, line)
            cy -= leading
            line = word
    if line:
        c.drawString(x, cy, line)
