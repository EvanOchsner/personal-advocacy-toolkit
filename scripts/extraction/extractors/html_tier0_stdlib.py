"""Tier-0 HTML extractor: stdlib ``html.parser`` only.

Ported from the previous ``scripts/ingest/html_to_text.py``. This is
the cheap path: well-formed static HTML renders cleanly, with
``<title>`` captured, block tags becoming newlines, lists prefixed
with ``- ``, links rendered as ``text (url)``, and images as
``[image: alt]``. JS-rendered SPAs trip the cascade's HTML emptiness
heuristic and escalate to tier 1 (Trafilatura) and tier 2
(Playwright).
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

from ..result import ExtractionResult


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


def detect_charset(raw: bytes) -> str:
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
                self._chunks.append("\x00HREF\x00" + href + "\x00")
            return
        if tag == "img":
            alt = next((v for (k, v) in attrs if k == "alt" and v), None)
            if alt:
                self._chunks.append(f"[image: {alt}]")
            return
        if tag in _BLOCK_TAGS:
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
        sentinel = "\x00HREF\x00"
        for i in range(len(self._chunks) - 1, -1, -1):
            chunk = self._chunks[i]
            if chunk.startswith(sentinel):
                href = chunk[len(sentinel):].rstrip("\x00")
                self._chunks[i] = ""
                self._chunks.append(f" ({href})")
                return

    def get_text(self) -> str:
        joined = "".join(self._chunks)
        joined = re.sub(r"\x00HREF\x00[^\x00]*\x00", "", joined)
        lines = [line.rstrip() for line in joined.split("\n")]
        cleaned = "\n".join(lines)
        cleaned = _BLANK_LINE_RUN.sub("\n\n", cleaned)
        return cleaned.strip() + "\n" if cleaned.strip() else ""


def render_html(raw: bytes) -> tuple[str, str | None, str]:
    """Decode and render `raw` HTML bytes.

    Returns (plaintext, title, charset). Public for callers that just
    want HTML→text conversion without going through the cascade.
    """
    charset = detect_charset(raw)
    try:
        decoded = raw.decode(charset, errors="replace")
    except LookupError:
        decoded = raw.decode("utf-8", errors="replace")
        charset = "utf-8"
    decoded = html.unescape(decoded)
    parser = _Renderer()
    parser.feed(decoded)
    parser.close()
    return parser.get_text(), parser.title, charset


def extract(raw_bytes: bytes) -> ExtractionResult:
    """Tier-0 cascade entry point for HTML."""
    text, title, charset = render_html(raw_bytes)
    return ExtractionResult(
        text=text,
        method="html.parser",
        tier=0,
        settings={"charset": charset},
        title=title,
        charset=charset,
    )
