#!/usr/bin/env python3
"""Batch EXIF scrub over a directory of images.

Usage:
    python -m scripts.publish.exif_scrub --root images/ [--apply]

Strategy:
    Re-save each image through Pillow without the EXIF block. This also drops
    maker-notes, GPS, serial numbers, and any TIFF-style tags stuffed into
    the image. We re-save rather than surgically editing EXIF because a
    surgical edit leaves unknown tags the toolkit doesn't recognize.

Post-check (mandatory):
    After saving, re-open each output image and report any file that still
    has `_getexif()` data, GPS info, or a MakerNote tag. Returns non-zero
    exit code if any file fails the post-check.

Formats:
    JPEG, PNG, TIFF, HEIC (HEIC needs pillow-heif to be registered; we don't
    hard-require it — we skip HEIC files if not supported, and list them in
    the report).
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp"}
HEIC_SUFFIXES = {".heic", ".heif"}


@dataclass
class ScrubResult:
    path: Path
    scrubbed: bool
    survivors: list[str]  # reasons this file still has sensitive tags, empty if clean


def _load_pil():
    from PIL import Image  # type: ignore
    return Image


def scrub_image(path: Path, *, apply: bool) -> ScrubResult:
    Image = _load_pil()
    survivors: list[str] = []

    if path.suffix.lower() in HEIC_SUFFIXES:
        # Skip if pillow-heif not registered.
        try:
            with Image.open(path) as im:
                im.load()
        except Exception as e:
            return ScrubResult(path=path, scrubbed=False, survivors=[f"heic-unsupported: {e}"])

    if path.suffix.lower() not in (SUPPORTED_SUFFIXES | HEIC_SUFFIXES):
        return ScrubResult(path=path, scrubbed=False, survivors=[])

    if apply:
        with Image.open(path) as im:
            im.load()
            # Build a fresh image with no info dict.
            data = list(im.getdata())
            clean = Image.new(im.mode, im.size)
            clean.putdata(data)
            # Preserve format and mode; save without exif=.
            fmt = im.format or "JPEG"
            # tmp write + atomic replace.
            tmp = path.with_suffix(path.suffix + ".scrub.tmp")
            save_kwargs: dict = {}
            # Pillow treats `exif` kwarg as explicit; omitting it drops it.
            clean.save(tmp, format=fmt, **save_kwargs)
            tmp.replace(path)

    # Post-check.
    with Image.open(path) as im:
        exif = None
        try:
            exif = im._getexif()  # type: ignore[attr-defined]
        except Exception:
            exif = None
        info = dict(getattr(im, "info", {}) or {})

    if exif:
        survivors.append(f"exif-present: {len(exif)} tags")
    # Pillow stashes EXIF bytes in info['exif']
    if "exif" in info and info["exif"]:
        survivors.append(f"info-exif-blob: {len(info['exif'])} bytes")
    if "GPSInfo" in info:
        survivors.append("info-gps-present")
    # Some formats stash XMP under info['xmp'].
    if "xmp" in info and info["xmp"]:
        survivors.append(f"info-xmp-blob: {len(info['xmp'])} bytes")

    return ScrubResult(path=path, scrubbed=apply, survivors=survivors)


def scrub_tree(root: Path, *, apply: bool) -> list[ScrubResult]:
    results: list[ScrubResult] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in (SUPPORTED_SUFFIXES | HEIC_SUFFIXES):
            continue
        results.append(scrub_image(p, apply=apply))
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--apply", action="store_true", help="Actually rewrite files.")
    args = ap.parse_args(argv)

    try:
        _load_pil()
    except ImportError:
        print("Pillow is required (pip install Pillow).", file=sys.stderr)
        return 2

    results = scrub_tree(args.root, apply=args.apply)
    bad = [r for r in results if r.survivors]

    mode = "applied" if args.apply else "dry-run"
    print(f"{mode}: {len(results)} images scanned, {len(bad)} with surviving tags")
    for r in bad:
        print(f"  {r.path}: {', '.join(r.survivors)}", file=sys.stderr)

    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
