#!/usr/bin/env python3
"""Ingest SMS / iMessage exports into the three-layer format.

Format-support matrix (Phase 3 prototype scope):

    +---------------------------------------------+-----------+
    | Format                                      | Status    |
    +---------------------------------------------+-----------+
    | Android "SMS Backup & Restore" XML (<sms>)  | PROTOTYPE |
    | iOS iMessage / sms.db export (chat.db)      | STUB      |
    | iMazing CSV export                          | STUB      |
    | Google Voice Takeout HTML                   | STUB      |
    +---------------------------------------------+-----------+

The Android SMS Backup & Restore XML format is chosen as the prototype
because it's plain-text XML with a stable, documented schema and no
binary dependencies to parse. iOS formats (chat.db SQLite, iMazing CSV)
have the same information shape — address, timestamp (ms-epoch),
direction, body — so stubs mirror the prototype's output contract.

Three-layer output (parallel to the email pipeline):

    raw/<source_id>.xml              # the original export, untouched
    structured/<source_id>/*.json    # one JSON per message, canonical shape
    human/<source_id>/*.txt          # one TXT per message, printable

Canonical JSON schema per message:

    {
      "source_export": "<path of the raw export>",
      "source_export_sha256": "<hex>",
      "source_id": "<short stable id for the export, e.g. sha256[:16]>",
      "message_index": <int>,           # position in the export
      "direction": "incoming"|"outgoing",
      "address": "<E.164 or raw>",
      "contact_name": "<str or null>",
      "date_iso": "<UTC ISO-8601>",
      "date_raw_ms": <int or null>,
      "body": "<str>",
      "service": "SMS"|"MMS"|"iMessage",
      "thread_id": "<str or null>",
      "parsed_at": "<UTC ISO-8601>"
    }

Usage:
    python -m scripts.ingest.sms_export EXPORT.xml \
        --out-dir data/sms/ \
        [--manifest data/sms/manifest.yaml] \
        [--force]

Note on scope: SMS exports are typically multi-message artifacts. This
tool records ONE manifest entry per export file, with per-message counts
and the export-level sha256 as source_id — not one entry per message.
That keeps the manifest human-scale. Per-message JSONs carry a stable
`<source_id>/<index>` path that downstream tools can reference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from scripts.ingest._manifest import append_entry


# --------------------------------------------------------------------------- #
# Android "SMS Backup & Restore" XML — prototype parser
# --------------------------------------------------------------------------- #

# Reference: <sms count="N"><sms protocol="0" address="+15551234567"
#   date="1700000000000" type="1"|"2" body="..." read="1" status="-1"
#   contact_name="Alice" service_center="null" readable_date="..."/></sms>
# type=1 -> received (incoming); type=2 -> sent (outgoing). Dates are
# milliseconds since epoch (UTC).

ANDROID_TYPE_DIRECTION = {"1": "incoming", "2": "outgoing"}


def _iso_from_ms(ms_value: str | None) -> tuple[str | None, int | None]:
    if not ms_value:
        return None, None
    try:
        ms = int(ms_value)
    except (TypeError, ValueError):
        return None, None
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.isoformat(), ms


def parse_android_sms_xml(xml_bytes: bytes) -> list[dict[str, Any]]:
    """Parse Android SMS Backup & Restore XML into a list of canonical dicts.

    Only handles the <sms> element today; <mms> is left as a stub.
    """
    # Defensive: the root wrapper can include an XSL processing instruction
    # and a DOCTYPE-style comment. ET.fromstring handles both.
    root = ET.fromstring(xml_bytes)
    messages: list[dict[str, Any]] = []
    for sms in root.findall("sms"):
        direction = ANDROID_TYPE_DIRECTION.get(sms.get("type", ""), "unknown")
        date_iso, date_ms = _iso_from_ms(sms.get("date"))
        messages.append(
            {
                "direction": direction,
                "address": sms.get("address"),
                "contact_name": sms.get("contact_name") or None,
                "date_iso": date_iso,
                "date_raw_ms": date_ms,
                "body": sms.get("body") or "",
                "service": "SMS",
                "thread_id": sms.get("thread_id"),
            }
        )
    # TODO(stub): iterate over <mms> elements and flatten their
    # <parts><part ct="text/plain" text="..."/></parts> children into
    # the same schema. Out of scope for prototype.
    return messages


# --------------------------------------------------------------------------- #
# Stubs for other formats — documented, non-functional
# --------------------------------------------------------------------------- #


def parse_ios_chat_db(_path: Path) -> list[dict[str, Any]]:
    """STUB: iOS chat.db SQLite export.

    Real implementation would open the SQLite DB, join `message`, `handle`,
    and `chat_message_join` tables, convert Apple's Core Data epoch
    (nanoseconds since 2001-01-01) into UTC ISO-8601, and emit the same
    canonical dict shape as the Android parser.
    """
    raise NotImplementedError("iOS chat.db parsing is a stub (prototype: Android XML)")


def parse_imazing_csv(_path: Path) -> list[dict[str, Any]]:
    """STUB: iMazing CSV export. Same canonical dict shape as above."""
    raise NotImplementedError("iMazing CSV parsing is a stub")


def parse_google_voice_html(_path: Path) -> list[dict[str, Any]]:
    """STUB: Google Voice Takeout HTML export."""
    raise NotImplementedError("Google Voice HTML parsing is a stub")


# --------------------------------------------------------------------------- #
# Three-layer writers
# --------------------------------------------------------------------------- #


_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(text: str, max_len: int = 40) -> str:
    s = _SAFE_CHARS.sub("-", text.strip()).strip("-")
    return (s or "msg")[:max_len]


def _render_txt(rec: dict[str, Any]) -> str:
    lines = [
        f"Date:      {rec.get('date_iso') or ''}",
        f"Direction: {rec.get('direction') or ''}",
        f"Address:   {rec.get('address') or ''}",
    ]
    if rec.get("contact_name"):
        lines.append(f"Contact:   {rec['contact_name']}")
    lines.append(f"Service:   {rec.get('service') or ''}")
    lines.append("")
    lines.append("-" * 60)
    lines.append("")
    lines.append(rec.get("body") or "[no body]")
    return "\n".join(lines).rstrip() + "\n"


def write_three_layers(
    raw_bytes: bytes,
    records: list[dict[str, Any]],
    source_path: Path,
    out_dir: Path,
) -> dict[str, Any]:
    """Write raw / structured / human layers. Returns a summary dict."""
    source_sha = hashlib.sha256(raw_bytes).hexdigest()
    source_id = source_sha[:16]

    raw_dir = out_dir / "raw"
    struct_dir = out_dir / "structured" / source_id
    human_dir = out_dir / "human" / source_id
    for d in (raw_dir, struct_dir, human_dir):
        d.mkdir(parents=True, exist_ok=True)

    raw_out = raw_dir / f"{source_id}{source_path.suffix or '.xml'}"
    raw_out.write_bytes(raw_bytes)

    parsed_at = datetime.now(timezone.utc).isoformat()
    for i, rec in enumerate(records):
        canonical = {
            "source_export": str(source_path),
            "source_export_sha256": source_sha,
            "source_id": source_id,
            "message_index": i,
            "parsed_at": parsed_at,
            **rec,
        }
        stem = f"{i:05d}_{_slug((rec.get('body') or rec.get('address') or 'msg'))}"
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
        "message_count": len(records),
        "parsed_at": parsed_at,
        "format": "android-sms-backup-restore-xml",
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _detect_format(path: Path, raw: bytes) -> str:
    suffix = path.suffix.lower()
    if suffix == ".xml" and b"<smses" in raw[:2048]:
        return "android-xml"
    if suffix in (".db", ".sqlite"):
        return "ios-chatdb"
    if suffix == ".csv":
        return "imazing-csv"
    if suffix in (".html", ".htm"):
        return "google-voice-html"
    # Fallback: if it opens as XML and has <sms>, treat as Android.
    if b"<sms " in raw[:4096] or b"<smses" in raw[:4096]:
        return "android-xml"
    return "unknown"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export", type=Path, help="SMS export file")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing manifest entry with the same source_id.",
    )
    args = ap.parse_args(argv)

    if not args.export.exists():
        print(f"no such file: {args.export}", file=sys.stderr)
        return 2

    raw = args.export.read_bytes()
    fmt = _detect_format(args.export, raw)
    if fmt == "android-xml":
        records = parse_android_sms_xml(raw)
    elif fmt == "ios-chatdb":
        records = parse_ios_chat_db(args.export)
    elif fmt == "imazing-csv":
        records = parse_imazing_csv(args.export)
    elif fmt == "google-voice-html":
        records = parse_google_voice_html(args.export)
    else:
        print(f"unknown export format: {args.export}", file=sys.stderr)
        return 2

    summary = write_three_layers(raw, records, args.export, args.out_dir)

    if args.manifest is not None:
        try:
            append_entry(args.manifest, {"kind": "sms_export", **summary}, force=args.force)
        except FileExistsError as e:
            print(str(e), file=sys.stderr)
            return 3

    print(
        f"{args.export} -> {summary['message_count']} messages, "
        f"source_id={summary['source_id']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
