"""Round-trip test for scripts/publish/docx_comment_roundtrip.py.

Synthesizes a minimal .docx with two comments, extracts and re-injects,
and asserts round-trip invariants.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from scripts.publish.docx_comment_roundtrip import (
    COMMENTS_PART,
    DOCUMENT_PART,
    RoundTripError,
    extract,
    inject,
)


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


CONTENT_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
</Types>
"""

ROOT_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""

DOCUMENT_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdComments" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" Target="comments.xml"/>
</Relationships>
"""

DOCUMENT_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:commentRangeStart w:id="0"/>
      <w:r><w:t>First paragraph with a comment.</w:t></w:r>
      <w:commentRangeEnd w:id="0"/>
      <w:r><w:commentReference w:id="0"/></w:r>
    </w:p>
    <w:p>
      <w:commentRangeStart w:id="1"/>
      <w:r><w:t>Second paragraph also with a comment.</w:t></w:r>
      <w:commentRangeEnd w:id="1"/>
      <w:r><w:commentReference w:id="1"/></w:r>
    </w:p>
  </w:body>
</w:document>
"""

COMMENTS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:comment w:id="0" w:author="Reviewer A" w:initials="RA" w:date="2026-04-22T10:00:00Z">
    <w:p><w:r><w:t>first review comment</w:t></w:r></w:p>
  </w:comment>
  <w:comment w:id="1" w:author="Reviewer B" w:initials="RB" w:date="2026-04-22T10:05:00Z">
    <w:p><w:r><w:t>second review comment</w:t></w:r></w:p>
  </w:comment>
</w:comments>
"""


def _write_synthetic_docx(path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        z.writestr("_rels/.rels", ROOT_RELS_XML)
        z.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS_XML)
        z.writestr("word/document.xml", DOCUMENT_XML)
        z.writestr("word/comments.xml", COMMENTS_XML)


def _zip_members(path: Path) -> list[str]:
    with zipfile.ZipFile(path, "r") as z:
        return z.namelist()


def _zip_read(path: Path, name: str) -> bytes:
    with zipfile.ZipFile(path, "r") as z:
        return z.read(name)


def _body_text(document_xml_bytes: bytes) -> list[str]:
    root = ET.fromstring(document_xml_bytes)
    return [
        t.text or ""
        for t in root.iter(f"{{{W_NS}}}t")
    ]


def _anchor_count(document_xml_bytes: bytes) -> int:
    root = ET.fromstring(document_xml_bytes)
    n = 0
    for tag in ("commentRangeStart", "commentRangeEnd", "commentReference"):
        n += len(list(root.iter(f"{{{W_NS}}}{tag}")))
    return n


def test_extract_strips_comments_and_anchors(tmp_path: Path):
    in_docx = tmp_path / "in.docx"
    out_docx = tmp_path / "out-clean.docx"
    sidecar = tmp_path / "sidecar.yaml"
    _write_synthetic_docx(in_docx)

    extract(in_docx, out_docx, sidecar)

    members = _zip_members(out_docx)
    assert COMMENTS_PART not in members, members

    ct = _zip_read(out_docx, "[Content_Types].xml").decode("utf-8")
    assert "comments.xml" not in ct

    rels = _zip_read(out_docx, "word/_rels/document.xml.rels").decode("utf-8")
    assert "comments" not in rels.lower() or "relationships/comments" not in rels

    doc = _zip_read(out_docx, DOCUMENT_PART)
    assert _anchor_count(doc) == 0
    # Body text runs survive.
    texts = _body_text(doc)
    assert "First paragraph with a comment." in texts
    assert "Second paragraph also with a comment." in texts

    # Sidecar carries both comments.
    assert sidecar.exists()
    text = sidecar.read_text(encoding="utf-8")
    assert "Reviewer A" in text
    assert "Reviewer B" in text
    assert "first review comment" in text
    assert "second review comment" in text


def test_round_trip_restores_comments_and_anchors(tmp_path: Path):
    in_docx = tmp_path / "in.docx"
    stripped = tmp_path / "stripped.docx"
    sidecar = tmp_path / "sidecar.yaml"
    restored = tmp_path / "restored.docx"

    _write_synthetic_docx(in_docx)
    extract(in_docx, stripped, sidecar)
    inject(stripped, sidecar, restored)

    members = _zip_members(restored)
    assert COMMENTS_PART in members

    # Content-Types override restored.
    ct = _zip_read(restored, "[Content_Types].xml").decode("utf-8")
    assert "/word/comments.xml" in ct

    # Relationship restored.
    rels = _zip_read(restored, "word/_rels/document.xml.rels").decode("utf-8")
    assert "relationships/comments" in rels

    # Anchor elements restored.
    doc = _zip_read(restored, DOCUMENT_PART)
    assert _anchor_count(doc) == 6  # 3 anchors per comment, 2 comments

    # Body text preserved.
    texts = _body_text(doc)
    assert "First paragraph with a comment." in texts
    assert "Second paragraph also with a comment." in texts

    # Comments body preserved (author + body text).
    comments = _zip_read(restored, COMMENTS_PART).decode("utf-8")
    assert "Reviewer A" in comments
    assert "Reviewer B" in comments
    assert "first review comment" in comments
    assert "second review comment" in comments


def test_extract_errors_when_no_comments(tmp_path: Path):
    in_docx = tmp_path / "no-comments.docx"
    # Build a docx without comments part.
    with zipfile.ZipFile(in_docx, "w", compression=zipfile.ZIP_DEFLATED) as z:
        ct_no_comments = CONTENT_TYPES_XML.replace(
            '<Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>',
            "",
        )
        rels_no_comments = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>
"""
        doc_no_anchors = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>plain</w:t></w:r></w:p></w:body>
</w:document>
"""
        z.writestr("[Content_Types].xml", ct_no_comments)
        z.writestr("_rels/.rels", ROOT_RELS_XML)
        z.writestr("word/_rels/document.xml.rels", rels_no_comments)
        z.writestr("word/document.xml", doc_no_anchors)

    with pytest.raises(RoundTripError):
        extract(in_docx, tmp_path / "out.docx", tmp_path / "sidecar.yaml")
