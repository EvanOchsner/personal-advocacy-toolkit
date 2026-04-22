"""Generate a cover page for a governing-documents appendix.

A "governing-documents appendix" collects any counterparty-authored
document the authority may need to consult: a policy form, a contract,
a terms-of-service, an employee handbook, a homeowner-association
bylaws excerpt, and so on.

The cover page makes three things explicit, every time:

  1. This appendix is a **compiled reference**, not the officially
     filed / authoritative document.
  2. The source files came from the counterparty during the dispute
     (or were retrieved from their public-facing site).
  3. Every page in the body of the appendix carries a SYNTHETIC or
     DISPUTED-PROVENANCE watermark when applicable.

Usable either as a library (import `build_appendix_cover`) or as a
CLI:

    python -m scripts.packet.appendix_cover \\
        --title "Counterparty Policy Reference" \\
        --counterparty "Acme Widgets, Inc." \\
        --output out/cover.pdf \\
        --note "Compiled from documents produced on 2026-01-05."
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ._pdfutil import render_cover_page

DEFAULT_DISCLAIMER = (
    "This appendix is a compiled reference assembled from documents "
    "produced by the counterparty (or retrieved from their public "
    "filings / website) during the course of this dispute. It is NOT "
    "the official, authoritatively-filed version of any governing "
    "document. Any reviewer who needs the official version should "
    "request it directly from the counterparty or the relevant "
    "filing authority."
)


def build_appendix_cover(
    *,
    output: Path,
    title: str,
    counterparty: str,
    note: str | None = None,
    watermark: str | None = "COMPILED REFERENCE",
) -> Path:
    """Write a cover-page PDF for a governing-documents appendix."""
    lines = [f"Counterparty: {counterparty}"]
    if note:
        lines.append("")
        lines.append(note)
    footer = DEFAULT_DISCLAIMER
    render_cover_page(
        output,
        heading=title,
        subheading="Governing-Documents Appendix",
        lines=lines,
        footer=footer,
        watermark=watermark,
    )
    return output


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--title", required=True)
    p.add_argument("--counterparty", required=True)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--note", default=None)
    p.add_argument("--watermark", default="COMPILED REFERENCE")
    args = p.parse_args(argv)
    build_appendix_cover(
        output=args.output,
        title=args.title,
        counterparty=args.counterparty,
        note=args.note,
        watermark=args.watermark or None,
    )
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
