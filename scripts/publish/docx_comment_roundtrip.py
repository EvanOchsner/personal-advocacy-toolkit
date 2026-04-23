#!/usr/bin/env python3
"""Extract / re-inject Word comments for a .docx without altering body content.

A .docx is a ZIP of XML parts. Comments live in:

    word/comments.xml          — <w:comments><w:comment w:id="N" .../>
    word/commentsExtended.xml  — optional, newer Word versions
    word/commentsIds.xml       — optional, newer Word versions
    word/commentsExtensible.xml — optional, very new Word versions
    word/_rels/document.xml.rels — relationship entry for comments part
    [Content_Types].xml        — content-type override for comments part
    word/document.xml          — anchor elements: <w:commentRangeStart/End>
                                 and <w:commentReference>

Two modes:

    --extract  .docx -> sidecar (YAML) AND produces a stripped .docx
               where comments.xml (+ friends) is removed and the anchor
               elements in document.xml are deleted. Body text runs are
               preserved; only the comment markup is removed.

    --inject   sidecar + stripped .docx -> .docx with comments restored.
               Round-trips the comment IDs, authors, timestamps, and
               body text exactly. Anchor positions are inserted at the
               locations recorded in the sidecar.

This is deliberately conservative: we only touch the comment parts and
the anchor elements. Other parts of the zip are copied byte-for-byte
(same member order, same compression) so diffs remain meaningful.

Usage:
    # Strip comments from a .docx going to a counterparty; keep sidecar
    # so we can restore them to the author's working copy later.
    uv run python -m scripts.publish.docx_comment_roundtrip \\
        --extract \\
        --in draft-with-comments.docx \\
        --out draft-clean.docx \\
        --sidecar comments-sidecar.yaml

    # Restore comments back onto the stripped copy.
    uv run python -m scripts.publish.docx_comment_roundtrip \\
        --inject \\
        --in draft-clean.docx \\
        --sidecar comments-sidecar.yaml \\
        --out draft-with-comments.docx
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import yaml

from scripts.publish.docx_pack import save_members as _write_all
from scripts.publish.docx_unpack import load_members as _read_all


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

COMMENTS_PART = "word/comments.xml"
EXTRA_COMMENT_PARTS = (
    "word/commentsExtended.xml",
    "word/commentsIds.xml",
    "word/commentsExtensible.xml",
)
DOCUMENT_PART = "word/document.xml"
DOCUMENT_RELS_PART = "word/_rels/document.xml.rels"
CT_PART = "[Content_Types].xml"

COMMENTS_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
)
COMMENTS_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
)

ET.register_namespace("w", W_NS)
ET.register_namespace("r", R_NS)


def _tag(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


class RoundTripError(Exception):
    pass


# ---------------------------------------------------------------------------
# Comment parsing / serialization


def _parse_comments_xml(data: bytes) -> list[dict[str, Any]]:
    """Return a list of comment records preserving the raw XML for the body."""
    root = ET.fromstring(data)
    comments: list[dict[str, Any]] = []
    for c in root.findall(_tag(W_NS, "comment")):
        rec = {
            "id": c.attrib.get(_tag(W_NS, "id")),
            "author": c.attrib.get(_tag(W_NS, "author"), ""),
            "initials": c.attrib.get(_tag(W_NS, "initials"), ""),
            "date": c.attrib.get(_tag(W_NS, "date"), ""),
            # Keep the full child XML — this preserves <w:p>/<w:r>/<w:t>
            # structure so a round-trip restores formatting byte-for-byte
            # within the comment body.
            "body_xml": "".join(
                ET.tostring(child, encoding="unicode") for child in list(c)
            ),
        }
        comments.append(rec)
    return comments


def _build_comments_xml(comments: list[dict[str, Any]]) -> bytes:
    root = ET.Element(_tag(W_NS, "comments"))
    for rec in comments:
        c = ET.SubElement(root, _tag(W_NS, "comment"))
        c.set(_tag(W_NS, "id"), str(rec["id"]))
        if rec.get("author"):
            c.set(_tag(W_NS, "author"), rec["author"])
        if rec.get("initials"):
            c.set(_tag(W_NS, "initials"), rec["initials"])
        if rec.get("date"):
            c.set(_tag(W_NS, "date"), rec["date"])
        body = rec.get("body_xml", "")
        if body:
            # Wrap so we can parse as a fragment.
            frag = ET.fromstring(f'<wrap xmlns:w="{W_NS}">{body}</wrap>')
            for child in list(frag):
                c.append(child)
    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml


# ---------------------------------------------------------------------------
# document.xml surgery — anchors


def _strip_anchors(document_bytes: bytes) -> tuple[bytes, list[dict[str, Any]]]:
    """Remove <w:commentRangeStart/End/> and <w:commentReference/>.

    Returns (new_document_bytes, anchors). `anchors` is a list of
    records, in document order, that lets us re-insert the anchors at
    the same positions when injecting.
    """
    root = ET.fromstring(document_bytes)
    anchors: list[dict[str, Any]] = []
    # Walk every parent so we know where to delete from. We use a pre-order
    # traversal storing a trail of (parent, index) pairs for each anchor.
    _walk_and_strip(root, anchors, position_counter=[0])
    new_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return new_xml, anchors


def _walk_and_strip(
    parent: ET.Element,
    anchors: list[dict[str, Any]],
    position_counter: list[int],
    path: tuple[int, ...] = (),
) -> None:
    """Recursive walker that removes anchor elements and records their
    position via a path-tuple (sequence of child indices from the root).
    """
    anchor_tags = {
        _tag(W_NS, "commentRangeStart"),
        _tag(W_NS, "commentRangeEnd"),
        _tag(W_NS, "commentReference"),
    }
    # Iterate in reverse so we can delete without shifting indices for
    # elements we have not visited yet in this loop.
    new_children = []
    for idx, child in enumerate(list(parent)):
        if child.tag in anchor_tags:
            kind = child.tag.rsplit("}", 1)[-1]  # commentRangeStart/End/Reference
            anchors.append(
                {
                    "kind": kind,
                    "comment_id": child.attrib.get(_tag(W_NS, "id")),
                    "path": list(path) + [len(new_children)],
                    "order": position_counter[0],
                }
            )
            position_counter[0] += 1
            # Skip (do not append): effectively removes the anchor.
            continue
        new_children.append(child)
    # Reset parent children to the filtered list.
    for c in list(parent):
        parent.remove(c)
    for c in new_children:
        parent.append(c)
    # Recurse into the kept children.
    for i, c in enumerate(list(parent)):
        _walk_and_strip(c, anchors, position_counter, path + (i,))


def _reinsert_anchors(
    document_bytes: bytes, anchors: list[dict[str, Any]]
) -> bytes:
    root = ET.fromstring(document_bytes)
    # Insert in original document order so indices line up.
    for rec in sorted(anchors, key=lambda r: r["order"]):
        path = rec["path"]
        parent = root
        for step in path[:-1]:
            parent = list(parent)[step]
        el = ET.Element(_tag(W_NS, rec["kind"]))
        if rec.get("comment_id") is not None:
            el.set(_tag(W_NS, "id"), str(rec["comment_id"]))
        insert_idx = path[-1]
        # Clamp to valid range.
        insert_idx = max(0, min(insert_idx, len(list(parent))))
        parent.insert(insert_idx, el)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


# ---------------------------------------------------------------------------
# [Content_Types].xml and rels surgery


def _has_override(ct_bytes: bytes, part_name: str) -> bool:
    root = ET.fromstring(ct_bytes)
    target = f"/{part_name}" if not part_name.startswith("/") else part_name
    for ov in root.findall(_tag(CT_NS, "Override")):
        if ov.attrib.get("PartName") == target:
            return True
    return False


def _ensure_override(ct_bytes: bytes, part_name: str, content_type: str) -> bytes:
    if _has_override(ct_bytes, part_name):
        return ct_bytes
    root = ET.fromstring(ct_bytes)
    ov = ET.SubElement(root, _tag(CT_NS, "Override"))
    ov.set("PartName", f"/{part_name}")
    ov.set("ContentType", content_type)
    ET.register_namespace("", CT_NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _remove_override(ct_bytes: bytes, part_name: str) -> bytes:
    root = ET.fromstring(ct_bytes)
    target = f"/{part_name}"
    for ov in list(root.findall(_tag(CT_NS, "Override"))):
        if ov.attrib.get("PartName") == target:
            root.remove(ov)
    ET.register_namespace("", CT_NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _has_comments_rel(rels_bytes: bytes) -> bool:
    root = ET.fromstring(rels_bytes)
    for r in root.findall(_tag(PKG_REL_NS, "Relationship")):
        if r.attrib.get("Type") == COMMENTS_REL_TYPE:
            return True
    return False


def _ensure_comments_rel(rels_bytes: bytes) -> bytes:
    root = ET.fromstring(rels_bytes)
    if _has_comments_rel(rels_bytes):
        return rels_bytes
    existing_ids: set[str] = {
        r.attrib.get("Id", "")
        for r in root.findall(_tag(PKG_REL_NS, "Relationship"))
    }
    new_id = "rIdComments"
    i = 1
    while new_id in existing_ids:
        new_id = f"rIdComments{i}"
        i += 1
    r = ET.SubElement(root, _tag(PKG_REL_NS, "Relationship"))
    r.set("Id", new_id)
    r.set("Type", COMMENTS_REL_TYPE)
    r.set("Target", "comments.xml")
    ET.register_namespace("", PKG_REL_NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _remove_comments_rel(rels_bytes: bytes) -> bytes:
    root = ET.fromstring(rels_bytes)
    for r in list(root.findall(_tag(PKG_REL_NS, "Relationship"))):
        if r.attrib.get("Type") == COMMENTS_REL_TYPE:
            root.remove(r)
    ET.register_namespace("", PKG_REL_NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


# ---------------------------------------------------------------------------
# Public API: extract / inject


def extract(in_docx: Path, out_docx: Path, sidecar_path: Path) -> dict[str, Any]:
    members = _read_all(in_docx)
    by_name = {info.filename: (i, data) for i, (info, data) in enumerate(members)}

    if COMMENTS_PART not in by_name:
        raise RoundTripError(
            f"{in_docx} has no {COMMENTS_PART}; nothing to extract."
        )

    comments = _parse_comments_xml(by_name[COMMENTS_PART][1])

    doc_idx, doc_bytes = by_name[DOCUMENT_PART]
    new_doc_bytes, anchors = _strip_anchors(doc_bytes)

    rels_idx, rels_bytes = by_name[DOCUMENT_RELS_PART]
    new_rels_bytes = _remove_comments_rel(rels_bytes)

    ct_idx, ct_bytes = by_name[CT_PART]
    new_ct_bytes = _remove_override(ct_bytes, COMMENTS_PART)
    for extra in EXTRA_COMMENT_PARTS:
        new_ct_bytes = _remove_override(new_ct_bytes, extra)

    # Rebuild members list, skipping the comments parts entirely.
    drop = {COMMENTS_PART, *EXTRA_COMMENT_PARTS}
    new_members: list[tuple[zipfile.ZipInfo, bytes]] = []
    for info, data in members:
        if info.filename in drop:
            continue
        if info.filename == DOCUMENT_PART:
            new_members.append((info, new_doc_bytes))
        elif info.filename == DOCUMENT_RELS_PART:
            new_members.append((info, new_rels_bytes))
        elif info.filename == CT_PART:
            new_members.append((info, new_ct_bytes))
        else:
            new_members.append((info, data))

    _write_all(out_docx, new_members)

    sidecar = {
        "schema_version": "1.0",
        "source_docx": in_docx.name,
        "comments": comments,
        "anchors": anchors,
    }
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    with sidecar_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(sidecar, fh, sort_keys=False, allow_unicode=True)

    return sidecar


def inject(stripped_docx: Path, sidecar_path: Path, out_docx: Path) -> None:
    with sidecar_path.open("r", encoding="utf-8") as fh:
        sidecar = yaml.safe_load(fh) or {}
    comments = sidecar.get("comments") or []
    anchors = sidecar.get("anchors") or []
    if not comments:
        raise RoundTripError(
            f"{sidecar_path} has no comments to inject."
        )

    members = _read_all(stripped_docx)
    by_name = {info.filename: (i, data) for i, (info, data) in enumerate(members)}

    doc_idx, doc_bytes = by_name[DOCUMENT_PART]
    new_doc_bytes = _reinsert_anchors(doc_bytes, anchors)

    rels_idx, rels_bytes = by_name[DOCUMENT_RELS_PART]
    new_rels_bytes = _ensure_comments_rel(rels_bytes)

    ct_idx, ct_bytes = by_name[CT_PART]
    new_ct_bytes = _ensure_override(ct_bytes, COMMENTS_PART, COMMENTS_CONTENT_TYPE)

    new_comments_bytes = _build_comments_xml(comments)

    new_members: list[tuple[zipfile.ZipInfo, bytes]] = []
    replaced: set[str] = set()
    for info, data in members:
        if info.filename == DOCUMENT_PART:
            new_members.append((info, new_doc_bytes))
            replaced.add(DOCUMENT_PART)
        elif info.filename == DOCUMENT_RELS_PART:
            new_members.append((info, new_rels_bytes))
            replaced.add(DOCUMENT_RELS_PART)
        elif info.filename == CT_PART:
            new_members.append((info, new_ct_bytes))
            replaced.add(CT_PART)
        else:
            new_members.append((info, data))

    # Append the comments part.
    comments_info = zipfile.ZipInfo(filename=COMMENTS_PART)
    comments_info.compress_type = zipfile.ZIP_DEFLATED
    new_members.append((comments_info, new_comments_bytes))

    _write_all(out_docx, new_members)


# ---------------------------------------------------------------------------
# CLI


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--extract", action="store_true")
    mode.add_argument("--inject", action="store_true")
    p.add_argument("--in", dest="in_path", type=Path, required=True)
    p.add_argument("--out", dest="out_path", type=Path, required=True)
    p.add_argument("--sidecar", type=Path, required=True)
    args = p.parse_args(argv)

    try:
        if args.extract:
            extract(args.in_path, args.out_path, args.sidecar)
            print(f"extracted comments -> {args.sidecar}; stripped .docx -> {args.out_path}")
        else:
            inject(args.in_path, args.sidecar, args.out_path)
            print(f"injected comments from {args.sidecar} -> {args.out_path}")
    except RoundTripError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
