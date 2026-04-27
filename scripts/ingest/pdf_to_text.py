#!/usr/bin/env python3
"""Ingest a PDF into the project's three-layer evidence shape.

Pipeline:
  raw/<source_id>.pdf            # byte-identical copy of the input
  structured/<source_id>.json    # provenance + extraction metadata
  human/<source_id>.txt          # plaintext transcript

If the input PDF lacks a text layer and `ocrmypdf` is on PATH, OCR is
applied first so the resulting transcript is searchable. Missing
`ocrmypdf` is a stderr warning, not an error — the structured JSON
records `ocr_applied: false` and `text_chars: 0` so a reviewer can spot
the gap and re-run after installing the binary.

Canonical structured record:

    {
      "source_file": "<original input path>",
      "source_sha256": "<hex>",
      "source_id": "<hex[:16]>",
      "page_count": <int>,
      "ocr_applied": <bool>,
      "ocr_engine": "<ocrmypdf version string or null>",
      "text_chars": <int>,
      "raw_path": "<copy under out_dir/raw/>",
      "plaintext_path": "<.txt under out_dir/human/>",
      "parsed_at": "<UTC ISO-8601>",
      "notes": [<warning strings>]
    }

Usage:
    uv run python -m scripts.ingest.pdf_to_text input.pdf [more.pdf ...] \\
        --out-dir evidence/pdfs/ \\
        [--manifest evidence/pdfs/manifest.yaml] \\
        [--force]

Inputs may also be directories; every `.pdf` found (non-recursive) is
processed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.ingest._manifest import append_entry
from scripts.ingest._pdf import (
    extract_text,
    ocr_pdf,
    ocrmypdf_version,
    page_count,
    pdf_has_text_layer,
)


def _expand_inputs(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            out.extend(sorted(q for q in p.iterdir() if q.suffix.lower() == ".pdf"))
        else:
            out.append(p)
    return out


def ingest_pdf(src: Path, out_dir: Path) -> dict[str, Any]:
    """Process a single PDF and return its structured summary record."""
    raw_bytes = src.read_bytes()
    source_sha = hashlib.sha256(raw_bytes).hexdigest()
    source_id = source_sha[:16]

    raw_dir = out_dir / "raw"
    struct_dir = out_dir / "structured"
    human_dir = out_dir / "human"
    for d in (raw_dir, struct_dir, human_dir):
        d.mkdir(parents=True, exist_ok=True)

    raw_out = raw_dir / f"{source_id}.pdf"
    raw_out.write_bytes(raw_bytes)

    notes: list[str] = []
    ocr_applied = False
    ocr_engine: str | None = None

    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        if pdf_has_text_layer(raw_out):
            working_pdf = raw_out
        else:
            working_pdf, ocr_applied = ocr_pdf(raw_out, workdir)
            if ocr_applied:
                ocr_engine = ocrmypdf_version()
            else:
                notes.append(
                    "image-only PDF; ocrmypdf unavailable or failed — "
                    "extracted text will be empty"
                )
        text = extract_text(working_pdf)
        pages = page_count(working_pdf)

    plaintext_path = human_dir / f"{source_id}.txt"
    plaintext_path.write_text(text, encoding="utf-8")

    parsed_at = datetime.now(timezone.utc).isoformat()

    record: dict[str, Any] = {
        "source_file": str(src),
        "source_sha256": source_sha,
        "source_id": source_id,
        "page_count": pages,
        "ocr_applied": ocr_applied,
        "ocr_engine": ocr_engine,
        "text_chars": len(text),
        "raw_path": str(raw_out),
        "plaintext_path": str(plaintext_path),
        "parsed_at": parsed_at,
        "notes": notes,
    }

    (struct_dir / f"{source_id}.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False)
    )
    return record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing manifest entry with the same source_id.",
    )
    args = ap.parse_args(argv)

    pdfs = _expand_inputs(args.inputs)
    if not pdfs:
        print("no PDF inputs found", file=sys.stderr)
        return 2

    rc = 0
    for pdf in pdfs:
        if not pdf.is_file():
            print(f"skip: {pdf} (not a file)", file=sys.stderr)
            rc = 1
            continue
        record = ingest_pdf(pdf, args.out_dir)
        if args.manifest is not None:
            try:
                append_entry(
                    args.manifest, {"kind": "pdf_to_text", **record}, force=args.force
                )
            except FileExistsError as e:
                print(str(e), file=sys.stderr)
                rc = 3
                continue
        ocr_note = " (OCR'd)" if record["ocr_applied"] else ""
        print(
            f"{pdf} -> {record['source_id']}: "
            f"{record['page_count']} pages, "
            f"{record['text_chars']} chars{ocr_note}"
        )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
