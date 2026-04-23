"""Tests for scripts.publish.docx_apply_replies.

Covers:
- Simple reply injection: new comment appears in word/comments.xml with
  correct paraIdParent linkage in word/commentsExtended.xml, plus
  range-start / range-end / reference markers nested inside the parent's
  in document.xml.
- Tracked-edit mode produces <w:ins> / <w:del> blocks.
- Silent-edit mode performs inline replacement.
- Downgrade path: guardrail failure demotes edit to prose comment and
  logs DOWNGRADE.
- Citation-footer guard: rejects replies that cite a file path without
  a Source: … sha256=…@… footer.
- Role-aware suffix for opposing-counsel commenters.
- Publication-sensitive-role detection helper.
"""
from __future__ import annotations

import re
from pathlib import Path
from textwrap import dedent

import pytest

from scripts.publish.docx_apply_replies import (
    ApplyError,
    apply_replies,
    publication_sensitive_roles,
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
W15 = "http://schemas.microsoft.com/office/word/2012/wordml"


def _document(paragraphs: list[tuple[str, list[int]]]) -> str:
    out = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
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
        out.append(
            f'<w15:commentEx w15:paraId="{pid}" w15:done="0"{parent_attr}/>'
        )
    out.append("</w15:commentsEx>")
    return "".join(out)


def _seed(tmp_path: Path, doc: str, comments: str, extended: str) -> Path:
    (tmp_path / "word").mkdir(parents=True, exist_ok=True)
    (tmp_path / "word" / "document.xml").write_text(doc, encoding="utf-8")
    (tmp_path / "word" / "comments.xml").write_text(comments, encoding="utf-8")
    (tmp_path / "word" / "commentsExtended.xml").write_text(
        extended, encoding="utf-8"
    )
    return tmp_path


def _one_thread_tree(tmp_path: Path, anchor_text: str = "the quick brown fox"):
    doc = _document([(anchor_text, [0])])
    comments = _comments(
        [
            {
                "id": 0,
                "para_id": "ROOT0001",
                "author": "Reviewer",
                "initials": "R",
                "date": "2026-04-20T10:00:00Z",
                "text": "F: verify",
            }
        ]
    )
    extended = _extended([("ROOT0001", "")])
    return _seed(tmp_path, doc, comments, extended)


def test_apply_reply_adds_comment_and_markers(tmp_path: Path) -> None:
    root = _one_thread_tree(tmp_path)
    stats = apply_replies(
        root,
        [{"thread_root_id": 0, "reply_text": "Confirmed."}],
        author="Claude",
        initials="C",
    )
    assert stats["applied"] == 1
    doc = (root / "word" / "document.xml").read_text(encoding="utf-8")
    comments = (root / "word" / "comments.xml").read_text(encoding="utf-8")
    extended = (root / "word" / "commentsExtended.xml").read_text(encoding="utf-8")

    # New comment exists with id=1 (max was 0).
    assert '<w:comment w:id="1"' in comments
    assert 'w:author="Claude"' in comments
    assert "Confirmed." in comments
    # Nested markers present in the document.
    assert '<w:commentRangeStart w:id="1"/>' in doc
    assert '<w:commentRangeEnd w:id="1"/>' in doc
    assert '<w:commentReference w:id="1"/>' in doc
    # commentsExtended links the new paraId to ROOT0001.
    assert 'w15:paraIdParent="ROOT0001"' in extended


def test_apply_tracked_edit(tmp_path: Path) -> None:
    root = _one_thread_tree(tmp_path, anchor_text="amount: $36,321.40 shown")
    stats = apply_replies(
        root,
        [
            {
                "thread_root_id": 0,
                "reply_text": "Discrepancy noted.",
                "edit_proposal": {"find": "$36,321.40", "replace": "$36,321.00"},
            }
        ],
        edit_mode="tracked",
    )
    assert stats["tracked"] == 1
    assert stats["downgrades"] == 0
    doc = (root / "word" / "document.xml").read_text(encoding="utf-8")
    assert "<w:del " in doc
    assert "<w:ins " in doc


def test_apply_silent_edit(tmp_path: Path) -> None:
    root = _one_thread_tree(tmp_path, anchor_text="amount: $36,321.40 shown")
    stats = apply_replies(
        root,
        [
            {
                "thread_root_id": 0,
                "reply_text": "Silent fix applied.",
                "edit_proposal": {"find": "$36,321.40", "replace": "$36,321.00"},
            }
        ],
        edit_mode="silent",
    )
    assert stats["silent"] == 1
    doc = (root / "word" / "document.xml").read_text(encoding="utf-8")
    assert "$36,321.00" in doc
    assert "$36,321.40" not in doc


def test_downgrade_on_guardrail_miss(tmp_path: Path, capsys) -> None:
    # Anchor has 'cat' twice → ambiguous find.
    root = _one_thread_tree(tmp_path, anchor_text="cat and cat")
    stats = apply_replies(
        root,
        [
            {
                "thread_root_id": 0,
                "reply_text": "Tighten this.",
                "edit_proposal": {"find": "cat", "replace": "dog"},
            }
        ],
        edit_mode="tracked",
    )
    assert stats["downgrades"] == 1
    assert stats["tracked"] == 0
    captured = capsys.readouterr()
    assert "DOWNGRADE" in captured.err
    # Downgraded comment body has the synthesized prefix.
    comments = (root / "word" / "comments.xml").read_text(encoding="utf-8")
    assert "Suggested edit:" in comments


def test_citation_footer_required_when_path_cited(tmp_path: Path) -> None:
    root = _one_thread_tree(tmp_path)
    with pytest.raises(ApplyError) as excinfo:
        apply_replies(
            root,
            [
                {
                    "thread_root_id": 0,
                    # Mentions a file path but no citation footer.
                    "reply_text": "See evidence/reports/foo.pdf for details.",
                }
            ],
        )
    assert "citation footer" in str(excinfo.value)


def test_citation_footer_accepted_when_present(tmp_path: Path) -> None:
    root = _one_thread_tree(tmp_path)
    reply = (
        "See evidence/reports/foo.pdf for details. "
        "Source: evidence/reports/foo.pdf:3  "
        "sha256=" + "0" * 64 + "@git:abcd1234"
    )
    stats = apply_replies(
        root,
        [{"thread_root_id": 0, "reply_text": reply}],
    )
    assert stats["applied"] == 1


def test_opposing_counsel_role_suffix(tmp_path: Path) -> None:
    root = _one_thread_tree(tmp_path)
    commenters = root / ".claude-commenters.yaml"
    commenters.write_text(
        dedent(
            """\
            commenters:
              - match:
                  author: "Reviewer"
                role: opposing-counsel
            default_role: unknown
            """
        ),
        encoding="utf-8",
    )
    apply_replies(
        root,
        [{"thread_root_id": 0, "reply_text": "Confirmed."}],
        commenters_path=commenters,
    )
    comments = (root / "word" / "comments.xml").read_text(encoding="utf-8")
    assert "[risk: check with counsel before sending]" in comments


def test_publication_sensitive_roles_detection(tmp_path: Path) -> None:
    root = _one_thread_tree(tmp_path)
    commenters = root / ".claude-commenters.yaml"
    commenters.write_text(
        dedent(
            """\
            commenters:
              - match:
                  author: "Reviewer"
                role: lawyer
            default_role: unknown
            """
        ),
        encoding="utf-8",
    )
    sensitive = publication_sensitive_roles(root, commenters, "Claude")
    assert "lawyer" in sensitive
