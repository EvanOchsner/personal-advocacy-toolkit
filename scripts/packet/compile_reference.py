"""Compile a counterparty's governing documents into a single reference PDF.

Given a list of source files (PDFs, docx, text), produce a single PDF
consisting of:

  1. A cover page labeling this as a compiled reference (not the
     official document) and naming the counterparty.
  2. The concatenated source documents, each preceded by a small
     section-header page naming the source file.
  3. A watermark on every body page reading e.g. "COMPILED REFERENCE"
     or "DISPUTED PROVENANCE" or a caller-specified string. This is
     the same watermark facility used in the `lucy-repair-fight`
     original but unanchored from any particular insurer or case.

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
            # Stamp the converted body with the watermark so it carries
            # through every page regardless of source format.
            stamped = work / f"{i:02d}-stamped-{converted.stem}.pdf"
            stamp_watermark(converted, stamped, watermark)
            body_pdfs.append(stamped)

        merge_pdfs(body_pdfs, output)

    return output


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--title", required=True)
    p.add_argument("--counterparty", required=True)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--note", default=None)
    p.add_argument("--watermark", default=DEFAULT_WATERMARK)
    p.add_argument("sources", nargs="+", type=Path)
    args = p.parse_args(argv)

    out = compile_reference(
        title=args.title,
        counterparty=args.counterparty,
        sources=[s.resolve() for s in args.sources],
        output=args.output,
        note=args.note,
        watermark=args.watermark,
    )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
