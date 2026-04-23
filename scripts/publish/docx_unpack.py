#!/usr/bin/env python3
"""Unpack a .docx (Office Open XML zip package) into a directory.

A .docx is just a ZIP of XML parts plus some media. This script unzips
one into a directory, preserving file layout:

    word/document.xml
    word/comments.xml
    word/commentsExtended.xml
    word/_rels/document.xml.rels
    [Content_Types].xml
    ...

The directory form is what the rest of the `docx_*` family of scripts
(docx_catalog, docx_apply_replies, docx_edit_ops) operates on. Pack the
directory back into a .docx with `docx_pack.py`.

Library API:

    unpack(docx_path: Path, out_dir: Path) -> None
        Disk-based: unzip every member to out_dir/, preserving relative
        paths. out_dir is created if it doesn't exist.

    load_members(docx_path: Path) -> list[tuple[ZipInfo, bytes]]
        In-memory: read every member in original zip order. Useful when
        you need to manipulate members without round-tripping through
        disk (see scripts/publish/docx_comment_roundtrip.py).

Usage:

    uv run python -m scripts.publish.docx_unpack <input.docx> <output-dir>/
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


class UnpackError(Exception):
    pass


def load_members(docx_path: Path) -> list[tuple[zipfile.ZipInfo, bytes]]:
    """Read every member of the zip into memory in original order."""
    if not docx_path.exists():
        raise UnpackError(f"{docx_path} does not exist")
    if not zipfile.is_zipfile(docx_path):
        raise UnpackError(f"{docx_path} is not a valid zip file")
    members: list[tuple[zipfile.ZipInfo, bytes]] = []
    with zipfile.ZipFile(docx_path, "r") as z:
        for info in z.infolist():
            members.append((info, z.read(info.filename)))
    return members


def unpack(docx_path: Path, out_dir: Path) -> None:
    """Extract every member of docx_path into out_dir/, preserving layout."""
    members = load_members(docx_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    for info, data in members:
        # Skip directory entries; we create directories on demand below.
        if info.filename.endswith("/"):
            continue
        target = out_dir / info.filename
        # Refuse to write outside out_dir (defensive against crafted zips
        # with ../ or absolute paths in member names).
        try:
            target.resolve().relative_to(out_dir.resolve())
        except ValueError as exc:
            raise UnpackError(
                f"refusing to write {info.filename!r} outside {out_dir}"
            ) from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("docx", type=Path, help="input .docx file")
    p.add_argument("out_dir", type=Path, help="output directory")
    args = p.parse_args(argv)
    try:
        unpack(args.docx, args.out_dir)
    except UnpackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"unpacked {args.docx} -> {args.out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
