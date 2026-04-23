"""Minimal, conservative Markdown -> HTML renderer for entity notes.

Intentionally tiny: the app is airgap-policy-level, not structural, and
every external rendering dependency expands the surface area we have
to audit. This module supports:

    - headings:   `# h1` … `###### h6`
    - emphasis:   `**bold**`, `*italic*`, `_italic_`, `__bold__`
    - inline code: `` `code` ``
    - unordered list items: `- item`
    - paragraphs separated by blank lines
    - internal links: `[text](relative/path)` — but ONLY if the URL
      contains no scheme (no `:`). External URLs are emitted as plain
      text, not anchor tags, to prevent CSP-bypassing clicks.

Not supported (on purpose): raw HTML passthrough, images, blockquotes,
tables, ordered lists, fenced code blocks, reference links, autolinks.
If users want richer notes they can split them across headings and
paragraphs.
"""
from __future__ import annotations

import html
import re

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST_ITEM_RE = re.compile(r"^\s*-\s+(.*)$")

_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)|(?<!_)_([^_\n]+)_(?!_)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def render(text: str) -> str:
    """Return sanitized HTML for the given markdown source."""
    if not text:
        return ""
    blocks = _split_blocks(text)
    rendered = [_render_block(b) for b in blocks]
    return "\n".join(b for b in rendered if b)


def _split_blocks(text: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    cur: list[str] = []
    for line in text.splitlines():
        if line.strip() == "":
            if cur:
                blocks.append(cur)
                cur = []
            continue
        cur.append(line)
    if cur:
        blocks.append(cur)
    return blocks


def _render_block(lines: list[str]) -> str:
    if not lines:
        return ""

    first = lines[0]
    h = _HEADING_RE.match(first)
    if h and len(lines) == 1:
        level = len(h.group(1))
        return f"<h{level}>{_render_inline(h.group(2))}</h{level}>"

    if all(_LIST_ITEM_RE.match(line) for line in lines):
        items = [
            f"<li>{_render_inline(_LIST_ITEM_RE.match(line).group(1))}</li>"  # type: ignore[union-attr]
            for line in lines
        ]
        return "<ul>\n" + "\n".join(items) + "\n</ul>"

    # Paragraph fallback: join with <br> so intra-paragraph newlines
    # survive for the user's visual formatting.
    joined = "<br>\n".join(_render_inline(line) for line in lines)
    return f"<p>{joined}</p>"


def _render_inline(text: str) -> str:
    # Escape first; then re-introduce safe markup. This is how we avoid
    # raw HTML passthrough: every `<` in user input is already `&lt;`
    # before any of our regexes run.
    safe = html.escape(text, quote=True)

    # Inline code — placeholder-protect so subsequent regexes don't
    # match inside code.
    code_spans: list[str] = []

    def _stash_code(m: re.Match[str]) -> str:
        code_spans.append(m.group(1))
        return f"\x00CODE{len(code_spans) - 1}\x00"

    safe = _INLINE_CODE_RE.sub(_stash_code, safe)

    # Links: only internal (no scheme). External URLs become plain
    # text (the `[text](url)` source renders verbatim).
    def _link_sub(m: re.Match[str]) -> str:
        label, url = m.group(1), m.group(2)
        if ":" in url or url.startswith("//"):
            return m.group(0)  # leave untouched → renders as source text
        return f'<a href="{url}">{label}</a>'

    safe = _LINK_RE.sub(_link_sub, safe)

    safe = _BOLD_RE.sub(lambda m: f"<strong>{m.group(2)}</strong>", safe)
    safe = _ITALIC_RE.sub(
        lambda m: f"<em>{m.group(1) or m.group(2)}</em>", safe
    )

    # Restore code spans.
    def _restore_code(m: re.Match[str]) -> str:
        idx = int(m.group(1))
        return f"<code>{code_spans[idx]}</code>"

    safe = re.sub(r"\x00CODE(\d+)\x00", _restore_code, safe)
    return safe
