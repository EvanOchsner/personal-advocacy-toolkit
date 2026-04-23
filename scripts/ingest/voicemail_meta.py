#!/usr/bin/env python3
"""Ingest voicemail / call-log metadata (no audio).

Format-support matrix:

    +------------------------------------------+-----------+
    | Format                                   | Status    |
    +------------------------------------------+-----------+
    | Generic CSV (phone_logs.csv)             | PROTOTYPE |
    | iOS call-history CallHistory.storedata   | STUB      |
    | Android call-log XML (SMS Backup&Restore)| STUB      |
    +------------------------------------------+-----------+

Scope: **metadata only** — number, timestamp, direction, duration,
optional voicemail-transcript text. No audio is captured. Jurisdictional
call-recording rules vary (one-party vs two-party consent); this tool
deliberately does not touch audio files.

Canonical per-call record:

    {
      "source_file": "<path>",
      "source_sha256": "<hex>",
      "source_id": "<hex[:16]>",
      "index": <int>,
      "caller_number": "<str>",
      "contact_name": "<str or null>",
      "direction": "incoming"|"outgoing"|"missed"|"voicemail",
      "timestamp_iso": "<UTC ISO-8601>",
      "duration_seconds": <int or null>,
      "transcript": "<str or null>",    # voicemail transcription if present
      "parsed_at": "<UTC ISO-8601>"
    }

CSV prototype accepts these columns (header row required, case-insensitive,
extras ignored):

    number, name, direction, timestamp, duration_seconds, transcript

`timestamp` accepts either ISO-8601 or millisecond-epoch.
`direction` accepts: incoming, outgoing, missed, voicemail (case-insensitive).

Usage:
    uv run python -m scripts.ingest.voicemail_meta call_log.csv \
        --out-dir data/voicemail/ \
        [--manifest data/voicemail/manifest.yaml] \
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


_VALID_DIRECTIONS = {"incoming", "outgoing", "missed", "voicemail"}


def _parse_timestamp(value: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    # ms-epoch
    if value.isdigit():
        ms = int(value)
        # Heuristic: 13-digit ms epoch, 10-digit sec epoch
        if len(value) >= 13:
            ts = ms / 1000
        else:
            ts = float(ms)
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    # ISO-8601
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_int(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_csv(csv_bytes: bytes) -> list[dict[str, Any]]:
    """Parse the generic call-log CSV. Returns a list of canonical dicts."""
    text = csv_bytes.decode("utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    out: list[dict[str, Any]] = []
    for row in reader:
        # Normalize keys to lowercase so headers like "Number" / "number" both work.
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        direction = norm.get("direction", "").lower()
        if direction and direction not in _VALID_DIRECTIONS:
            # Preserve oddities but flag them — don't drop silently.
            direction = f"unknown:{direction}"
        out.append(
            {
                "caller_number": norm.get("number") or None,
                "contact_name": norm.get("name") or None,
                "direction": direction or None,
                "timestamp_iso": _parse_timestamp(norm.get("timestamp", "")),
                "duration_seconds": _parse_int(norm.get("duration_seconds", "")),
                "transcript": norm.get("transcript") or None,
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Stubs for future formats
# --------------------------------------------------------------------------- #


def parse_ios_storedata(_path: Path) -> list[dict[str, Any]]:
    """STUB: iOS CallHistory.storedata (SQLite Core Data store)."""
    raise NotImplementedError("iOS CallHistory.storedata parser is a stub")


def parse_android_calllog_xml(_bytes: bytes) -> list[dict[str, Any]]:
    """STUB: Android SMS Backup & Restore 'calls.xml' format."""
    raise NotImplementedError("Android call-log XML parser is a stub")


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #


_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(text: str, max_len: int = 30) -> str:
    return (_SAFE.sub("-", text).strip("-") or "call")[:max_len]


def _render_txt(rec: dict[str, Any]) -> str:
    lines = [
        f"Timestamp: {rec.get('timestamp_iso') or ''}",
        f"Number:    {rec.get('caller_number') or ''}",
    ]
    if rec.get("contact_name"):
        lines.append(f"Contact:   {rec['contact_name']}")
    lines.append(f"Direction: {rec.get('direction') or ''}")
    if rec.get("duration_seconds") is not None:
        lines.append(f"Duration:  {rec['duration_seconds']}s")
    if rec.get("transcript"):
        lines.append("")
        lines.append("Transcript:")
        lines.append(rec["transcript"])
    return "\n".join(lines) + "\n"


def write_three_layers(
    raw_bytes: bytes,
    records: list[dict[str, Any]],
    source_path: Path,
    out_dir: Path,
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
        stem = f"{i:04d}_{_slug(rec.get('caller_number') or 'call')}"
        (struct_dir / f"{stem}.json").write_text(
            json.dumps(canonical, indent=2, ensure_ascii=False)
        )
        (human_dir / f"{stem}.txt").write_text(_render_txt(canonical))

    return {
        "source_id": source_id,
        "source_path": str(source_path),
        "source_sha256": source_sha,
        "raw_path": str(raw_out),
        "structured_dir": str(struct_dir),
        "human_dir": str(human_dir),
        "record_count": len(records),
        "parsed_at": parsed_at,
        "format": "generic-call-log-csv",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("csv_file", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    if not args.csv_file.exists():
        print(f"no such file: {args.csv_file}", file=sys.stderr)
        return 2

    raw = args.csv_file.read_bytes()
    records = parse_csv(raw)
    summary = write_three_layers(raw, records, args.csv_file, args.out_dir)

    if args.manifest is not None:
        try:
            append_entry(
                args.manifest, {"kind": "voicemail_meta", **summary}, force=args.force
            )
        except FileExistsError as e:
            print(str(e), file=sys.stderr)
            return 3

    print(f"{args.csv_file} -> {summary['record_count']} call records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
