#!/usr/bin/env python3
"""Pack a directory into a .docx (Office Open XML zip package).

The inverse of `docx_unpack.py`. Zips the contents of a directory into
a .docx at the output path. Two modes:

    Plain pack: `docx_pack.py <dir>/ <out.docx>`
        Members are added in a deterministic sorted order. Timestamps
        are pinned so two pack runs of the same input produce
        byte-identical output.

    Matched pack: `docx_pack.py <dir>/ <out.docx> --original <ref.docx>`
        Members are emitted in the same order as --original's zip, with
        any new files appended at the end sorted lexicographically.
        Compression type and external_attr are copied from --original
        when the member exists there; new files use ZIP_DEFLATED.

Why matched pack: Word does not care about member order, but diff tools
do. Preserving order makes `unzip -l before.docx` vs `unzip -l
after.docx` a meaningful comparison.

Library API:

    pack(in_dir: Path, out: Path, *, original: Path | None = None) -> None
    save_members(path: Path, members: list[tuple[ZipInfo, bytes]]) -> None

Usage:

    python -m scripts.publish.docx_pack <input-dir>/ <output.docx>
    python -m scripts.publish.docx_pack <input-dir>/ <output.docx> \\
        --original <reference.docx>
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


class PackError(Exception):
    pass


# Pinned timestamp for byte-deterministic output. 1980-01-01 00:00:00 is
# the zip epoch; we use a slightly later value because zip rejects
# pre-1980 dates. Matches the typical "no timestamp" convention used by
# reproducible-build tooling.
_PINNED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def save_members(
    path: Path, members: list[tuple[zipfile.ZipInfo, bytes]]
) -> None:
    """Write members to path as a zip, preserving ZipInfo fields."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for info, data in members:
            new_info = zipfile.ZipInfo(
                filename=info.filename,
                date_time=info.date_time,
            )
            new_info.compress_type = info.compress_type
            new_info.external_attr = info.external_attr
            z.writestr(new_info, data)


def _walk_dir(in_dir: Path) -> list[tuple[str, bytes]]:
    """Return (arcname, bytes) for every file under in_dir, sorted."""
    entries: list[tuple[str, bytes]] = []
    for p in sorted(in_dir.rglob("*")):
        if p.is_dir():
            continue
        arcname = p.relative_to(in_dir).as_posix()
        entries.append((arcname, p.read_bytes()))
    return entries


def pack(in_dir: Path, out: Path, *, original: Path | None = None) -> None:
    """Zip in_dir's contents into out."""
    if not in_dir.exists() or not in_dir.is_dir():
        raise PackError(f"{in_dir} is not a directory")

    disk = dict(_walk_dir(in_dir))
    if not disk:
        raise PackError(f"{in_dir} is empty")

    if original is not None:
        if not original.exists():
            raise PackError(f"--original {original} does not exist")
        order: list[str] = []
        meta: dict[str, tuple[int, int]] = {}
        with zipfile.ZipFile(original, "r") as z:
            for info in z.infolist():
                if info.filename.endswith("/"):
                    continue
                order.append(info.filename)
                meta[info.filename] = (info.compress_type, info.external_attr)
        # Start with members in the original's order (only if present in
        # the disk tree). Append any new-to-disk files at the end, sorted.
        seen: set[str] = set()
        members: list[tuple[zipfile.ZipInfo, bytes]] = []
        for name in order:
            if name in disk:
                ct, attr = meta[name]
                info = zipfile.ZipInfo(
                    filename=name, date_time=_PINNED_TIMESTAMP
                )
                info.compress_type = ct
                info.external_attr = attr
                members.append((info, disk[name]))
                seen.add(name)
        for name in sorted(disk):
            if name in seen:
                continue
            info = zipfile.ZipInfo(
                filename=name, date_time=_PINNED_TIMESTAMP
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            members.append((info, disk[name]))
    else:
        members = []
        for name in sorted(disk):
            info = zipfile.ZipInfo(
                filename=name, date_time=_PINNED_TIMESTAMP
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            members.append((info, disk[name]))

    save_members(out, members)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("in_dir", type=Path, help="input directory")
    p.add_argument("out", type=Path, help="output .docx")
    p.add_argument(
        "--original",
        type=Path,
        default=None,
        help="reference .docx for member order and compression metadata",
    )
    args = p.parse_args(argv)
    try:
        pack(args.in_dir, args.out, original=args.original)
    except PackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"packed {args.in_dir}/ -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
