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
from ._hash import sha256_file
from ._pdfutil import (
    merge_pdfs,
    render_cover_page,
    stamp_watermark,
)
from .appendix_cover import build_appendix_cover


DEFAULT_WATERMARK = "COMPILED REFERENCE"
MARKDOWN_BANNER = "> SYNTHETIC — COMPILED REFERENCE"

# Deterministic default for PDF creationDate/modDate. Callers can
# override via `--compiled-date` (CLI) or `compiled_date=` (library).
# Epoch is used so re-runs without an override produce byte-identical
# PDFs. Real compilations should pass the real date.
DETERMINISTIC_DEFAULT_DATE = "1970-01-01T00:00:00Z"

# Threshold below which a per-source markdown extraction is considered
# suspicious — matches the OCR-fallback heuristic from the source
# project's compile_policy.py. Sources below this in chars-per-page
# usually indicate a failed text-layer extraction.
FIDELITY_CHARS_PER_PAGE_FLOOR = 200


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
    compiled_date: str = DETERMINISTIC_DEFAULT_DATE,
) -> Path:
    """Compile `sources` into a watermarked single PDF at `output`.

    The output's `/Info` dictionary (creationDate, modDate, producer,
    title) and trailer `/ID` are pinned to deterministic values so two
    runs with the same inputs produce byte-identical PDFs. Pass
    `compiled_date` to set a real compilation date instead of the
    epoch default.
    """
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
            stamped = work / f"{i:02d}-stamped-{converted.stem}.pdf"
            stamp_watermark(converted, stamped, watermark)
            body_pdfs.append(stamped)

        merge_pdfs(body_pdfs, output)

    expected_pages = _count_pages(body_pdfs)
    _pin_pdf_metadata(
        output,
        title=title,
        counterparty=counterparty,
        compiled_date=compiled_date,
    )
    _verify_page_count(output, expected_pages)
    return output


def compile_reference_markdown(
    *,
    title: str,
    counterparty: str,
    sources: list[Path],
    output: Path,
    note: str | None = None,
    compiled_date: str = DETERMINISTIC_DEFAULT_DATE,
) -> Path:
    """Flatten `sources` into a single Markdown file at `output`.

    Output shape (mirrors the source project's compile_policy.py
    defensive layering):

      1. Top disclaimer block with counterparty, compilation date, and
         a SHA-256 table of every source.
      2. Per-section header + blockquote callout + source provenance
         line (path, SHA-256, extracted chars) + extracted body.
      3. Bottom disclaimer block reprising the top + source SHA-256
         list, so a reader who started partway through can't miss that
         this is a compiled reference.

    A chars-per-page fidelity report is printed to stderr listing any
    source whose extracted body falls below FIDELITY_CHARS_PER_PAGE_FLOOR
    — a silent-extraction-failure guardrail.

    PDFs are text-extracted (OCR'd first if image-only and `ocrmypdf`
    is on PATH); .docx is converted to PDF then extracted; .txt/.md is
    inlined. Binary sources that can't be extracted emit a
    "[binary source …]" placeholder rather than silently dropping.
    """
    if not sources:
        raise ValueError("compile_reference_markdown requires at least one source file.")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    # Hash every source up front so the disclaimers list them.
    source_hashes: dict[int, str] = {i: sha256_file(s) for i, s in enumerate(sources, 1)}
    # Extract every source up front so we can print a fidelity report
    # before writing the file.
    extracted: dict[int, tuple[str | None, int]] = {}
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        for i, src in enumerate(sources, 1):
            body = _extract_text(src, work)
            # Best-effort page count for fidelity reporting. Plain-text
            # sources are treated as "1 page" for the chars/page metric.
            page_count = _estimate_page_count(src, work)
            extracted[i] = (body, page_count)

    _print_fidelity_report(sources, extracted)

    lines: list[str] = []
    lines.extend(
        _render_top_disclaimer(title, counterparty, sources, source_hashes, compiled_date, note)
    )
    for i, src in enumerate(sources, 1):
        body, page_count = extracted[i]
        lines.append("---")
        lines.append("")
        lines.append(f"## Source {i}: {src.name}")
        lines.append("")
        lines.extend(_render_section_callout(counterparty))
        lines.append("")
        lines.append(f"**Source file:** `{src}`  ")
        lines.append(f"**SHA-256:** `{source_hashes[i]}`  ")
        lines.append(f"**Page count:** {page_count}")
        lines.append("")
        if body is None:
            lines.append(
                f"*[binary source — could not extract text; see compiled PDF for {src.name}]*"
            )
        else:
            lines.append("```text")
            lines.append(body.rstrip())
            lines.append("```")
        lines.append("")

    lines.extend(_render_bottom_disclaimer(sources, source_hashes))

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


