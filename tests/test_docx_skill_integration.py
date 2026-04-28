"""End-to-end integration test for the docx-comment-roundtrip skill.

The LLM driver itself (subagent dispatch) isn't exercised here — that
is out of scope for a deterministic unit test. Instead we run the
data-path end-to-end with stubbed specialist output:

    unpack → catalog → (mocked router+specialist results) → apply → pack → verify

Scenarios covered:

- 5 threads mirror the real MIA use case: one `F:`, one `Q:`, one
  `A:`, one `F+A:`, one untagged with role=lawyer.
- Catalog correctly classifies all five.
- Applied .docx has +5 new Claude comments (one per thread).
- Round-trip: unpacked + re-packed + re-catalog'd = same count.
- Citation-footer post-check passes.
- Opposing-counsel thread carries the risk-flag suffix.
"""
from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from scripts.publish.docx_apply_replies import apply_replies
from scripts.publish.docx_catalog import build_catalog
from scripts.publish.docx_pack import pack
from scripts.publish.docx_unpack import unpack


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
W15 = "http://schemas.microsoft.com/office/word/2012/wordml"


def _build_five_thread_docx(tmp_path: Path) -> Path:
    """Build a synthetic .docx that mirrors the skill's target workload."""
    import zipfile

    doc_body = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<w:document xmlns:w="{W_NS}"><w:body>',
        # Thread 0: F: verify $58,000 figure
        '<w:p><w:commentRangeStart w:id="0"/>'
        '<w:r><w:t>Total loss damages: $58,000 claimed.</w:t></w:r>'
        '<w:commentRangeEnd w:id="0"/>'
        '<w:r><w:commentReference w:id="0"/></w:r></w:p>',
        # Thread 1: Q: does MD prompt-pay statute apply
        '<w:p><w:commentRangeStart w:id="1"/>'
        '<w:r><w:t>Maryland prompt-pay statute cited as authority.</w:t></w:r>'
        '<w:commentRangeEnd w:id="1"/>'
        '<w:r><w:commentReference w:id="1"/></w:r></w:p>',
        # Thread 2: A: salvage-transfer grievance framing
        '<w:p><w:commentRangeStart w:id="2"/>'
        '<w:r><w:t>Salvage transfer grievance as framed.</w:t></w:r>'
        '<w:commentRangeEnd w:id="2"/>'
        '<w:r><w:commentReference w:id="2"/></w:r></w:p>',
        # Thread 3: F+A: mixed — verify and analyze
        '<w:p><w:commentRangeStart w:id="3"/>'
        '<w:r><w:t>Policy expiration date on page 3.</w:t></w:r>'
        '<w:commentRangeEnd w:id="3"/>'
        '<w:r><w:commentReference w:id="3"/></w:r></w:p>',
        # Thread 4: untagged — lawyer commenter
        '<w:p><w:commentRangeStart w:id="4"/>'
        '<w:r><w:t>Opening paragraph framing.</w:t></w:r>'
        '<w:commentRangeEnd w:id="4"/>'
        '<w:r><w:commentReference w:id="4"/></w:r></w:p>',
        '</w:body></w:document>',
    ]
    document_xml = "".join(doc_body)

    comments = [
        {"id": 0, "para_id": "T0", "author": "Sally Ridesdale", "initials": "SR",
         "date": "2026-04-22T10:00:00Z",
         "text": "F: verify the $58,000 figure against the valuation report"},
        {"id": 1, "para_id": "T1", "author": "Sally Ridesdale", "initials": "SR",
         "date": "2026-04-22T10:05:00Z",
         "text": "Q: does MD's prompt-pay statute actually apply here?"},
        {"id": 2, "para_id": "T2", "author": "Sally Ridesdale", "initials": "SR",
         "date": "2026-04-22T10:10:00Z",
         "text": "A: is the salvage-transfer grievance framed strongly?"},
        {"id": 3, "para_id": "T3", "author": "Sally Ridesdale", "initials": "SR",
         "date": "2026-04-22T10:15:00Z",
         "text": "F+A: verify policy expiration and assess implication"},
        {"id": 4, "para_id": "T4", "author": "Elena Rojas", "initials": "ER",
         "date": "2026-04-22T10:20:00Z",
         "text": "Consider reframing the opening."},
    ]

    comments_xml_parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<w:comments xmlns:w="{W_NS}" xmlns:w14="{W14}">',
    ]
    for r in comments:
        comments_xml_parts.append(
            f'<w:comment w:id="{r["id"]}" w:author="{r["author"]}" '
            f'w:initials="{r["initials"]}" w:date="{r["date"]}">'
            f'<w:p w14:paraId="{r["para_id"]}">'
            f'<w:r><w:t>{r["text"]}</w:t></w:r>'
            f'</w:p></w:comment>'
        )
    comments_xml_parts.append("</w:comments>")
    comments_xml = "".join(comments_xml_parts)

    extended_xml_parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<w15:commentsEx xmlns:w15="{W15}">',
    ]
    for r in comments:
        extended_xml_parts.append(
            f'<w15:commentEx w15:paraId="{r["para_id"]}" w15:done="0"/>'
        )
    extended_xml_parts.append("</w15:commentsEx>")
    extended_xml = "".join(extended_xml_parts)

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/comments.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>'
        '</Types>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>'
    )
    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdComments" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" '
        'Target="comments.xml"/>'
        '</Relationships>'
    )

    docx = tmp_path / "mia.docx"
    with zipfile.ZipFile(docx, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("word/document.xml", document_xml)
        z.writestr("word/comments.xml", comments_xml)
        z.writestr("word/commentsExtended.xml", extended_xml)
    return docx


@pytest.fixture
def mia_commenters(tmp_path: Path) -> Path:
    path = tmp_path / ".claude-commenters.yaml"
    path.write_text(
        dedent(
            """\
            commenters:
              - match:
                  author: "Sally Ridesdale"
                role: complainant
              - match:
                  author: "Elena Rojas"
                role: lawyer
              - match:
                  author: "Claude"
                role: self
            default_role: unknown
            """
        ),
        encoding="utf-8",
    )
    return path


def test_full_pipeline_five_threads(tmp_path: Path, mia_commenters: Path) -> None:
    docx = _build_five_thread_docx(tmp_path)
    unpacked = tmp_path / "unpacked"
    unpack(docx, unpacked)

    # Phase 1: catalog.
    catalog = build_catalog(
        unpacked,
        claude_identity="Claude",
        commenters_path=mia_commenters,
    )
    assert catalog["threads_total"] == 5
    assert catalog["threads_needing_reply"] == 5
    tags = {e["thread_root_id"]: e["tag"] for e in catalog["needs_reply"]}
    assert tags[0] == "F"
    assert tags[1] == "Q"
    assert tags[2] == "A"
    assert tags[3] == "F+A"
    assert tags[4] == ""  # untagged (lawyer)

    roles = {e["thread_root_id"]: e["latest_author_role"]
             for e in catalog["needs_reply"]}
    assert roles[4] == "lawyer"
    assert roles[0] == "complainant"

    # Phase 2–4 (mocked): stub specialist output.
    replies = [
        {
            "thread_root_id": 0,
            "reply_text": "Confirmed. $58,000 is consistent with the valuation.",
        },
        {
            "thread_root_id": 1,
            "reply_text": "MD prompt-pay statute applies to first-party claims.",
        },
        {
            "thread_root_id": 2,
            "reply_text": "The framing is strong; consider adding a concrete date.",
        },
        {
            "thread_root_id": 3,
            "reply_text": "Policy expiration confirmed; implication is procedural.",
        },
        {
            "thread_root_id": 4,
            "reply_text": "Tighter opening: lead with the factual deadline violation.",
        },
    ]
    replies_path = tmp_path / "replies.json"
    replies_path.write_text(json.dumps(replies), encoding="utf-8")

    # Phase 5: apply.
    stats = apply_replies(
        unpacked,
        replies,
        author="Claude",
        initials="C",
        commenters_path=mia_commenters,
    )
    assert stats["applied"] == 5
    assert stats["downgrades"] == 0
    assert stats["failures"] == 0

    # Pack, re-unpack, re-catalog.
    out_docx = tmp_path / "mia-out.docx"
    pack(unpacked, out_docx, original=docx)

    verify_dir = tmp_path / "verify"
    unpack(out_docx, verify_dir)
    verify_cat = build_catalog(
        verify_dir,
        claude_identity="Claude",
        commenters_path=mia_commenters,
    )

    # Phase 6 assertions.
    # 1. Total comments = 5 originals + 5 replies = 10.
    assert len(verify_cat["comments"]) == 10
    claude_comments = [
        c for c in verify_cat["comments"] if c["author"] == "Claude"
    ]
    assert len(claude_comments) == 5
    # 2. Every Claude reply has a paraIdParent set.
    for c in claude_comments:
        assert c["para_id_parent"], c
    # 3. Balanced markers in document.xml.
    doc = (verify_dir / "word" / "document.xml").read_text(encoding="utf-8")
    assert doc.count("<w:commentRangeStart") == 10
    assert doc.count("<w:commentRangeEnd") == 10
    assert doc.count("<w:commentReference") == 10
    # 4. All 5 threads are now current with a Claude reply — nothing to do.
    assert verify_cat["threads_needing_reply"] == 0


def test_opposing_counsel_risk_flag_round_trips(
    tmp_path: Path, mia_commenters: Path
) -> None:
    # Swap the lawyer role for opposing-counsel on author "Elena Rojas"
    # to exercise the risk-flag suffix.
    mia_commenters.write_text(
        dedent(
            """\
            commenters:
              - match:
                  author: "Elena Rojas"
                role: opposing-counsel
              - match:
                  author: "Sally Ridesdale"
                role: complainant
            default_role: unknown
            """
        ),
        encoding="utf-8",
    )
    docx = _build_five_thread_docx(tmp_path)
    unpacked = tmp_path / "unpacked"
    unpack(docx, unpacked)
    replies = [
        {"thread_root_id": 4, "reply_text": "Literal answer only."},
    ]
    apply_replies(
        unpacked,
        replies,
        author="Claude",
        initials="C",
        commenters_path=mia_commenters,
    )
    comments = (unpacked / "word" / "comments.xml").read_text(encoding="utf-8")
    assert "[risk: check with counsel before sending]" in comments
