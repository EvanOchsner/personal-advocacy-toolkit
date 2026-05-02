"""End-to-end three-layer writer: raw → structured → readable + recipe.

Replaces the per-format ingest CLIs (``pdf_to_text``, ``html_to_text``,
``email_eml_to_json`` + ``email_json_to_txt``). Given a source file
and an output dir, writes:

  - ``<out_dir>/raw/<source_id>.<ext>``           (byte-identical copy)
  - ``<out_dir>/structured/<source_id>.json``     (extraction metadata)
  - ``<out_dir>/readable/<source_id>.txt``        (plaintext / markdown)

…and, if a case root is provided, also:

  - ``<case_root>/extraction/scripts/extract_<source_id>.py`` (recipe)

A manifest entry can be appended (same shape as the prior ingest
manifests) so existing manifest tooling keeps working.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import cascade, recipe
from .result import ExtractionResult

# Reuse the existing manifest helper so the file format doesn't drift.
from scripts.ingest._manifest import append_entry


def _classify_kind(file: Path) -> str:
    suffix = file.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in (".html", ".htm", ".xhtml"):
        return "html"
    if suffix == ".eml":
        return "email"
    if suffix in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif"):
        return "image"
    return "unknown"


def _suffix_for(kind: str, original: str) -> str:
    if kind == "pdf":
        return ".pdf"
    if kind == "html":
        return original or ".html"
    if kind == "email":
        return ".eml"
    if kind == "image":
        return original or ".png"
    return original or ".bin"


def write_three_layer(
    src: Path,
    out_dir: Path,
    *,
    case_root: Path | None = None,
    vlm_provider: str | None = None,
    interactive: bool = True,
    verbose: bool = False,
    manifest_path: Path | None = None,
    manifest_kind: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Run the cascade and write raw/structured/readable + (optional) recipe.

    Returns the structured record (suitable for printing / further
    processing). Raises ``FileExistsError`` from the manifest helper
    if a same-source-id entry already exists and ``force`` is False.
    """
    src = Path(src)
    out_dir = Path(out_dir)

    raw_bytes = src.read_bytes()
    source_sha = hashlib.sha256(raw_bytes).hexdigest()
    source_id = source_sha[:16]

    kind = _classify_kind(src)
    raw_dir = out_dir / "raw"
    struct_dir = out_dir / "structured"
    readable_dir = out_dir / "readable"
    for d in (raw_dir, struct_dir, readable_dir):
        d.mkdir(parents=True, exist_ok=True)

    raw_out = raw_dir / f"{source_id}{_suffix_for(kind, src.suffix.lower())}"
    raw_out.write_bytes(raw_bytes)

    result: ExtractionResult = cascade.extract(
        raw_out,
        case_root=case_root,
        vlm_provider=vlm_provider,
        interactive=interactive,
        verbose=verbose,
    )

    readable_path = readable_dir / f"{source_id}.txt"
    readable_path.write_text(result.text, encoding="utf-8")

    parsed_at = datetime.now(timezone.utc).isoformat()
    record: dict[str, Any] = {
        "source_file": str(src),
        "source_sha256": source_sha,
        "source_id": source_id,
        "kind": kind,
        "method": result.method,
        "tier": result.tier,
        "vlm_provider": result.vlm_provider,
        "title": result.title,
        "charset": result.charset,
        "text_chars": len(result.text),
        "page_count": _page_count(result),
        "raw_path": str(raw_out),
        "readable_path": str(readable_path),
        "parsed_at": parsed_at,
        "warnings": list(result.warnings),
        "overrides_applied": dict(result.overrides_applied),
        "extraction": result.to_metadata_dict(),
    }
    structured_path = struct_dir / f"{source_id}.json"
    structured_path.write_text(
        json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )

    if case_root is not None:
        try:
            recipe.write_recipe(
                case_root=case_root,
                source_id=source_id,
                source_file=raw_out,
                source_sha256=source_sha,
                structured_path=structured_path,
                readable_path=readable_path,
                result=result,
            )
        except OSError as exc:
            record["warnings"].append(f"recipe writer failed: {exc}")

    if manifest_path is not None:
        entry_kind = manifest_kind or f"extract_{kind}"
        # `record["kind"]` is the bare format ("pdf", "html", ...);
        # the manifest "kind" reflects the cascade pipeline that
        # produced the entry ("extract_pdf"). Spread first, then
        # override the kind so dict-merge order doesn't matter.
        entry = {**record, "kind": entry_kind}
        append_entry(manifest_path, entry, force=force)

    return record


def _page_count(result: ExtractionResult) -> int:
    if result.page_results is None:
        return 0
    return len(result.page_results)
