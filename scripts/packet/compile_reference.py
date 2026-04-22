"""Compile a counterparty's governing documents into a single reference artifact.

Given a list of source files (PDFs, docx, text), produce either:

  * A single compiled-reference PDF, with:
      1. A cover page labeling this as a compiled reference (not the
         official document) and naming the counterparty.
      2. The concatenated source documents, each preceded by a small
         section-header page naming the source file.
      3. A watermark on every body page reading e.g. "COMPILED REFERENCE"
         or a caller-specified string.
    If an input PDF has no extractable text layer and `ocrmypdf` is on
    PATH, it is run through OCR first so the compiled reference is
    searchable. Missing `ocrmypdf` is a warning, not a hard failure.

  * A single Markdown file (``--markdown``) with the same content
    flattened to plaintext and a ``> SYNTHETIC — COMPILED REFERENCE``
    banner at the top. This is useful for diffing and for plaintext
    review where a PDF is overkill.

Library entry point: `compile_reference(...)`.

CLI:

    python -m scripts.packet.compile_reference \\
        --title "Acme Terms Reference" \\
        --counterparty "Acme Widgets, Inc." \\
        --output out/acme-terms-reference.pdf \\
        evidence/acme-terms.pdf evidence/acme-return-policy.txt
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ._convert import to_pdf
from ._pdfutil import (
    merge_pdfs,
    render_cover_page,
    stamp_watermark,
)
from .appendix_cover import build_appendix_cover


DEFAULT_WATERMARK = "COMPILED REFERENCE"
MARKDOWN_BANNER = "> SYNTHETIC — COMPILED REFERENCE"


def _pdf_has_text_layer(pdf: Path) -> bool:
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


def _ocr_pdf(src: Path, workdir: Path) -> Path:
    """Run `ocrmypdf` on `src`; return the OCR'd path, or `src` on skip.

    If `ocrmypdf` is not on PATH, emits a stderr warning and returns the
    original PDF unchanged. Never raises for a missing binary — OCR is a
    nice-to-have, not a build prerequisite.
    """
    if _pdf_has_text_layer(src):
        return src
    ocrmypdf = shutil.which("ocrmypdf")
    if not ocrmypdf:
        print(
            f"warning: {src.name} appears to be an image-only PDF and "
            "ocrmypdf is not on PATH; skipping OCR.",
            file=sys.stderr,
        )
        return src
    out = workdir / f"ocr-{src.stem}.pdf"
    result = subprocess.run(
        [ocrmypdf, "--skip-text", str(src), str(out)],
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
        return src
    return out


def compile_reference(
    *,
    title: str,
    counterparty: str,
    sources: list[Path],
    output: Path,
    note: str | None = None,
    watermark: str = DEFAULT_WATERMARK,
) -> Path:
    """Compile `sources` into a watermarked single PDF at `output`."""
    if not sources:
        raise ValueError("compile_reference requires at least one source file.")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        cover = work / "00-cover.pdf"
        build_appendix_cover(
            output=cover,
            title=title,
            counterparty=counterparty,
            note=note,
            watermark=watermark,
        )

        body_pdfs: list[Path] = [cover]
        for i, src in enumerate(sources, start=1):
            section_cover = work / f"{i:02d}-section-cover.pdf"
            render_cover_page(
                section_cover,
                heading=f"Source {i}",
                subheading=src.name,
                lines=[],
                footer=None,
                watermark=watermark,
            )
            body_pdfs.append(section_cover)
            converted = to_pdf(src, work, title=src.name)
            if converted.suffix.lower() == ".pdf":
                converted = _ocr_pdf(converted, work)
            # Stamp the converted body with the watermark so it carries
            # through every page regardless of source format.
            stamped = work / f"{i:02d}-stamped-{converted.stem}.pdf"
            stamp_watermark(converted, stamped, watermark)
            body_pdfs.append(stamped)

        merge_pdfs(body_pdfs, output)

    return output


def compile_reference_markdown(
    *,
    title: str,
    counterparty: str,
    sources: list[Path],
    output: Path,
    note: str | None = None,
) -> Path:
    """Flatten `sources` into a single Markdown file at `output`.

    PDFs are text-extracted (OCR'd first if image-only and `ocrmypdf` is
    available); .docx is converted to PDF then extracted; .txt/.md is
    inlined. Unsupported inputs are linked by name with a
    "[binary source — see PDF build]" note instead of being omitted.
    """
    if not sources:
        raise ValueError("compile_reference_markdown requires at least one source file.")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append(MARKDOWN_BANNER)
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"**Counterparty:** {counterparty}")
    if note:
        lines.append("")
        lines.append(f"*{note}*")
    lines.append("")

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        for i, src in enumerate(sources, start=1):
            lines.append("---")
            lines.append("")
            lines.append(f"## Source {i}: {src.name}")
            lines.append("")
            body = _extract_text(src, work)
            if body is None:
                lines.append(
                    f"*[binary source — could not extract text; see compiled PDF for {src.name}]*"
                )
            else:
                lines.append(body.rstrip())
            lines.append("")

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def _extract_text(src: Path, workdir: Path) -> str | None:
    suffix = src.suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        try:
            return src.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
    try:
        pdf = to_pdf(src, workdir, title=src.name)
    except Exception:
        return None
    pdf = _ocr_pdf(pdf, workdir) if suffix == ".pdf" else pdf
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return None
    try:
        reader = PdfReader(str(pdf))
    except Exception:
        return None
    chunks: list[str] = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        if t.strip():
            chunks.append(t.strip())
    return "\n\n".join(chunks) if chunks else None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--title", required=True)
    p.add_argument("--counterparty", required=True)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--note", default=None)
    p.add_argument("--watermark", default=DEFAULT_WATERMARK)
    p.add_argument(
        "--markdown",
        action="store_true",
        help="Emit a plaintext Markdown file instead of a watermarked PDF.",
    )
    p.add_argument("sources", nargs="+", type=Path)
    args = p.parse_args(argv)

    sources = [s.resolve() for s in args.sources]
    if args.markdown:
        out = compile_reference_markdown(
            title=args.title,
            counterparty=args.counterparty,
            sources=sources,
            output=args.output,
            note=args.note,
        )
    else:
        out = compile_reference(
            title=args.title,
            counterparty=args.counterparty,
            sources=sources,
            output=args.output,
            note=args.note,
            watermark=args.watermark,
        )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
