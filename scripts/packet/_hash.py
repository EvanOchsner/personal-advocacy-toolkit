"""Shared SHA-256 helper for packet tooling.

Extracted so `compile_reference.py` and `packet_manifest_validate.py`
use identical semantics (1 MiB chunked read) and lower the surface for
hash-comparison drift bugs.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    """Return hex-encoded SHA-256 of `path`, read in 1 MiB chunks."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
