"""Pure-function OOXML text-edit primitives for docx_apply_replies.

The `docx-comment-roundtrip` skill supports three edit modes:

    reply   — specialist's `edit_proposal` becomes a "Suggested edit: …"
              prose comment; no document text changes.
    tracked — apply Word tracked-change markup (`<w:ins>` / `<w:del>`)
              at the find target inside the parent comment's anchor.
    silent  — replace text directly in `<w:t>` with no markup.

All three paths converge on this module for find-and-replace inside a
comment's anchor range. Two public operations:

    apply_tracked_edit(doc_text, parent_comment_id, find, replace,
                       revision_id, author, iso_date)
        -> (new_doc_text, ok, reason)

    apply_silent_edit(doc_text, parent_comment_id, find, replace)
        -> (new_doc_text, ok, reason)

Both enforce guardrails:

    1. `find` is non-empty.
    2. commentRangeStart / commentRangeEnd markers for `parent_comment_id`
       exist in document.xml.
    3. `find` occurs exactly once in the anchor range (counting on the
       XML-escaped form).
    4. `find` falls entirely within a single `<w:r>` whose only text
       element is a single `<w:t>` (no tabs, breaks, or other content).

On any guardrail miss, ok=False and reason names which rule failed.
doc_text is returned unchanged in that case.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import NamedTuple


# Regexes compiled at module scope; all operate on XML text with our
# comment-tracking namespace assumed to be bound to the "w:" prefix.
_RUN_RE = re.compile(r"<w:r(?:\s[^>]*)?>(.*?)</w:r>", re.DOTALL)
_T_RE = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", re.DOTALL)
_RPR_RE = re.compile(r"<w:rPr\b.*?</w:rPr>", re.DOTALL)
_REV_ID_RE = re.compile(r'<w:(?:ins|del)\s+[^>]*w:id="(\d+)"')


class RunInfo(NamedTuple):
    abs_start: int         # offset of '<w:r' in doc_text
    abs_end: int           # offset past '</w:r>'
    full_xml: str          # complete '<w:r>…</w:r>'
    inner: str             # content between tags
    text_escaped: str      # exactly as in <w:t>…</w:t>
    rpr: str               # '<w:rPr>…</w:rPr>' block or ''
    is_simple: bool        # True iff inner is (rPr?)(<w:t>…</w:t>)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def next_revision_id(doc_text: str) -> int:
    ids = [int(m.group(1)) for m in _REV_ID_RE.finditer(doc_text)]
    return max(ids) + 1 if ids else 1


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _space_attr(text: str) -> str:
    if text and (text[:1].isspace() or text[-1:].isspace()):
        return ' xml:space="preserve"'
    return ""


def _find_marker(doc_text: str, tag: str, cid: int) -> int | None:
    """Return byte offset of a self-closing marker like
    <w:commentRangeStart w:id="N"/>. Returns None if not found.
    """
    pat = rf'<w:{tag}\s+[^>]*w:id="{cid}"[^>]*/>'
    m = re.search(pat, doc_text)
    return m.start() if m else None


def _find_marker_end(doc_text: str, tag: str, cid: int) -> int | None:
    pat = rf'<w:{tag}\s+[^>]*w:id="{cid}"[^>]*/>'
    m = re.search(pat, doc_text)
    return m.end() if m else None


def find_anchor_runs(
    doc_text: str, comment_id: int
) -> tuple[int, int, list[RunInfo]] | None:
    """Locate the anchor's range-start / range-end, collect <w:r> runs in between."""
    start = _find_marker_end(doc_text, "commentRangeStart", comment_id)
    if start is None:
        return None
    end = _find_marker(doc_text, "commentRangeEnd", comment_id)
    if end is None or end <= start:
        return None
    region = doc_text[start:end]
    runs: list[RunInfo] = []
    for m in _RUN_RE.finditer(region):
        full = m.group(0)
        inner = m.group(1)
        abs_start = start + m.start()
        abs_end = start + m.end()
        t_match = _T_RE.search(inner)
        text_escaped = t_match.group(1) if t_match else ""
        rpr_match = _RPR_RE.search(inner)
        rpr = rpr_match.group(0) if rpr_match else ""
        # Simple = inner consists of just the optional rPr + exactly one
        # <w:t>…</w:t> with no sibling elements (no <w:tab/>, <w:br/>, …).
        stripped = _RPR_RE.sub("", inner, count=1).strip()
        t_count = len(re.findall(r"<w:t[\s>]", stripped))
        # Non-text run-level elements that disqualify a run from simple.
        compound_markers = re.search(
            r"<w:(?:tab|br|drawing|pict|object|sym|noBreakHyphen|softHyphen|ptab|cr|fldChar|instrText)\b",
            stripped,
        )
        is_simple = (
            t_match is not None
            and t_count == 1
            and compound_markers is None
        )
        runs.append(
            RunInfo(
                abs_start=abs_start,
                abs_end=abs_end,
                full_xml=full,
                inner=inner,
                text_escaped=text_escaped,
                rpr=rpr,
                is_simple=is_simple,
            )
        )
    return start, end, runs


