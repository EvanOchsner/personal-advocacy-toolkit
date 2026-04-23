"""Tests for scripts.publish.docx_catalog.

Builds a synthetic unpacked-docx tree with multiple comment threads
exercising the tag grammar, threading via commentsExtended.xml, the
needs-reply rule, commenter-role annotation, and prior-substantive-reply
detection.
"""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scripts.publish.docx_catalog import (
    build_catalog,
    is_skip_marker,
    parse_tag,
    role_for,
)


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
W15 = "http://schemas.microsoft.com/office/word/2012/wordml"


def _write_tree(
    root: Path, *, document_xml: str, comments_xml: str, extended_xml: str
) -> None:
    (root / "word").mkdir(parents=True, exist_ok=True)
    (root / "word" / "document.xml").write_text(document_xml, encoding="utf-8")
    (root / "word" / "comments.xml").write_text(comments_xml, encoding="utf-8")
    (root / "word" / "commentsExtended.xml").write_text(
        extended_xml, encoding="utf-8"
    )


def _document(paragraphs: list[tuple[str, list[int]]]) -> str:
    """paragraphs: list of (body_text, [comment_ids]) tuples.

    Each comment_id gets a commentRangeStart/End wrapping the body_text.
    """
    out = [
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<w:document xmlns:w="{W_NS}"><w:body>',
    ]
    for text, ids in paragraphs:
        out.append("<w:p>")
        for cid in ids:
            out.append(f'<w:commentRangeStart w:id="{cid}"/>')
        out.append(f"<w:r><w:t>{text}</w:t></w:r>")
        for cid in ids:
            out.append(f'<w:commentRangeEnd w:id="{cid}"/>')
            out.append(f'<w:r><w:commentReference w:id="{cid}"/></w:r>')
        out.append("</w:p>")
    out.append("</w:body></w:document>")
    return "".join(out)


def _comments(records: list[dict]) -> str:
    out = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<w:comments xmlns:w="{W_NS}" xmlns:w14="{W14}">',
    ]
    for r in records:
        out.append(
            f'<w:comment w:id="{r["id"]}" w:author="{r["author"]}" '
            f'w:initials="{r.get("initials", "")}" w:date="{r["date"]}">'
            f'<w:p w14:paraId="{r["para_id"]}">'
            f'<w:r><w:t>{r["text"]}</w:t></w:r>'
            f'</w:p></w:comment>'
        )
    out.append("</w:comments>")
    return "".join(out)


def _extended(pairs: list[tuple[str, str]]) -> str:
    out = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<w15:commentsEx xmlns:w15="{W15}">',
    ]
    for pid, parent in pairs:
        parent_attr = f' w15:paraIdParent="{parent}"' if parent else ""
        out.append(f'<w15:commentEx w15:paraId="{pid}" w15:done="0"{parent_attr}/>')
    out.append("</w15:commentsEx>")
    return "".join(out)


# ---------------------------------------------------------------------------
# Unit tests for the small helpers


def test_parse_tag_variants() -> None:
    assert parse_tag("F: check this") == ("F", "check this")
    assert parse_tag("F") == ("F", "")
    assert parse_tag("q+a: mixed") == ("F+A" if False else "Q+A", "mixed")
    assert parse_tag("S") == ("S", "")
    assert parse_tag("untagged question?") == ("", "untagged question?")
    # Tag mid-text does not match.
    assert parse_tag("see F: section") == ("", "see F: section")
    # Whitespace around tag tolerated.
    assert parse_tag("  A:   do the thing") == ("A", "do the thing")


def test_parse_tag_canonicalizes_order() -> None:
    assert parse_tag("A+F")[0] == "F+A"
    assert parse_tag("q+a+f: body")[0] == "F+Q+A"


def test_is_skip_marker_em_dash() -> None:
    assert is_skip_marker("[skip \u2014 user-tagged S:]")
    # Regular hyphen is not the skip marker prefix.
    assert not is_skip_marker("[skip - plain hyphen]")
    assert not is_skip_marker("not a skip at all")


