#!/usr/bin/env python3
"""Split a Unix-mbox file into individual `.eml` files.

Unfiltered split by default; optional --filter-config accepts the same
YAML/TOML schema as `scripts/manifest/correspondence_manifest.py` so you
can narrow a mbox to e.g. a single counterparty on first pass.

Usage:
    python -m scripts.ingest.mbox_split INPUT.mbox --out-dir DIR [--prefix all] \
        [--filter-config cfg.yaml]

Output filenames: `<prefix>_<NNNN>_<sanitized-subject>.eml`.
"""
from __future__ import annotations

import argparse
import mailbox
import re
import sys
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path


_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(text: str | None, max_len: int = 48) -> str:
    if not text:
        return "nosubject"
    s = _SAFE_CHARS.sub("-", text.strip()).strip("-")
    return (s or "nosubject")[:max_len]


def _load_filter(path: Path | None):
    """Load an optional filter config. Returns a predicate (msg) -> bool or None."""
    if path is None:
        return None
    # Late import so we only require the dep if a filter is actually requested.
    from scripts.manifest.correspondence_manifest import (  # type: ignore
        load_config,
        message_matches,
    )

    cfg = load_config(path)
    return lambda msg: message_matches(msg, cfg)


def split_mbox(
    mbox_path: Path,
    out_dir: Path,
    prefix: str = "msg",
    predicate=None,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    mbox = mailbox.mbox(str(mbox_path))
    try:
        for i, msg in enumerate(mbox):
            if predicate is not None and not predicate(msg):
                continue
            # Prefer date-sortable stem when Date: is parseable, fall back to index.
            date_str = ""
            try:
                dt = parsedate_to_datetime(msg.get("Date", ""))
                if dt is not None:
                    date_str = dt.strftime("%Y%m%dT%H%M%S") + "_"
            except (TypeError, ValueError):
                pass
            stem = f"{prefix}_{i:04d}_{date_str}{_slug(msg.get('Subject'))}"
            path = out_dir / f"{stem}.eml"
            # mailbox returns email.message.Message; as_bytes() preserves headers + body.
            path.write_bytes(msg.as_bytes())
            written.append(path)
    finally:
        mbox.close()
    return written


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("mbox", type=Path)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--prefix", default="msg")
    p.add_argument("--filter-config", type=Path, default=None)
    args = p.parse_args(argv)

    if not args.mbox.exists():
        print(f"no such mbox: {args.mbox}", file=sys.stderr)
        return 2

    predicate = _load_filter(args.filter_config)
    written = split_mbox(args.mbox, args.out_dir, prefix=args.prefix, predicate=predicate)
    print(f"wrote {len(written)} .eml files to {args.out_dir}")
    return 0


# Used by tests and by correspondence_manifest filter helpers. Kept here so
# mbox_split stays standalone when no filter config is supplied.
def addresses_in(msg) -> list[str]:
    fields = []
    for h in ("From", "To", "Cc", "Bcc", "Reply-To"):
        v = msg.get(h)
        if v:
            fields.append(v)
    return [addr.lower() for _, addr in getaddresses(fields) if addr]


if __name__ == "__main__":
    raise SystemExit(main())
