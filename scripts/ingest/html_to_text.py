#!/usr/bin/env python3
"""Ingest a standalone HTML document into the project's three-layer shape.

Pipeline:
  raw/<source_id>.html           # byte-identical copy of the input
  structured/<source_id>.json    # provenance + extraction metadata
  human/<source_id>.txt          # plaintext rendering

Some adversaries deliver content as HTML where the visible text is
nontrivial to recover (nested tables, inline styles, MIME-encoded
images, no plaintext alternative). This ingester runs a stdlib-only
HTML→text pass that preserves enough structure for skimming and grep:

  - `<script>`, `<style>`, and most `<head>` content is dropped
    (`<title>` is captured and recorded in the structured JSON).
  - Block-level closes (`</p>`, `</div>`, `</li>`, `</tr>`, headings,
    `<br>`) become newlines.
  - `<li>` items get a `- ` prefix.
  - `<a href="X">text</a>` renders as `text (X)` so URLs stay grep-able.
  - `<img alt="X">` renders as `[image: X]`.
  - HTML entities are decoded via `html.unescape`.
  - Runs of 3+ blank lines collapse to 2.

No third-party HTML parser is used — `html.parser.HTMLParser` is
stdlib. Inputs that are pathological enough to defeat it can be
converted upstream (e.g., open in a browser and "save as plain text")
and re-ingested via this same tool.

Canonical structured record:

    {
      "source_file": "<original input path>",
      "source_sha256": "<hex>",
      "source_id": "<hex[:16]>",
      "title": "<contents of <title>, if any>",
      "charset": "<detected charset>",
      "text_chars": <int>,
      "raw_path": "<copy under out_dir/raw/>",
      "plaintext_path": "<.txt under out_dir/human/>",
      "parsed_at": "<UTC ISO-8601>"
    }

Usage:
    uv run python -m scripts.ingest.html_to_text input.html [more.html ...] \\
        --out-dir evidence/html/ \\
        [--manifest evidence/html/manifest.yaml] \\
        [--force]

Inputs may also be directories; every `.html` / `.htm` found
(non-recursive) is processed.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from scripts.ingest._manifest import append_entry


_HTML_SUFFIXES = {".html", ".htm"}

_BLOCK_TAGS = {
    "p", "div", "br", "li", "tr", "section", "article",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre", "ul", "ol", "table", "thead", "tbody",
    "header", "footer", "nav", "main", "aside",
    "hr",
}
_DROP_TAGS = {"script", "style", "noscript", "template"}
_CHARSET_META_RE = re.compile(
    rb"""<meta[^>]+charset\s*=\s*['"]?([A-Za-z0-9_\-:.]+)""",
    re.IGNORECASE,
)
_BLANK_LINE_RUN = re.compile(r"\n{3,}")


def _detect_charset(raw: bytes) -> str:
    """Look for a `<meta charset>` declaration in the first few KB; default UTF-8."""
    head = raw[:4096]
    m = _CHARSET_META_RE.search(head)
    if m:
        try:
            return m.group(1).decode("ascii").lower()
        except UnicodeDecodeError:
            pass
    return "utf-8"


