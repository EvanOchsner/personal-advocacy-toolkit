#!/usr/bin/env python3
"""Validate a packet-manifest.yaml — schema + on-disk integrity.

Layered on top of ``scripts.packet._manifest.load_manifest``:

- **Schema**: the loader already raises ManifestError on shape problems
  (missing keys, bad names, missing source+sources, etc.). We surface
  those as schema errors.
- **Integrity**: every exhibit source path exists on disk. If a SHA-256
  line manifest is supplied via ``--hash-manifest``, each exhibit
  source's hash is compared.
- **Ordering**: exhibit labels must be sequential A, B, C, ... with no
  gaps.

Exit codes:
    0 — valid
    1 — schema errors (bad YAML shape, missing required keys)
    2 — integrity errors (missing files, hash mismatch, label gap)

Usage:
    python -m scripts.packet.packet_manifest_validate \\
        examples/mustang-in-maryland/complaint_packet/packet-manifest.yaml

    python -m scripts.packet.packet_manifest_validate \\
        path/to/packet-manifest.yaml \\
        --hash-manifest evidence/manifest.sha256
"""
from __future__ import annotations

import argparse
import hashlib
import string
import sys
from pathlib import Path

from scripts.packet._manifest import (
    ManifestError,
    PacketManifest,
    load_manifest,
)


SCHEMA_EXIT = 1
INTEGRITY_EXIT = 2


def _read_hash_manifest(path: Path) -> dict[str, str]:
    """Parse a shasum-style line manifest -> {posix_relpath: hex_digest}."""
    out: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            if "  " not in line:
                continue
            digest, rel = line.split("  ", 1)
            out[rel.strip()] = digest.strip()
    return out


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _expected_labels(n: int) -> list[str]:
    # A..Z for the first 26; the loader supports AA+, but the plan spec
    # asks for "A, B, C, ... sequential with no gaps" — extend if needed.
    letters = string.ascii_uppercase
    if n <= len(letters):
        return list(letters[:n])
    out = list(letters)
    i = 0
    while len(out) < n:
        for c in letters:
            out.append(letters[i] + c)
            if len(out) == n:
                return out
        i += 1
    return out


def check_exhibit_ordering(manifest: PacketManifest) -> list[str]:
    errors: list[str] = []
    expected = _expected_labels(len(manifest.exhibits))
    for got, want, ex in zip(
        [e.label for e in manifest.exhibits], expected, manifest.exhibits
    ):
        if got != want:
            errors.append(
                f"exhibit label out of sequence: got {got!r}, expected {want!r} "
                f"for exhibit titled {ex.title!r}"
            )
    return errors


def check_exhibit_sources_exist(manifest: PacketManifest) -> list[str]:
    errors: list[str] = []
    for ex in manifest.exhibits:
        for src in ex.all_sources:
            if not src.exists():
                errors.append(
                    f"exhibit {ex.label}: source does not exist: {src}"
                )
    # Complaint source:
    if manifest.complaint.source is not None and not manifest.complaint.source.exists():
        errors.append(
            f"complaint source does not exist: {manifest.complaint.source}"
        )
    if (
        manifest.complaint.docx_source is not None
        and not manifest.complaint.docx_source.exists()
    ):
        errors.append(
            f"complaint docx_source does not exist: {manifest.complaint.docx_source}"
        )
    # Reference appendices:
    for app in manifest.reference_appendices:
        for s in app.sources:
            if not s.exists():
                errors.append(
                    f"reference appendix {app.name!r}: source does not exist: {s}"
                )
    return errors


def check_hashes(
    manifest: PacketManifest, hash_manifest_path: Path
) -> list[str]:
    if not hash_manifest_path.exists():
        return [f"hash manifest not found: {hash_manifest_path}"]
    expected = _read_hash_manifest(hash_manifest_path)
    # Paths in the hash manifest are relative to its directory (shasum
    # style). Callers typically run `shasum -a 256` from the evidence
    # root, so resolve relative to that.
    hash_root = hash_manifest_path.parent.resolve()

    errors: list[str] = []
    for ex in manifest.exhibits:
        for src in ex.all_sources:
            if not src.exists():
                continue  # already reported by the existence check
            try:
                rel = src.resolve().relative_to(hash_root).as_posix()
            except ValueError:
                errors.append(
                    f"exhibit {ex.label}: source {src} is not under hash "
                    f"manifest root {hash_root} — cannot verify hash"
                )
                continue
            want = expected.get(rel)
            if want is None:
                errors.append(
                    f"exhibit {ex.label}: no hash for {rel} in {hash_manifest_path.name}"
                )
                continue
            got = _sha256_file(src)
            if got != want:
                errors.append(
                    f"exhibit {ex.label}: hash mismatch for {rel}\n"
                    f"  expected {want}\n  actual   {got}"
                )
    return errors


def validate(
    manifest_path: Path, hash_manifest: Path | None = None
) -> tuple[int, list[str], list[str]]:
    """Return (exit_code, schema_errors, integrity_errors)."""
    try:
        manifest = load_manifest(manifest_path)
    except ManifestError as exc:
        return SCHEMA_EXIT, [str(exc)], []

    integrity: list[str] = []
    integrity.extend(check_exhibit_ordering(manifest))
    integrity.extend(check_exhibit_sources_exist(manifest))
    if hash_manifest is not None:
        integrity.extend(check_hashes(manifest, hash_manifest))

    if integrity:
        return INTEGRITY_EXIT, [], integrity
    return 0, [], []


def _print_report(
    manifest_path: Path,
    code: int,
    schema_errors: list[str],
    integrity_errors: list[str],
) -> None:
    print(f"packet-manifest-validate: {manifest_path}")
    if code == 0:
        print("  OK — schema valid, all exhibit sources exist, ordering correct.")
        return
    if schema_errors:
        print("  SCHEMA ERRORS:")
        for e in schema_errors:
            for line in str(e).splitlines():
                print(f"    {line}")
    if integrity_errors:
        print("  INTEGRITY ERRORS:")
        for e in integrity_errors:
            for line in str(e).splitlines():
                print(f"    {line}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("manifest", type=Path)
    p.add_argument(
        "--hash-manifest",
        type=Path,
        default=None,
        help="Optional shasum-style manifest for integrity checks.",
    )
    args = p.parse_args(argv)

    code, schema_errors, integrity_errors = validate(
        args.manifest, args.hash_manifest
    )
    _print_report(args.manifest, code, schema_errors, integrity_errors)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