def _locate_find_in_runs(
    runs: list[RunInfo], find_escaped: str
) -> tuple[int, int] | tuple[None, str]:
    """Return (run_index, within_index) on success, or (None, reason) on miss."""
    total_hits = 0
    hit_run: int | None = None
    hit_within: int | None = None
    for i, r in enumerate(runs):
        count = r.text_escaped.count(find_escaped)
        if count:
            total_hits += count
            if hit_run is None:
                hit_run = i
                hit_within = r.text_escaped.find(find_escaped)
    # Also check cross-run: concatenation of all run texts.
    joined = "".join(r.text_escaped for r in runs)
    joined_hits = joined.count(find_escaped)
    if joined_hits == 0:
        return None, "find-not-in-anchor"
    if joined_hits > 1:
        return None, "find-ambiguous"
    # joined_hits == 1: did we see it within a single run?
    if total_hits != 1 or hit_run is None:
        return None, "find-spans-runs"
    if not runs[hit_run].is_simple:
        return None, "find-in-compound-run"
    return hit_run, hit_within  # type: ignore[return-value]


def _make_run(rpr: str, text_escaped: str) -> str:
    decoded = text_escaped.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    space = _space_attr(decoded)
    return f"<w:r>{rpr}<w:t{space}>{text_escaped}</w:t></w:r>"


def _make_del(rev_id: int, author: str, iso_date: str, rpr: str,
              text_escaped: str) -> str:
    decoded = text_escaped.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    space = _space_attr(decoded)
    return (
        f'<w:del w:id="{rev_id}" w:author="{_xml_escape(author)}" '
        f'w:date="{iso_date}">'
        f"<w:r>{rpr}<w:delText{space}>{text_escaped}</w:delText></w:r>"
        f"</w:del>"
    )


def _make_ins(rev_id: int, author: str, iso_date: str, rpr: str,
              text_escaped: str) -> str:
    decoded = text_escaped.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    space = _space_attr(decoded)
    return (
        f'<w:ins w:id="{rev_id}" w:author="{_xml_escape(author)}" '
        f'w:date="{iso_date}">'
        f"<w:r>{rpr}<w:t{space}>{text_escaped}</w:t></w:r>"
        f"</w:ins>"
    )


def _apply_find_replace(
    doc_text: str,
    parent_comment_id: int,
    find: str,
    replace: str,
) -> tuple[RunInfo, str, str, str] | tuple[None, str]:
    """Shared validation path for tracked and silent edits.

    Returns (target_run, pre_text, find_escaped, post_text) on success
    or (None, reason) on guardrail failure.
    """
    if not find:
        return None, "find-empty"
    located = find_anchor_runs(doc_text, parent_comment_id)
    if located is None:
        return None, "anchor-markers-missing"
    _, _, runs = located
    if not runs:
        return None, "anchor-has-no-runs"
    find_escaped = _xml_escape(find)
    outcome = _locate_find_in_runs(runs, find_escaped)
    if outcome[0] is None:
        return None, outcome[1]
    run_idx, within = outcome  # type: ignore[misc]
    r = runs[run_idx]
    pre_text = r.text_escaped[:within]
    post_text = r.text_escaped[within + len(find_escaped):]
    return r, pre_text, find_escaped, post_text


def apply_tracked_edit(
    doc_text: str,
    parent_comment_id: int,
    find: str,
    replace: str,
    revision_id: int,
    author: str,
    iso_date: str,
) -> tuple[str, bool, str]:
    outcome = _apply_find_replace(doc_text, parent_comment_id, find, replace)
    if outcome[0] is None:
        return doc_text, False, outcome[1]
    r, pre, find_esc, post = outcome  # type: ignore[misc]
    replace_esc = _xml_escape(replace)

    pieces: list[str] = []
    if pre:
        pieces.append(_make_run(r.rpr, pre))
    pieces.append(_make_del(revision_id, author, iso_date, r.rpr, find_esc))
    if replace_esc:
        pieces.append(
            _make_ins(revision_id + 1, author, iso_date, r.rpr, replace_esc)
        )
    if post:
        pieces.append(_make_run(r.rpr, post))
    new_run_xml = "".join(pieces)
    new_doc = doc_text[:r.abs_start] + new_run_xml + doc_text[r.abs_end:]
    return new_doc, True, ""


def apply_silent_edit(
    doc_text: str,
    parent_comment_id: int,
    find: str,
    replace: str,
) -> tuple[str, bool, str]:
    outcome = _apply_find_replace(doc_text, parent_comment_id, find, replace)
    if outcome[0] is None:
        return doc_text, False, outcome[1]
    r, pre, find_esc, post = outcome  # type: ignore[misc]
    replace_esc = _xml_escape(replace)
    new_text = pre + replace_esc + post
    new_run_xml = _make_run(r.rpr, new_text)
    new_doc = doc_text[:r.abs_start] + new_run_xml + doc_text[r.abs_end:]
    return new_doc, True, ""


def count_claude_revisions(
    doc_text: str, author: str = "Claude"
) -> tuple[int, int]:
    author_attr = f'w:author="{_xml_escape(author)}"'
    ins = len(re.findall(rf"<w:ins\s+[^>]*{re.escape(author_attr)}", doc_text))
    dels = len(re.findall(rf"<w:del\s+[^>]*{re.escape(author_attr)}", doc_text))
    return ins, dels