def test_role_for_matches_author() -> None:
    rules = [
        {"match": {"author": "Alice"}, "role": "lawyer"},
        {"match": {"initials": "CM"}, "role": "opposing-counsel"},
    ]
    assert role_for("Alice", "A", rules, "unknown") == "lawyer"
    assert role_for("Bob", "CM", rules, "unknown") == "opposing-counsel"
    assert role_for("Carol", "X", rules, "unknown") == "unknown"


# ---------------------------------------------------------------------------
# Integration: full catalog build


@pytest.fixture
def three_thread_tree(tmp_path: Path) -> Path:
    """Three threads:

    Thread 1 (root id=0, paraId=P0): tagged "F: verify the figure"
    Thread 2 (root id=1, paraId=P1): tagged "F+A: mixed intent"
    Thread 3 (root id=2, paraId=P2): untagged, with a prior Claude reply
        comment 2: Reviewer asks a question
        comment 3: Claude replies at length (>80 chars) - prior substantive
        comment 4: Reviewer re-asks, needs-reply=true, prior flag set
    """
    doc = _document([
        ("First paragraph about a dollar amount.", [0]),
        ("Second paragraph about policy language.", [1]),
        ("Third paragraph about strategy.", [2]),
    ])
    records = [
        {"id": 0, "para_id": "P0", "author": "Reviewer", "initials": "R",
         "date": "2026-04-20T10:00:00Z", "text": "F: verify the figure"},
        {"id": 1, "para_id": "P1", "author": "Reviewer", "initials": "R",
         "date": "2026-04-20T10:05:00Z", "text": "F+A: mixed intent"},
        {"id": 2, "para_id": "P2", "author": "Reviewer", "initials": "R",
         "date": "2026-04-20T10:10:00Z", "text": "Should we reframe this?"},
        {"id": 3, "para_id": "P2R1", "author": "Claude", "initials": "C",
         "date": "2026-04-20T11:00:00Z",
         "text": "A prior substantive Claude reply explaining the tradeoff at length with citations."},
        {"id": 4, "para_id": "P2R2", "author": "Reviewer", "initials": "R",
         "date": "2026-04-20T12:00:00Z", "text": "Still not sure — elaborate?"},
    ]
    ext = [
        ("P0", ""),
        ("P1", ""),
        ("P2", ""),
        ("P2R1", "P2"),
        ("P2R2", "P2"),
    ]
    _write_tree(
        tmp_path,
        document_xml=doc,
        comments_xml=_comments(records),
        extended_xml=_extended(ext),
    )
    return tmp_path


def test_catalog_threads_and_tags(three_thread_tree: Path) -> None:
    cat = build_catalog(three_thread_tree, claude_identity="Claude")
    assert cat["threads_total"] == 3
    # All three threads have a non-Claude last commenter, so all need reply.
    assert cat["threads_needing_reply"] == 3

    # Tag parsing preserved on needs_reply entries.
    tags = {e["thread_root_id"]: e["tag"] for e in cat["needs_reply"]}
    assert tags[0] == "F"
    assert tags[1] == "F+A"
    assert tags[2] == ""  # untagged


def test_catalog_prior_reply_annotation(three_thread_tree: Path) -> None:
    cat = build_catalog(three_thread_tree, claude_identity="Claude")
    thread_2 = next(e for e in cat["needs_reply"] if e["thread_root_id"] == 2)
    assert "prior_substantive_reply" in thread_2
    assert thread_2["prior_substantive_reply"]["comment_id"] == 3
    assert thread_2["prior_substantive_reply"]["author"] == "Claude"

    thread_0 = next(e for e in cat["needs_reply"] if e["thread_root_id"] == 0)
    assert "prior_substantive_reply" not in thread_0


