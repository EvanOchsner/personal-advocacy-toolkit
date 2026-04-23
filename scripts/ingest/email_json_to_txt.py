#!/usr/bin/env python3
"""Render canonical email JSON (as produced by email_eml_to_json.py) into a
human-readable `.txt` transcript — the form that's easy to skim, diff,
print, or paste into a packet.

Usage:
    uv run python -m scripts.ingest.email_json_to_txt INPUT [INPUT ...] \
        --out-dir data/correspondence/txt/ \
        [--overwrite]

The output is deliberately plain text (no HTML, no Markdown) so it renders
identically in Mail.app, `less`, and printed exhibits.
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
from pathlib import Path
from typing import Any


def _fmt_addrs(addrs: list[dict[str, str]] | dict[str, str] | None) -> str:
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


def render_txt(record: dict[str, Any]) -> str:
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
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("inputs", nargs="+", type=Path, help=".json files or dirs")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--overwrite", action="store_true")
    p.add_argument(
        "--wrap", type=int, default=0, help="Hard-wrap body at N cols (0 = no wrap)"
    )
    args = p.parse_args(argv)

    files: list[Path] = []
    for item in args.inputs:
        if item.is_dir():
            files.extend(sorted(item.rglob("*.json")))
        elif item.suffix.lower() == ".json":
            files.append(item)
        else:
            print(f"skip (not .json): {item}", file=sys.stderr)
    if not files:
        print("no .json inputs found", file=sys.stderr)
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for j in files:
        record = json.loads(j.read_text())
        text = render_txt(record)
        if args.wrap and args.wrap > 0:
            text = "\n".join(
                textwrap.fill(line, width=args.wrap, replace_whitespace=False) or ""
                for line in text.splitlines()
            )
        out = args.out_dir / (j.stem + ".txt")
        if out.exists() and not args.overwrite:
            print(f"exists, skip: {out}", file=sys.stderr)
            continue
        out.write_text(text)
        print(f"{j} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