# -----------------------------------------------------------------------------
# Markdown templates
# -----------------------------------------------------------------------------


def _render_top_disclaimer(
    title: str,
    counterparty: str,
    sources: list[Path],
    source_hashes: dict[int, str],
    compiled_date: str,
    note: str | None,
) -> list[str]:
    out: list[str] = []
    out.append(f"# ⚠️ COMPILED REFERENCE — NOT A {counterparty.upper()} DOCUMENT ⚠️")
    out.append("")
    out.append(
        f"> **This file is a locally-assembled compilation of documents from "
        f"{counterparty}.** It is NOT an authentic {counterparty}-issued document. "
        f"It was produced by concatenating separate source files (listed below "
        f"with SHA-256 hashes) for the purpose of reading and searching."
    )
    out.append(">")
    out.append(
        f"> **DO NOT CITE THIS COMPILATION** as the official {counterparty} "
        "document in any complaint, correspondence, discovery production, or "
        "court filing. Cite the underlying individual evidence files listed "
        "below. This compilation has no independent evidentiary standing."
    )
    out.append("")
    out.append(f"## {title}")
    out.append("")
    out.append(f"- **Counterparty:** {counterparty}")
    out.append(f"- **Compiled:** {compiled_date}")
    out.append("- **Compiled via:** `scripts/packet/compile_reference.py`")
    if note:
        out.append(f"- **Note:** {note}")
    out.append("")
    out.append("### Sources (in order of appearance after this disclaimer)")
    out.append("")
    for i, src in enumerate(sources, 1):
        out.append(f"- **§ {i}** `{src}`")
        out.append(f"  - SHA-256: `{source_hashes[i]}`")
    out.append("")
    return out


def _render_section_callout(counterparty: str) -> list[str]:
    return [
        f"> ⚠️ **COMPILED REFERENCE — NOT A {counterparty.upper()} DOCUMENT**",
        ">",
        f"> This section is extracted from a source PDF and inserted into a "
        f"locally-assembled compilation. Do not cite this rendering — cite "
        f"the source file listed above.",
    ]


def _render_bottom_disclaimer(
    sources: list[Path], source_hashes: dict[int, str]
) -> list[str]:
    out: list[str] = []
    out.append("---")
    out.append("")
    out.append("## ⚠️ COMPILED REFERENCE — NOT AN ORIGINAL DOCUMENT ⚠️")
    out.append("")
    out.append(
        "> Reminder: the file you just finished reading is a "
        "**locally-assembled compilation**, not an authentic "
        "counterparty-issued document. Do not cite it in any complaint, "
        "correspondence, discovery production, or court filing. Cite the "
        "underlying individual source files instead."
    )
    out.append("")
    out.append("### Source file SHA-256 hashes (final)")
    out.append("")
    for i, src in enumerate(sources, 1):
        out.append(f"- § {i} `{src}`")
        out.append(f"  - SHA-256: `{source_hashes[i]}`")
    out.append("")
    return out


# -----------------------------------------------------------------------------
# Fidelity / page count helpers
# -----------------------------------------------------------------------------


def _estimate_page_count(src: Path, work: Path) -> int:
    suffix = src.suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        return 1
    try:
        pdf = to_pdf(src, work, title=src.name)
    except Exception:
        return 0
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return 0
    try:
        reader = PdfReader(str(pdf))
    except Exception:
        return 0
    return len(reader.pages)


def _print_fidelity_report(
    sources: list[Path],
    extracted: dict[int, tuple[str | None, int]],
) -> None:
    """Write a chars-per-page report to stderr; flag thin extractions."""
    print("compile_reference: markdown fidelity (chars/page):", file=sys.stderr)
    any_thin = False
    for i, src in enumerate(sources, 1):
        body, page_count = extracted[i]
        chars = len(body or "")
        per_page = chars / page_count if page_count else 0.0
        thin = per_page < FIDELITY_CHARS_PER_PAGE_FLOOR
        marker = "  WARN" if thin else "      "
        print(
            f"  § {i} {marker}  pages={page_count:3d}  chars={chars:7d}  "
            f"chars/page={per_page:8.1f}  {src.name}",
            file=sys.stderr,
        )
        if thin:
            any_thin = True
    if any_thin:
        print(
            f"  (sources below {FIDELITY_CHARS_PER_PAGE_FLOOR} chars/page "
            "likely failed text extraction; check source PDFs.)",
            file=sys.stderr,
        )