class _Renderer(HTMLParser):
    """Convert HTML into a plaintext rendering preserving block structure."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._drop_depth = 0
        self._in_title = False
        self._in_head = False
        self.title: str | None = None
        self._title_buf: list[str] = []
        self._pending_li_marker = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "head":
            self._in_head = True
        if tag in _DROP_TAGS:
            self._drop_depth += 1
            return
        if tag == "title":
            self._in_title = True
            return
        if self._drop_depth or self._in_head:
            return
        if tag == "br":
            self._chunks.append("\n")
            return
        if tag == "li":
            self._chunks.append("\n- ")
            self._pending_li_marker = True
            return
        if tag == "a":
            href = next((v for (k, v) in attrs if k == "href" and v), None)
            if href:
                # Stash href; emitted at endtag.
                self._chunks.append("\x00HREF\x00" + href + "\x00")
            return
        if tag == "img":
            alt = next((v for (k, v) in attrs if k == "alt" and v), None)
            if alt:
                self._chunks.append(f"[image: {alt}]")
            return
        if tag in _BLOCK_TAGS:
            # Open block: ensure we're on a fresh line.
            if self._chunks and not self._chunks[-1].endswith("\n"):
                self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "head":
            self._in_head = False
            return
        if tag in _DROP_TAGS:
            if self._drop_depth > 0:
                self._drop_depth -= 1
            return
        if tag == "title":
            self._in_title = False
            self.title = "".join(self._title_buf).strip() or None
            return
        if self._drop_depth or self._in_head:
            return
        if tag == "a":
            # Close out the most recent HREF marker by attaching " (url)".
            self._close_href()
            return
        if tag in _BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._drop_depth:
            return
        if self._in_title:
            self._title_buf.append(data)
            return
        if self._in_head:
            return
        if self._pending_li_marker:
            data = data.lstrip()
            self._pending_li_marker = False
        self._chunks.append(data)

    def _close_href(self) -> None:
        # Walk back and find the last sentinel chunk; emit "<text> (<url>)".
        sentinel = "\x00HREF\x00"
        for i in range(len(self._chunks) - 1, -1, -1):
            chunk = self._chunks[i]
            if chunk.startswith(sentinel):
                href = chunk[len(sentinel):].rstrip("\x00")
                # Replace the sentinel with empty; append " (href)" at end.
                self._chunks[i] = ""
                self._chunks.append(f" ({href})")
                return
        # No sentinel found (link without href) — nothing to do.

    def get_text(self) -> str:
        joined = "".join(self._chunks)
        # Strip residual sentinels (e.g. <a> with no </a>).
        joined = re.sub(r"\x00HREF\x00[^\x00]*\x00", "", joined)
        # Normalize whitespace per line, then collapse blank-line runs.
        lines = [line.rstrip() for line in joined.split("\n")]
        cleaned = "\n".join(lines)
        cleaned = _BLANK_LINE_RUN.sub("\n\n", cleaned)
        return cleaned.strip() + "\n" if cleaned.strip() else ""


def render_html(raw: bytes) -> tuple[str, str | None, str]:
    """Decode and render `raw` HTML bytes.

    Returns (plaintext, title, charset).
    """
    charset = _detect_charset(raw)
    try:
        decoded = raw.decode(charset, errors="replace")
    except LookupError:
        decoded = raw.decode("utf-8", errors="replace")
        charset = "utf-8"
    decoded = html.unescape(decoded)  # belt-and-suspenders alongside convert_charrefs
    parser = _Renderer()
    parser.feed(decoded)
    parser.close()
    return parser.get_text(), parser.title, charset


def _expand_inputs(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            out.extend(
                sorted(q for q in p.iterdir() if q.suffix.lower() in _HTML_SUFFIXES)
            )
        else:
            out.append(p)
    return out


def ingest_html(src: Path, out_dir: Path) -> dict[str, Any]:
    """Process a single HTML file and return its structured summary record."""
    raw_bytes = src.read_bytes()
    source_sha = hashlib.sha256(raw_bytes).hexdigest()
    source_id = source_sha[:16]

    raw_dir = out_dir / "raw"
    struct_dir = out_dir / "structured"
    human_dir = out_dir / "human"
    for d in (raw_dir, struct_dir, human_dir):
        d.mkdir(parents=True, exist_ok=True)

    raw_out = raw_dir / f"{source_id}{src.suffix.lower() or '.html'}"
    raw_out.write_bytes(raw_bytes)

    text, title, charset = render_html(raw_bytes)

    plaintext_path = human_dir / f"{source_id}.txt"
    plaintext_path.write_text(text, encoding="utf-8")

    parsed_at = datetime.now(timezone.utc).isoformat()

    record: dict[str, Any] = {
        "source_file": str(src),
        "source_sha256": source_sha,
        "source_id": source_id,
        "title": title,
        "charset": charset,
        "text_chars": len(text),
        "raw_path": str(raw_out),
        "plaintext_path": str(plaintext_path),
        "parsed_at": parsed_at,
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

    htmls = _expand_inputs(args.inputs)
    if not htmls:
        print("no HTML inputs found", file=sys.stderr)
        return 2

    rc = 0
    for h in htmls:
        if not h.is_file():
            print(f"skip: {h} (not a file)", file=sys.stderr)
            rc = 1
            continue
        record = ingest_html(h, args.out_dir)
        if args.manifest is not None:
            try:
                append_entry(
                    args.manifest, {"kind": "html_to_text", **record}, force=args.force
                )
            except FileExistsError as e:
                print(str(e), file=sys.stderr)
                rc = 3
                continue
        title_note = f" title={record['title']!r}" if record["title"] else ""
        print(
            f"{h} -> {record['source_id']}: "
            f"{record['text_chars']} chars{title_note}"
        )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
