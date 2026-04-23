#!/usr/bin/env python3
"""Parse one or more `.eml` files into a canonical JSON-per-message form.

The JSON shape is intentionally stable so downstream tools (manifest,
packet, analysis) can consume a directory of JSONs without re-parsing
MIME. One `.eml` produces exactly one `.json` by the same stem.

Usage:
    uv run python -m scripts.ingest.email_eml_to_json INPUT [INPUT ...] \
        --out-dir data/correspondence/json/ \
        [--manifest data/correspondence/manifest.yaml] \
        [--overwrite]

Design notes (generalized from the lucy-repair-fight original):
  - No case-specific identifiers (claim numbers, party names) in the
    parser. Filtering / labeling is the manifest tool's job.
  - Uses only the stdlib `email` package so we do not introduce a new
    runtime dep. `mail-parser` was considered and rejected: its value-add
    over stdlib is small for our purposes and it drags chardet + six.
  - Attachments are recorded by name + content-type + size + sha256,
    and optionally written to an `attachments/` subdir of --out-dir.
"""
from __future__ import annotations

import argparse
import email
import email.policy
import hashlib
import json
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any


def _addr_list(value: str | None) -> list[dict[str, str]]:
    if not value:
        return []
    return [{"name": name, "email": addr} for name, addr in getaddresses([value]) if addr]


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _best_body(msg: EmailMessage) -> tuple[str | None, str | None]:
    """Return (text_plain, text_html) using the policy's body selector."""
    text_plain = None
    text_html = None
    try:
        plain_part = msg.get_body(preferencelist=("plain",))
        if plain_part is not None:
            text_plain = plain_part.get_content()
    except (KeyError, LookupError):
        pass
    try:
        html_part = msg.get_body(preferencelist=("html",))
        if html_part is not None:
            text_html = html_part.get_content()
    except (KeyError, LookupError):
        pass
    if text_plain is None and not msg.is_multipart():
        ct = msg.get_content_type()
        if ct == "text/plain":
            text_plain = msg.get_content()
        elif ct == "text/html":
            text_html = msg.get_content()
    return text_plain, text_html


def _walk_attachments(
    msg: EmailMessage,
    attach_dir: Path | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for part in msg.iter_attachments():
        payload = part.get_payload(decode=True) or b""
        digest = hashlib.sha256(payload).hexdigest()
        filename = part.get_filename() or f"attachment-{digest[:8]}"
        record: dict[str, Any] = {
            "filename": filename,
            "content_type": part.get_content_type(),
            "size_bytes": len(payload),
            "sha256": digest,
        }
        if attach_dir is not None and payload:
            attach_dir.mkdir(parents=True, exist_ok=True)
            # Prefix with digest to avoid collisions across messages.
            safe = f"{digest[:12]}_{Path(filename).name}"
            (attach_dir / safe).write_bytes(payload)
            record["saved_as"] = safe
        out.append(record)
    return out


def parse_eml(
    eml_path: Path,
    attach_dir: Path | None = None,
) -> dict[str, Any]:
    """Parse a single .eml file into a canonical dict."""
    with eml_path.open("rb") as fh:
        msg: EmailMessage = email.message_from_binary_file(
            fh, policy=email.policy.default
        )  # type: ignore[assignment]
    text_plain, text_html = _best_body(msg)
    attachments = _walk_attachments(msg, attach_dir)
    raw_bytes = eml_path.read_bytes()
    return {
        "source_path": str(eml_path),
        "source_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "message_id": msg.get("Message-ID"),
        "date_raw": msg.get("Date"),
        "date_iso": _iso_date(msg.get("Date")),
        "subject": msg.get("Subject"),
        "from": _addr_list(msg.get("From")),
        "to": _addr_list(msg.get("To")),
        "cc": _addr_list(msg.get("Cc")),
        "bcc": _addr_list(msg.get("Bcc")),
        "reply_to": _addr_list(msg.get("Reply-To")),
        "in_reply_to": msg.get("In-Reply-To"),
        "references": msg.get("References"),
        "headers": {k: v for k, v in msg.items()},
        "body_text": text_plain,
        "body_html": text_html,
        "attachments": attachments,
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }


def _write_json(record: dict[str, Any], out_path: Path, overwrite: bool) -> None:
    if out_path.exists() and not overwrite:
        raise FileExistsError(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, indent=2, ensure_ascii=False))


def _append_to_manifest(manifest_path: Path, record: dict[str, Any], json_path: Path) -> None:
    """Best-effort manifest append. YAML if PyYAML is available, else JSON-lines sidecar."""
    entry = {
        "json": str(json_path),
        "message_id": record.get("message_id"),
        "date_iso": record.get("date_iso"),
        "subject": record.get("subject"),
        "from": record.get("from"),
        "to": record.get("to"),
        "source_sha256": record.get("source_sha256"),
    }
    try:
        import yaml  # type: ignore
    except ImportError:
        # Fallback: JSON-lines alongside the requested manifest.
        jsonl = manifest_path.with_suffix(manifest_path.suffix + ".jsonl")
        with jsonl.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return
    existing: list[dict[str, Any]] = []
    if manifest_path.exists():
        loaded = yaml.safe_load(manifest_path.read_text()) or {}
        existing = loaded.get("entries", []) if isinstance(loaded, dict) else []
    existing.append(entry)
    manifest_path.write_text(yaml.safe_dump({"entries": existing}, sort_keys=False))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("inputs", nargs="+", type=Path, help=".eml files or dirs containing them")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument(
        "--save-attachments",
        action="store_true",
        help="Write decoded attachment bytes into <out-dir>/attachments/",
    )
    p.add_argument("--manifest", type=Path, default=None, help="Optional manifest to append to")
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args(argv)

    eml_files: list[Path] = []
    for item in args.inputs:
        if item.is_dir():
            eml_files.extend(sorted(item.rglob("*.eml")))
        elif item.suffix.lower() == ".eml":
            eml_files.append(item)
        else:
            print(f"skip (not .eml): {item}", file=sys.stderr)
    if not eml_files:
        print("no .eml inputs found", file=sys.stderr)
        return 2

    attach_dir = args.out_dir / "attachments" if args.save_attachments else None
    for eml in eml_files:
        record = parse_eml(eml, attach_dir=attach_dir)
        out_path = args.out_dir / (eml.stem + ".json")
        _write_json(record, out_path, args.overwrite)
        if args.manifest is not None:
            _append_to_manifest(args.manifest, record, out_path)
        print(f"{eml} -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