# -----------------------------------------------------------------------------
# PDF determinism + verification
# -----------------------------------------------------------------------------


def _count_pages(pdfs: list[Path]) -> int:
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return 0
    total = 0
    for p in pdfs:
        try:
            total += len(PdfReader(str(p)).pages)
        except Exception:
            continue
    return total


def _verify_page_count(output: Path, expected: int) -> None:
    """Re-read the written PDF and assert the page count matches."""
    if expected == 0:
        return
    from pypdf import PdfReader

    try:
        got = len(PdfReader(str(output)).pages)
    except Exception as exc:
        raise RuntimeError(f"could not reopen {output} to verify page count: {exc}") from exc
    if got != expected:
        raise RuntimeError(
            f"PDF page count mismatch for {output}: "
            f"in-memory={expected} on-disk={got}"
        )


def _pin_pdf_metadata(
    output: Path,
    *,
    title: str,
    counterparty: str,
    compiled_date: str,
) -> None:
    """Pin `/Info` + `/ID` with pikepdf so two runs produce byte-identical output."""
    import pikepdf

    # Parse `compiled_date` into a pikepdf-friendly PDF date string.
    # Accepts ISO-8601; falls back to D:19700101000000Z on parse failure.
    pdf_date = _iso_to_pdf_date(compiled_date)

    with pikepdf.Pdf.open(output, allow_overwriting_input=True) as pdf:
        pdf.docinfo["/Title"] = f"COMPILED REFERENCE — {title}"
        pdf.docinfo["/Author"] = "advocacy-toolkit/scripts/packet/compile_reference.py"
        pdf.docinfo["/Subject"] = (
            f"Locally compiled reference of {counterparty} documents — "
            "not an authentic counterparty document"
        )
        pdf.docinfo["/Keywords"] = "compiled, reference, not-original, work-product"
        pdf.docinfo["/Creator"] = "advocacy-toolkit/compile_reference"
        pdf.docinfo["/Producer"] = "advocacy-toolkit/compile_reference (pikepdf)"
        pdf.docinfo["/CreationDate"] = pdf_date
        pdf.docinfo["/ModDate"] = pdf_date
        # Pin the /ID array so re-runs produce byte-identical trailers.
        id_bytes = _fixed_id_bytes(title, counterparty, compiled_date)
        pdf.trailer["/ID"] = pikepdf.Array([id_bytes, id_bytes])
        pdf.save(
            output,
            deterministic_id=True,
            compress_streams=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
        )


def _iso_to_pdf_date(iso: str) -> str:
    """Convert `YYYY-MM-DDTHH:MM:SSZ` to `D:YYYYMMDDHHMMSSZ`."""
    try:
        # Drop trailing Z if present; we always emit UTC.
        s = iso.rstrip("Z")
        # Split date/time.
        date_part, _, time_part = s.partition("T")
        y, m, d = date_part.split("-")
        hh, mm, ss = (time_part or "00:00:00").split(":")
        return f"D:{y}{m}{d}{hh}{mm}{ss}Z"
    except (ValueError, AttributeError):
        return "D:19700101000000Z"


def _fixed_id_bytes(title: str, counterparty: str, compiled_date: str) -> bytes:
    """Derive a stable 16-byte /ID from the compilation inputs."""
    import hashlib as _h

    key = f"{title}|{counterparty}|{compiled_date}".encode()
    return _h.sha256(key).digest()[:16]


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
    p.add_argument(
        "--compiled-date",
        default=DETERMINISTIC_DEFAULT_DATE,
        help="ISO-8601 compilation date stamped into disclaimers and PDF metadata. "
        "Defaults to the epoch for deterministic output; pass today's date "
        "(e.g. 2026-04-22T00:00:00Z) for a real compilation.",
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
            compiled_date=args.compiled_date,
        )
    else:
        out = compile_reference(
            title=args.title,
            counterparty=args.counterparty,
            sources=sources,
            output=args.output,
            note=args.note,
            watermark=args.watermark,
            compiled_date=args.compiled_date,
        )
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
