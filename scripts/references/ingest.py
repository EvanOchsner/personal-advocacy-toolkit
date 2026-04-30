"""Ingest a single trusted reference doc into ``<case>/references/``.

CLI:

    uv run python -m scripts.references.ingest \\
        --file path/to/policy.pdf \\
        --kind official-policy \\
        --citation "Acme TOS as of 2026-04-15" \\
        --case-root .

    uv run python -m scripts.references.ingest \\
        --url https://mgaleg.maryland.gov/... \\
        --kind statute \\
        --citation "Md. Code Ins. § 27-303" \\
        --jurisdiction MD \\
        --case-root .

The pipeline:

    1. Acquire raw bytes (file read OR HTTP fetch with allowlist).
    2. Compute sha256, derive a stable slug from the citation/URL/filename.
    3. Write raw bytes to ``references/raw/<slug>.<ext>``.
    4. Extract plaintext → ``references/readable/<slug>.txt``.
    5. Run completeness heuristics (``scripts.references.assess``).
    6. Write sidecar JSON → ``references/structured/<slug>.json``.
    7. Append to ``references/.references-manifest.yaml`` (keyed on
       sha256 source_id; clobber-protected with ``--force``).
    8. Refresh ``<case>/.references-manifest.sha256``.

Disclaimers
-----------
The verbatim string ``"This is reference information, not legal advice."``
is always written into the sidecar. The agent must carry it through any
quote, paraphrase, or downstream draft.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.references import _manifest, assess, extract, fetch

DISCLAIMER = "This is reference information, not legal advice."

KINDS = [
    "statute",
    "regulation",
    "official-policy",
    "tos",
    "guidance",
    "case-law",
    "other",
]

SCHEMA_VERSION = "0.1"


# ---------------------------------------------------------------------------
# Slug + path derivation
# ---------------------------------------------------------------------------


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str, *, max_len: int = 60) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s[:max_len].rstrip("-") or "ref"


def _derive_slug(*, citation: str | None, url: str | None, src: Path | None) -> str:
    if citation:
        return _slugify(citation)
    if url:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host_path = (parsed.hostname or "") + (parsed.path or "")
        return _slugify(host_path)
    if src is not None:
        return _slugify(src.stem)
    return "ref"


def _next_unique_slug(base: str, raw_dir: Path) -> str:
    """Append -2, -3, etc. if a doc with the same slug already exists."""
    candidate = base
    i = 2
    while any(raw_dir.glob(f"{candidate}.*")):
        candidate = f"{base}-{i}"
        i += 1
    return candidate


def _suffix_for_content_type(content_type: str, *, fallback_path: Path | None = None) -> str:
    table = {
        "text/html": ".html",
        "application/xhtml+xml": ".html",
        "application/pdf": ".pdf",
        "text/plain": ".txt",
        "text/markdown": ".md",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/msword": ".doc",
    }
    if content_type in table:
        return table[content_type]
    if fallback_path is not None and fallback_path.suffix:
        return fallback_path.suffix.lower()
    return ".bin"


# ---------------------------------------------------------------------------
# Core ingest
# ---------------------------------------------------------------------------


def _ensure_dirs(case_root: Path) -> tuple[Path, Path, Path]:
    raw_dir = case_root / "references" / "raw"
    struct_dir = case_root / "references" / "structured"
    readable_dir = case_root / "references" / "readable"
    for d in (raw_dir, struct_dir, readable_dir):
        d.mkdir(parents=True, exist_ok=True)
    return raw_dir, struct_dir, readable_dir


def ingest(
    *,
    case_root: Path,
    raw_bytes: bytes,
    content_type: str,
    kind: str,
    citation: str | None,
    title: str | None,
    jurisdiction: str | None,
    source_origin: str,  # "user-supplied" | "fetched" | "manual-download"
    source_url: str | None,
    source_label: str | None,
    source_filename: str | None,
    fetch_metadata: dict[str, Any] | None = None,
    as_of: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Land a single doc into ``case_root/references/``.

    Returns the sidecar dict that was written.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; expected one of {KINDS}")

    raw_dir, struct_dir, readable_dir = _ensure_dirs(case_root)

    sha = hashlib.sha256(raw_bytes).hexdigest()
    source_id = sha[:16]

    base_slug = _derive_slug(
        citation=citation,
        url=source_url,
        src=Path(source_filename) if source_filename else None,
    )
    slug = _next_unique_slug(base_slug, raw_dir)

    suffix = _suffix_for_content_type(
        content_type,
        fallback_path=Path(source_filename) if source_filename else None,
    )
    raw_path = raw_dir / f"{slug}{suffix}"
    raw_path.write_bytes(raw_bytes)

    extraction = extract.extract(raw_bytes, content_type)
    readable_path = readable_dir / f"{slug}.txt"
    readable_path.write_text(extraction.text, encoding="utf-8")

    assessment = assess.assess(extraction.text, kind=kind)

    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    sidecar: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_id": source_id,
        "source_sha256": sha,
        "kind": kind,
        "citation": citation,
        "title": title or extraction.title,
        "jurisdiction": jurisdiction,
        "source_url": source_url,
        "source_label": source_label,
        "source_origin": source_origin,
        "source_filename": source_filename,
        "fetched_at": fetched_at,
        "as_of": as_of,
        "content_type": content_type,
        "size_bytes": len(raw_bytes),
        "raw_path": raw_path.relative_to(case_root).as_posix(),
        "readable_path": readable_path.relative_to(case_root).as_posix(),
        "extraction": {
            "method": extraction.method,
            "title": extraction.title,
            "text_chars": len(extraction.text),
            "warnings": list(extraction.warnings),
        },
        "assessment": assessment.as_dict(),
        "fetch": fetch_metadata,
        "disclaimer": DISCLAIMER,
    }

    sidecar_path = struct_dir / f"{slug}.json"
    sidecar_path.write_text(
        json.dumps(sidecar, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    manifest_yaml = case_root / "references" / ".references-manifest.yaml"
    manifest_entry = {
        "source_id": source_id,
        "kind": kind,
        "citation": citation,
        "title": sidecar["title"],
        "jurisdiction": jurisdiction,
        "source_origin": source_origin,
        "source_url": source_url,
        "fetched_at": fetched_at,
        "raw_path": sidecar["raw_path"],
        "readable_path": sidecar["readable_path"],
        "structured_path": sidecar_path.relative_to(case_root).as_posix(),
    }
    _manifest.append_entry(manifest_yaml, manifest_entry, force=force)

    sha256_manifest = case_root / ".references-manifest.sha256"
    references_root = case_root / "references"
    _manifest.refresh_sha256_manifest(references_root, sha256_manifest)

    return sidecar


# ---------------------------------------------------------------------------
# Source acquisition
# ---------------------------------------------------------------------------


def _acquire_from_file(path: Path, declared_type: str | None) -> tuple[bytes, str]:
    raw = path.read_bytes()
    ct = extract.normalize_content_type(declared_type, path)
    return raw, ct


def _acquire_from_url(
    url: str,
    *,
    declared_type: str | None,
    allow_unknown: bool,
    timeout: float,
) -> tuple[bytes, str, dict[str, Any]]:
    result = fetch.fetch(url, allow_unknown=allow_unknown, timeout=timeout)
    ct = extract.normalize_content_type(
        declared_type or result.content_type,
        Path(result.final_url),
    )
    return result.raw_bytes, ct, fetch.describe(result)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Ingest a trusted reference document into <case>/references/.",
    )
    src_group = ap.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--file", type=Path, help="Local file to ingest.")
    src_group.add_argument("--url", type=str, help="URL to fetch and ingest.")

    ap.add_argument(
        "--kind",
        required=True,
        choices=KINDS,
        help="Document kind.",
    )
    ap.add_argument(
        "--citation",
        type=str,
        default=None,
        help="Canonical citation (e.g., 'Md. Code Ins. § 27-303').",
    )
    ap.add_argument("--title", type=str, default=None, help="Human-readable title.")
    ap.add_argument(
        "--jurisdiction",
        type=str,
        default=None,
        help="2-letter US state code, 'federal', or '*' for cross-jurisdiction (e.g., ToS).",
    )
    ap.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="Date the version applied (YYYY-MM-DD); important for ToS.",
    )
    ap.add_argument(
        "--source-label",
        type=str,
        default=None,
        help="Human-readable source name (e.g., 'Maryland General Assembly').",
    )
    ap.add_argument(
        "--source-origin",
        choices=["user-supplied", "fetched", "manual-download"],
        default=None,
        help="How the user got this copy. Default: 'fetched' for --url, 'user-supplied' for --file.",
    )
    ap.add_argument(
        "--declared-content-type",
        type=str,
        default=None,
        help="Override the content-type detected from suffix or HTTP response.",
    )
    ap.add_argument(
        "--case-root",
        type=Path,
        default=Path.cwd(),
        help="Case-folder root (default: cwd).",
    )
    ap.add_argument(
        "--allow-unknown",
        action="store_true",
        help=(
            "When fetching, allow hosts that are not on the trusted-source "
            "allowlist. Use only after explicit user confirmation."
        ),
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds (default: 30).",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing manifest entry with the same source_id.",
    )
    ap.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format for the summary line.",
    )
    args = ap.parse_args(argv)

    case_root: Path = args.case_root.resolve()
    if not case_root.is_dir():
        print(f"error: case-root does not exist: {case_root}", file=sys.stderr)
        return 2

    fetch_metadata: dict[str, Any] | None = None
    source_url: str | None = None
    source_filename: str | None = None
    source_origin = args.source_origin

    if args.file is not None:
        if not args.file.is_file():
            print(f"error: file not found: {args.file}", file=sys.stderr)
            return 2
        raw_bytes, content_type = _acquire_from_file(args.file, args.declared_content_type)
        source_filename = str(args.file)
        source_origin = source_origin or "user-supplied"
    else:
        try:
            raw_bytes, content_type, fetch_metadata = _acquire_from_url(
                args.url,
                declared_type=args.declared_content_type,
                allow_unknown=args.allow_unknown,
                timeout=args.timeout,
            )
        except fetch.FetchRefused as e:
            print(f"error: {e}", file=sys.stderr)
            return 4
        except fetch.FetchError as e:
            print(f"error: {e}", file=sys.stderr)
            return 5
        source_url = args.url
        source_origin = source_origin or "fetched"

    try:
        sidecar = ingest(
            case_root=case_root,
            raw_bytes=raw_bytes,
            content_type=content_type,
            kind=args.kind,
            citation=args.citation,
            title=args.title,
            jurisdiction=args.jurisdiction,
            source_origin=source_origin,
            source_url=source_url,
            source_label=args.source_label,
            source_filename=source_filename,
            fetch_metadata=fetch_metadata,
            as_of=args.as_of,
            force=args.force,
        )
    except FileExistsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3

    if args.format == "json":
        print(json.dumps(sidecar, indent=2, ensure_ascii=False))
    else:
        flags = sidecar["assessment"]["flags"]
        warn_flags = [f for f in flags if f["level"] == "warn"]
        print(
            f"ingested {sidecar['source_id']}: {sidecar['kind']} "
            f"[{sidecar['citation'] or '<no citation>'}] "
            f"-> {sidecar['readable_path']} "
            f"({sidecar['extraction']['text_chars']} chars)"
        )
        if warn_flags:
            print(f"  {len(warn_flags)} warning(s):")
            for f in warn_flags:
                print(f"    [{f['code']}] {f['detail']}")
        print(f"  ({DISCLAIMER})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
