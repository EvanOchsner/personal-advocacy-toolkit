"""Round-trip tests for docx_unpack.py and docx_pack.py.

Builds a synthetic .docx, unpacks it to a directory, repacks, and
asserts invariants:

- Disk-based unpack produces the expected files.
- pack() produces a valid zip whose members match the input tree.
- Two pack() runs of the same input produce byte-identical output.
- pack(..., original=ref) preserves member order from ref.
- load_members / save_members preserve member order in-memory.
"""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from scripts.publish.docx_pack import PackError, pack, save_members
from scripts.publish.docx_unpack import UnpackError, load_members, unpack


CONTENT_TYPES_XML = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
    b'<Override PartName="/word/document.xml" '
    b'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>\n'
    b"</Types>\n"
)

ROOT_RELS = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
    b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
    b'officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>\n'
    b"</Relationships>\n"
)

DOCUMENT_XML = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
    b"<w:body><w:p><w:r><w:t>hello</w:t></w:r></w:p></w:body>\n"
    b"</w:document>\n"
)


def _write_synthetic_docx(path: Path) -> None:
    # Deliberately write members in an unusual order so we can verify
    # that pack(--original) preserves it.
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", DOCUMENT_XML)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("[Content_Types].xml", CONTENT_TYPES_XML)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _member_names(docx: Path) -> list[str]:
    with zipfile.ZipFile(docx, "r") as z:
        return [i.filename for i in z.infolist()]


def test_unpack_creates_expected_tree(tmp_path: Path) -> None:
    src = tmp_path / "in.docx"
    _write_synthetic_docx(src)
    out = tmp_path / "unpacked"

    unpack(src, out)

    assert (out / "[Content_Types].xml").exists()
    assert (out / "_rels" / ".rels").exists()
    assert (out / "word" / "document.xml").exists()
    assert (out / "word" / "document.xml").read_bytes() == DOCUMENT_XML


def test_unpack_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(UnpackError):
        unpack(tmp_path / "nope.docx", tmp_path / "out")


def test_unpack_rejects_non_zip(tmp_path: Path) -> None:
    bogus = tmp_path / "not-a-zip.docx"
    bogus.write_text("plain text", encoding="utf-8")
    with pytest.raises(UnpackError):
        unpack(bogus, tmp_path / "out")


def test_unpack_refuses_path_traversal(tmp_path: Path) -> None:
    crafted = tmp_path / "evil.docx"
    with zipfile.ZipFile(crafted, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("../escaped.txt", b"pwn")
    with pytest.raises(UnpackError):
        unpack(crafted, tmp_path / "out")


def test_pack_round_trip(tmp_path: Path) -> None:
    src = tmp_path / "in.docx"
    _write_synthetic_docx(src)
    unpacked = tmp_path / "unpacked"
    unpack(src, unpacked)
    out = tmp_path / "out.docx"
    pack(unpacked, out)

    assert zipfile.is_zipfile(out)
    with zipfile.ZipFile(out, "r") as z:
        assert z.read("word/document.xml") == DOCUMENT_XML
        assert z.read("[Content_Types].xml") == CONTENT_TYPES_XML


def test_pack_is_byte_deterministic(tmp_path: Path) -> None:
    src = tmp_path / "in.docx"
    _write_synthetic_docx(src)
    unpacked = tmp_path / "unpacked"
    unpack(src, unpacked)

    out_a = tmp_path / "a.docx"
    out_b = tmp_path / "b.docx"
    pack(unpacked, out_a)
    pack(unpacked, out_b)

    assert _sha256(out_a) == _sha256(out_b)


def test_pack_matches_original_member_order(tmp_path: Path) -> None:
    src = tmp_path / "in.docx"
    _write_synthetic_docx(src)
    # src has order: word/document.xml, _rels/.rels, [Content_Types].xml
    original_order = _member_names(src)
    unpacked = tmp_path / "unpacked"
    unpack(src, unpacked)

    plain = tmp_path / "plain.docx"
    matched = tmp_path / "matched.docx"
    pack(unpacked, plain)
    pack(unpacked, matched, original=src)

    # Plain pack sorts lexicographically.
    assert _member_names(plain) == sorted(original_order)
    # Matched pack follows the original order.
    assert _member_names(matched) == original_order


def test_pack_rejects_empty_dir(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(PackError):
        pack(empty, tmp_path / "out.docx")


def test_pack_rejects_missing_original(tmp_path: Path) -> None:
    src = tmp_path / "in.docx"
    _write_synthetic_docx(src)
    unpacked = tmp_path / "unpacked"
    unpack(src, unpacked)
    with pytest.raises(PackError):
        pack(unpacked, tmp_path / "out.docx", original=tmp_path / "nope.docx")


def test_load_members_preserves_order(tmp_path: Path) -> None:
    src = tmp_path / "in.docx"
    _write_synthetic_docx(src)
    members = load_members(src)
    names = [info.filename for info, _ in members]
    assert names == _member_names(src)


def test_save_members_round_trip(tmp_path: Path) -> None:
    src = tmp_path / "in.docx"
    _write_synthetic_docx(src)
    members = load_members(src)
    out = tmp_path / "out.docx"
    save_members(out, members)
    assert _member_names(out) == _member_names(src)
    with zipfile.ZipFile(out, "r") as z:
        assert z.read("word/document.xml") == DOCUMENT_XML
