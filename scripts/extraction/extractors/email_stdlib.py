"""Tier-0 email extractor: stdlib ``email`` package.

Ported from the previous ``scripts/ingest/email_eml_to_json.py`` and
``scripts/ingest/email_json_to_txt.py``. Email is single-tier — the
stdlib parser is enough; we don't add a VLM tier here because the
cost/benefit doesn't make sense.

Two functions:

  - ``parse_eml(eml_path, attach_dir=None)`` — produces the canonical
    JSON-shaped dict.
  - ``render_text(record)`` — renders the canonical dict to a plain
    ``.txt`` transcript suitable for printing or pasting into a packet.
"""
from __future__ import annotations

import email
import email.policy
import hashlib
import textwrap
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any

from ..result import ExtractionResult


def _addr_list(value: str | None) -> list[dict[str, str]]:
    if not value:
        return []
    return [
        {"name": name, "email": addr}
        for name, addr in getaddresses([value])
        if addr
    ]


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
            safe = f"{digest[:12]}_{Path(filename).name}"
            (attach_dir / safe).write_bytes(payload)
            record["saved_as"] = safe
        out.append(record)
    return out


def parse_eml(
    eml_path: Path,
    attach_dir: Path | None = None,
) -> dict[str, Any]:
    """Parse a single .eml file into the project's canonical dict shape."""
    eml_path = Path(eml_path)
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


def _fmt_addrs(addrs: Any) -> str:
    if not addrs:
        return ""
    if isinstance(addrs, dict):
        addrs = [addrs]
    parts = []
    for a in addrs:
        if isinstance(a, str):
            parts.append(a)
            continue
        name = (a.get("name") or "").strip()
        email_ = (a.get("email") or "").strip()
        parts.append(f"{name} <{email_}>" if name else email_)
    return ", ".join(parts)


def render_text(record: dict[str, Any], *, wrap: int = 0) -> str:
    """Render a canonical email dict to a human-readable transcript."""
    lines: list[str] = []
    lines.append(f"Date:    {record.get('date_iso') or record.get('date_raw') or ''}")
    lines.append(f"From:    {_fmt_addrs(record.get('from'))}")
    lines.append(f"To:      {_fmt_addrs(record.get('to'))}")
    if record.get("cc"):
        lines.append(f"Cc:      {_fmt_addrs(record.get('cc'))}")
    if record.get("bcc"):
        lines.append(f"Bcc:     {_fmt_addrs(record.get('bcc'))}")
    lines.append(f"Subject: {record.get('subject') or ''}")
    if record.get("message_id"):
        lines.append(f"Message-ID: {record['message_id']}")
    attachments = record.get("attachments") or []
    if attachments:
        lines.append(f"Attachments ({len(attachments)}):")
        for att in attachments:
            lines.append(
                f"  - {att.get('filename')} "
                f"({att.get('content_type')}, {att.get('size_bytes')} B, "
                f"sha256={att.get('sha256', '')[:12]}...)"
            )
    lines.append("")
    lines.append("-" * 72)
    lines.append("")
    body = record.get("body_text")
    if not body and record.get("body_html"):
        body = "[HTML-only message; no plain-text alternative]\n\n" + (
            record["body_html"] or ""
        )
    lines.append(body or "[no body]")
    text = "\n".join(lines).rstrip() + "\n"
    if wrap and wrap > 0:
        text = "\n".join(
            textwrap.fill(line, width=wrap, replace_whitespace=False) or ""
            for line in text.splitlines()
        )
    return text


def extract(eml_path: Path, *, attach_dir: Path | None = None) -> ExtractionResult:
    """Tier-0 cascade entry point for emails.

    Returns an ExtractionResult whose ``text`` field is the rendered
    transcript and whose ``settings`` carries the canonical record
    (so the cascade can serialize both the structured JSON and the
    readable .txt without re-parsing).
    """
    record = parse_eml(eml_path, attach_dir=attach_dir)
    text = render_text(record)
    return ExtractionResult(
        text=text,
        method="email.parser",
        tier=0,
        settings={"record": record},
        title=record.get("subject") or None,
    )
