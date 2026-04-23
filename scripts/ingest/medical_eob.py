#!/usr/bin/env python3
"""Ingest medical EOB (Explanation of Benefits) / billing artifacts.

Format-support matrix:

    +-----------------------------------------+-----------+
    | Format                                  | Status    |
    +-----------------------------------------+-----------+
    | Generic EOB CSV (columns listed below)  | PROTOTYPE |
    | Anthem-style EOB PDF (pdfplumber)       | STUB      |
    | UnitedHealthcare EOB PDF                | STUB      |
    | Kaiser member-portal EOB PDF            | STUB      |
    | HL7 835 ERA                             | STUB      |
    +-----------------------------------------+-----------+

The CSV is picked as the prototype because EOB PDFs vary wildly per
insurer and per year, and the value of this ingester is the canonical
shape it produces — not PDF wrangling. Users who have EOB PDFs can
(a) OCR/transcribe into the CSV shape, or (b) write an insurer-specific
PDF extractor that emits the same CSV schema.

PDF parsing is a stub because `pdfplumber` is not in pyproject.toml; we
don't silently require un-declared deps. Adding it would be a one-line
change if this tool's scope expanded.

Accepted CSV columns (header row required, case-insensitive):

    date_of_service, provider, cpt_code, description,
    billed, allowed, patient_responsibility

Extra columns are preserved under `extra` on each record.

Canonical per-line-item record:

    {
      "source_file": "<path>",
      "source_sha256": "<hex>",
      "source_id": "<hex[:16]>",
      "index": <int>,
      "date_of_service": "<YYYY-MM-DD or raw>",
      "provider": "<str>",
      "cpt_code": "<str>",
      "description": "<str>",
      "billed": <float or null>,
      "allowed": <float or null>,
      "patient_responsibility": <float or null>,
      "extra": { ...unrecognized columns... },
      "parsed_at": "<UTC ISO-8601>"
    }

Usage:
    uv run python -m scripts.ingest.medical_eob eob.csv \
        --out-dir data/medical/ \
        [--manifest data/medical/manifest.yaml] \
        [--force]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.ingest._manifest import append_entry


KNOWN_COLUMNS = {
    "date_of_service",
    "provider",
    "cpt_code",
    "description",
    "billed",
    "allowed",
    "patient_responsibility",
}


def _parse_money(value: str) -> float | None:
    value = (value or "").strip().replace("$", "").replace(",", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_date(value: str) -> str:
    """Normalize to YYYY-MM-DD if possible; otherwise return raw."""
    value = (value or "").strip()
    if not value:
        return ""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value


def parse_csv(csv_bytes: bytes) -> list[dict[str, Any]]:
    text = csv_bytes.decode("utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    out: list[dict[str, Any]] = []
    for row in reader:
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        extra = {k: v for k, v in norm.items() if k not in KNOWN_COLUMNS}
        out.append(
            {
                "date_of_service": _parse_date(norm.get("date_of_service", "")),
                "provider": norm.get("provider", ""),
                "cpt_code": norm.get("cpt_code", ""),
                "description": norm.get("description", ""),
                "billed": _parse_money(norm.get("billed", "")),
                "allowed": _parse_money(norm.get("allowed", "")),
                "patient_responsibility": _parse_money(
                    norm.get("patient_responsibility", "")
                ),
                "extra": extra,
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Stubs for PDF formats
# --------------------------------------------------------------------------- #


def parse_anthem_pdf(_path: Path) -> list[dict[str, Any]]:
    """STUB: Anthem EOB PDF. Requires pdfplumber (not in pyproject)."""
    raise NotImplementedError(
        "Anthem EOB PDF parser is a stub. Install pdfplumber and implement, "
        "or transcribe into the generic CSV shape."
    )


def parse_uhc_pdf(_path: Path) -> list[dict[str, Any]]:
    """STUB: UnitedHealthcare EOB PDF."""
    raise NotImplementedError("UHC EOB PDF parser is a stub")


def parse_hl7_835(_path: Path) -> list[dict[str, Any]]:
    """STUB: HL7 835 ERA (electronic remittance advice)."""
    raise NotImplementedError("HL7 835 parser is a stub")


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #


_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(text: str, max_len: int = 40) -> str:
    return (_SAFE.sub("-", text).strip("-") or "line")[:max_len]


def _render_txt(rec: dict[str, Any]) -> str:
    lines = [
        f"Date of Service: {rec.get('date_of_service') or ''}",
        f"Provider:        {rec.get('provider') or ''}",
        f"CPT:             {rec.get('cpt_code') or ''}",
        f"Description:     {rec.get('description') or ''}",
    ]

    def _fmt(x: float | None) -> str:
        return f"${x:,.2f}" if x is not None else ""

    lines.append(f"Billed:          {_fmt(rec.get('billed'))}")
    lines.append(f"Allowed:         {_fmt(rec.get('allowed'))}")
    lines.append(f"Pt. responsible: {_fmt(rec.get('patient_responsibility'))}")
    if rec.get("extra"):
        lines.append("")
        lines.append("Extra columns:")
        for k, v in rec["extra"].items():
            lines.append(f"  {k}: {v}")
    return "\n".join(lines) + "\n"


def write_three_layers(
    raw_bytes: bytes,
    records: list[dict[str, Any]],
    source_path: Path,
    out_dir: Path,
    fmt_label: str,
) -> dict[str, Any]:
    source_sha = hashlib.sha256(raw_bytes).hexdigest()
    source_id = source_sha[:16]

    raw_dir = out_dir / "raw"
    struct_dir = out_dir / "structured" / source_id
    human_dir = out_dir / "human" / source_id
    for d in (raw_dir, struct_dir, human_dir):
        d.mkdir(parents=True, exist_ok=True)

    raw_out = raw_dir / f"{source_id}{source_path.suffix or '.csv'}"
    raw_out.write_bytes(raw_bytes)

    parsed_at = datetime.now(timezone.utc).isoformat()
    for i, rec in enumerate(records):
        canonical = {
            "source_file": str(source_path),
            "source_sha256": source_sha,
            "source_id": source_id,
            "index": i,
            "parsed_at": parsed_at,
            **rec,
        }
        stem = f"{i:04d}_{_slug(rec.get('cpt_code') or rec.get('description') or 'line')}"
        (struct_dir / f"{stem}.json").write_text(
            json.dumps(canonical, indent=2, ensure_ascii=False)
        )
        (human_dir / f"{stem}.txt").write_text(_render_txt(canonical))

    # Simple totals for the manifest entry — useful for dashboard/packet tools.
    totals: dict[str, float] = {"billed": 0.0, "allowed": 0.0, "patient_responsibility": 0.0}
    for r in records:
        for k in totals:
            v = r.get(k)
            if v is not None:
                totals[k] += float(v)

    return {
        "source_id": source_id,
        "source_path": str(source_path),
        "source_sha256": source_sha,
        "raw_path": str(raw_out),
        "structured_dir": str(struct_dir),
        "human_dir": str(human_dir),
        "line_item_count": len(records),
        "totals": {k: round(v, 2) for k, v in totals.items()},
        "parsed_at": parsed_at,
        "format": fmt_label,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("eob_file", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--format",
        choices=["auto", "csv", "anthem-pdf", "uhc-pdf", "hl7-835"],
        default="auto",
    )
    args = ap.parse_args(argv)

    if not args.eob_file.exists():
        print(f"no such file: {args.eob_file}", file=sys.stderr)
        return 2

    raw = args.eob_file.read_bytes()
    fmt = args.format
    if fmt == "auto":
        fmt = "csv" if args.eob_file.suffix.lower() == ".csv" else "unknown"

    if fmt == "csv":
        records = parse_csv(raw)
        fmt_label = "generic-eob-csv"
    elif fmt == "anthem-pdf":
        records = parse_anthem_pdf(args.eob_file)
        fmt_label = "anthem-eob-pdf"
    elif fmt == "uhc-pdf":
        records = parse_uhc_pdf(args.eob_file)
        fmt_label = "uhc-eob-pdf"
    elif fmt == "hl7-835":
        records = parse_hl7_835(args.eob_file)
        fmt_label = "hl7-835"
    else:
        print(
            f"unknown format for {args.eob_file}; pass --format explicitly "
            f"(prototype supports: csv)",
            file=sys.stderr,
        )
        return 2

    summary = write_three_layers(raw, records, args.eob_file, args.out_dir, fmt_label)

    if args.manifest is not None:
        try:
            append_entry(
                args.manifest, {"kind": "medical_eob", **summary}, force=args.force
            )
        except FileExistsError as e:
            print(str(e), file=sys.stderr)
            return 3

    print(
        f"{args.eob_file} -> {summary['line_item_count']} line items, "
        f"totals={summary['totals']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