def test_catalog_thread_context_excludes_latest(three_thread_tree: Path) -> None:
    cat = build_catalog(three_thread_tree, claude_identity="Claude")
    thread_2 = next(e for e in cat["needs_reply"] if e["thread_root_id"] == 2)
    ctx_ids = [c["id"] for c in thread_2["thread_context"]]
    # Thread 2 has comments 2, 3, 4. Latest is 4; context should be [2, 3].
    assert ctx_ids == [2, 3]


def test_catalog_anchor_text(three_thread_tree: Path) -> None:
    cat = build_catalog(three_thread_tree, claude_identity="Claude")
    anchors = {e["thread_root_id"]: e["anchor_text"] for e in cat["needs_reply"]}
    assert anchors[0] == "First paragraph about a dollar amount."
    assert anchors[1] == "Second paragraph about policy language."
    assert anchors[2] == "Third paragraph about strategy."


def test_catalog_claude_last_commenter_is_not_needs_reply(tmp_path: Path) -> None:
    doc = _document([("body", [0])])
    records = [
        {"id": 0, "para_id": "P0", "author": "Reviewer", "initials": "R",
         "date": "2026-04-20T10:00:00Z", "text": "F: anything"},
        {"id": 1, "para_id": "P0R1", "author": "Claude", "initials": "C",
         "date": "2026-04-20T11:00:00Z", "text": "Confirmed."},
    ]
    ext = [("P0", ""), ("P0R1", "P0")]
    _write_tree(
        tmp_path,
        document_xml=doc,
        comments_xml=_comments(records),
        extended_xml=_extended(ext),
    )
    cat = build_catalog(tmp_path, claude_identity="Claude")
    assert cat["threads_total"] == 1
    assert cat["threads_needing_reply"] == 0


def test_catalog_skip_marker_is_not_needs_reply(tmp_path: Path) -> None:
    doc = _document([("body", [0])])
    records = [
        {"id": 0, "para_id": "P0", "author": "Reviewer", "initials": "R",
         "date": "2026-04-20T10:00:00Z", "text": "some vent"},
        {"id": 1, "para_id": "P0R1", "author": "Claude", "initials": "C",
         "date": "2026-04-20T11:00:00Z",
         "text": "[skip \u2014 vent, no project hook]"},
    ]
    ext = [("P0", ""), ("P0R1", "P0")]
    _write_tree(
        tmp_path,
        document_xml=doc,
        comments_xml=_comments(records),
        extended_xml=_extended(ext),
    )
    cat = build_catalog(tmp_path, claude_identity="Claude")
    assert cat["threads_needing_reply"] == 0


def test_catalog_role_annotation(tmp_path: Path) -> None:
    doc = _document([("body", [0])])
    records = [
        {"id": 0, "para_id": "P0", "author": "Elena Rojas", "initials": "ER",
         "date": "2026-04-20T10:00:00Z", "text": "F: verify"},
    ]
    ext = [("P0", "")]
    _write_tree(
        tmp_path,
        document_xml=doc,
        comments_xml=_comments(records),
        extended_xml=_extended(ext),
    )
    commenters = tmp_path / ".claude-commenters.yaml"
    commenters.write_text(
        dedent(
            """\
            commenters:
              - match:
                  author: "Elena Rojas"
                role: lawyer
            default_role: unknown
            """
        ),
        encoding="utf-8",
    )
    cat = build_catalog(
        tmp_path, claude_identity="Claude", commenters_path=commenters
    )
    entry = cat["needs_reply"][0]
    assert entry["latest_author_role"] == "lawyer"
    # Role also lands on the per-comment record and thread metadata.
    assert cat["comments"][0]["role"] == "lawyer"
    assert cat["threads"][0]["last_author_role"] == "lawyer"


def test_catalog_missing_commenters_uses_default(three_thread_tree: Path) -> None:
    cat = build_catalog(
        three_thread_tree,
        claude_identity="Claude",
        commenters_path=three_thread_tree / ".claude-commenters.yaml",
    )
    for entry in cat["needs_reply"]:
        assert entry["latest_author_role"] == "unknown"
