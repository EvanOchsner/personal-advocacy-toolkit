"""Build a complaint packet from a packet-manifest.yaml.

This is the replacement for the original hardcoded packet builder.
Everything the builder needs — authority name, complaint document,
exhibit list + labels + descriptions, reference appendices, output
directory — is declared in the manifest. The builder has no
authority-, case-, or jurisdiction-specific code.

High-level assembly:

  1. Parse manifest (see `templates/packet-manifests/schema.yaml`).
  2. Emit a packet cover page naming the authority, the complainant,
     and the respondent.
  3. Convert the complaint document to PDF if necessary.
  4. For each exhibit in order: emit a labeled separator page, then
     the (converted) exhibit body.
  5. For each reference appendix: emit via `compile_reference.py`.
  6. Merge into a single "packet.pdf" and write each exhibit as a
     standalone labeled PDF alongside for filers who want to upload
     individually.

Usage:

    python -m scripts.packet.build path/to/packet-manifest.yaml
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from ._convert import to_pdf
from ._manifest import (
    Exhibit,
    PacketManifest,
    ReferenceAppendix,
    load_manifest,
)
from ._pdfutil import (
    merge_pdfs,
    render_cover_page,
    render_separator_page,
)
from .compile_reference import compile_reference


def build_packet(manifest: PacketManifest, *, verbose: bool = False) -> dict[str, Path]:
    """Assemble the packet described by `manifest`.

    Returns a dict with keys:
      - 'packet'    : Path to the merged packet PDF
      - 'exhibits'  : list[Path] of standalone exhibit PDFs
      - 'appendices': list[Path] of reference-appendix PDFs
    """
    out_dir = manifest.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        if verbose:
            print(msg)

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)

        cover_pdf = work / "00-cover.pdf"
        _render_packet_cover(cover_pdf, manifest)

        complaint_pdf = _prepare_complaint(manifest, work)
        log(f"complaint -> {complaint_pdf}")

        # Standalone per-exhibit PDFs for filers who upload individually.
        exhibit_outputs: list[Path] = []
        exhibit_workpaths: list[Path] = []
        for ex in manifest.exhibits:
            built = _build_exhibit(ex, work)
            standalone = (
                out_dir / f"exhibit-{ex.label}-{_slug(ex.title)}.pdf"
            )
            merge_pdfs(built, standalone)
            exhibit_outputs.append(standalone)
            exhibit_workpaths.extend(built)
            log(f"exhibit {ex.label} -> {standalone}")

        # Reference appendices via compile_reference.
        appendix_outputs: list[Path] = []
        appendix_workpaths: list[Path] = []
        for ref in manifest.reference_appendices:
            appendix_path = out_dir / f"appendix-{ref.name}.pdf"
            compile_reference(
                title=ref.title,
                counterparty=manifest.respondent.name,
                sources=ref.sources,
                output=appendix_path,
                note=ref.note,
            )
            appendix_outputs.append(appendix_path)
            appendix_workpaths.append(appendix_path)
            log(f"appendix {ref.name} -> {appendix_path}")

        # Final merged packet.
        packet_path = out_dir / f"{manifest.name}-{manifest.authority.short_code.lower()}-packet.pdf"
        merge_pdfs(
            [cover_pdf, complaint_pdf, *exhibit_workpaths, *appendix_workpaths],
            packet_path,
        )
        log(f"packet -> {packet_path}")

    return {
        "packet": packet_path,
        "exhibits": exhibit_outputs,
        "appendices": appendix_outputs,
    }


def _render_packet_cover(output: Path, m: PacketManifest) -> None:
    lines = [
        f"To: {m.authority.name}",
        "",
        f"From: {m.complainant.name}",
    ]
    if m.complainant.mailing_address:
        lines.append(m.complainant.mailing_address)
    if m.complainant.email:
        lines.append(f"Email: {m.complainant.email}")
    if m.complainant.phone:
        lines.append(f"Phone: {m.complainant.phone}")
    lines.append("")
    lines.append(f"Re: Complaint against {m.respondent.name}")
    if m.respondent.reference_number:
        lines.append(f"Reference: {m.respondent.reference_number}")
    if m.authority.mailing_address:
        lines.append("")
        lines.append("Mailing address:")
        lines.append(m.authority.mailing_address)

    render_cover_page(
        output,
        heading="Complaint Packet",
        subheading=m.authority.name,
        lines=lines,
        footer=(
            "Assembled by advocacy-toolkit packet builder. "
            "Exhibit order and labeling are defined in the accompanying "
            "packet manifest."
        ),
    )


def _prepare_complaint(m: PacketManifest, work: Path) -> Path:
    src = m.complaint.source or m.complaint.docx_source
    assert src is not None  # manifest validation ensures this
    return to_pdf(src, work, title=m.complaint.title)


def _build_exhibit(ex: Exhibit, work: Path) -> list[Path]:
    """Return [separator-pdf, body-pdf, ...] for this exhibit."""
    parts: list[Path] = []
    if not ex.no_separator:
        sep = work / f"sep-{ex.label}.pdf"
        render_separator_page(
            sep,
            label=ex.label,
            title=ex.title,
            description=ex.description,
            date=ex.date,
        )
        parts.append(sep)
    for src in ex.all_sources:
        parts.append(to_pdf(src, work, title=ex.title))
    return parts


def _slug(text: str) -> str:
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_":
            out.append("-")
    s = "".join(out)
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-") or "untitled"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("manifest", type=Path, help="Path to packet-manifest.yaml")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    manifest = load_manifest(args.manifest)
    result = build_packet(manifest, verbose=args.verbose)
    print(f"Packet: {result['packet']}")
    for ex in result["exhibits"]:
        print(f"  exhibit: {ex}")
    for ap in result["appendices"]:
        print(f"  appendix: {ap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
