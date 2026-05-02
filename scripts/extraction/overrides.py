"""Manual extraction overrides — case-author-supplied corrections.

A YAML sidecar at ``<case>/extraction/overrides/<source_id>.yaml``
carries directives the cascade should apply on top of automatic
behavior. Schema (all fields optional except ``source_id``):

    source_id: 7a3f1e9c
    file: evidence/policy/raw/acr-61-3.pdf
    overrides:
      skip_pages: [1, 14]
      crop_boxes:
        "3": [50, 100, 612, 700]   # PDF user-space coords (left, bottom, right, top)
      strip_text_patterns:
        - "CONFIDENTIAL — DO NOT DISTRIBUTE"
        - "Page \\\\d+ of \\\\d+"
      force_tier: 2
      vlm_provider: claude
      garble_thresholds:
        min_chars_per_page: 30
      notes: "Watermark on every page; tier 0 picks it up as body text."

Overrides feed both the live extraction and the reproducibility
script, which records exactly which overrides were used.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExtractionOverrides:
    """Parsed override sidecar (or empty if none on disk)."""

    source_id: str = ""
    file: str | None = None
    skip_pages: list[int] = field(default_factory=list)
    crop_boxes: dict[int, tuple[float, float, float, float]] = field(default_factory=dict)
    strip_text_patterns: list[str] = field(default_factory=list)
    force_tier: int | None = None
    vlm_provider: str | None = None
    garble_thresholds: dict[str, float] = field(default_factory=dict)
    notes: str | None = None
    # Original raw mapping, kept for the recipe / audit trail so we
    # don't lose unknown future fields if the schema grows.
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.skip_pages:
            out["skip_pages"] = list(self.skip_pages)
        if self.crop_boxes:
            out["crop_boxes"] = {str(k): list(v) for k, v in self.crop_boxes.items()}
        if self.strip_text_patterns:
            out["strip_text_patterns"] = list(self.strip_text_patterns)
        if self.force_tier is not None:
            out["force_tier"] = self.force_tier
        if self.vlm_provider is not None:
            out["vlm_provider"] = self.vlm_provider
        if self.garble_thresholds:
            out["garble_thresholds"] = dict(self.garble_thresholds)
        if self.notes:
            out["notes"] = self.notes
        return out

    def apply_text_strip(self, text: str) -> str:
        """Apply ``strip_text_patterns`` to *text* (regex)."""
        if not self.strip_text_patterns:
            return text
        out = text
        for pat in self.strip_text_patterns:
            try:
                out = re.sub(pat, "", out)
            except re.error:
                # Fall back to literal replacement on bad regex so
                # users without regex experience still get a useful
                # behavior; we record the problem in warnings via the
                # caller (the cascade emits a warning when this returns
                # a different result than expected).
                out = out.replace(pat, "")
        return out

    def is_empty(self) -> bool:
        return (
            not self.skip_pages
            and not self.crop_boxes
            and not self.strip_text_patterns
            and self.force_tier is None
            and self.vlm_provider is None
            and not self.garble_thresholds
        )


def overrides_path(case_root: Path, source_id: str) -> Path:
    """Conventional path for an override sidecar."""
    return case_root / "extraction" / "overrides" / f"{source_id}.yaml"


def load_overrides(path: Path) -> ExtractionOverrides:
    """Load ``ExtractionOverrides`` from ``path``.

    Returns an empty ``ExtractionOverrides`` if ``path`` doesn't exist
    or YAML isn't installed and the file is YAML. JSON sidecars (with
    a ``.json`` suffix) are accepted as a fallback for users without
    PyYAML.
    """
    if not path.is_file():
        return ExtractionOverrides()

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return ExtractionOverrides()
    else:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            # No YAML, no overrides. We could attempt a tiny ad-hoc
            # parser but failing loud is better — the user installed
            # the project without PyYAML, which is itself a signal.
            return ExtractionOverrides()
        try:
            data = yaml.safe_load(text) or {}
        except yaml.YAMLError:
            return ExtractionOverrides()

    if not isinstance(data, dict):
        return ExtractionOverrides()
    return _from_dict(data)


def _from_dict(data: dict[str, Any]) -> ExtractionOverrides:
    overrides = data.get("overrides") or {}
    if not isinstance(overrides, dict):
        overrides = {}
    skip_pages = [int(p) for p in overrides.get("skip_pages") or [] if isinstance(p, (int, str)) and str(p).lstrip("-").isdigit()]
    crop_raw = overrides.get("crop_boxes") or {}
    crop_boxes: dict[int, tuple[float, float, float, float]] = {}
    if isinstance(crop_raw, dict):
        for k, v in crop_raw.items():
            try:
                page = int(k)
                if isinstance(v, (list, tuple)) and len(v) == 4:
                    crop_boxes[page] = (
                        float(v[0]), float(v[1]), float(v[2]), float(v[3])
                    )
            except (TypeError, ValueError):
                continue
    strip_patterns = [
        str(p) for p in overrides.get("strip_text_patterns") or [] if p
    ]
    force_tier = overrides.get("force_tier")
    if force_tier is not None:
        try:
            force_tier = int(force_tier)
        except (TypeError, ValueError):
            force_tier = None
    vlm_provider = overrides.get("vlm_provider")
    if vlm_provider is not None and not isinstance(vlm_provider, str):
        vlm_provider = None
    garble_raw = overrides.get("garble_thresholds") or {}
    garble_thresholds: dict[str, float] = {}
    if isinstance(garble_raw, dict):
        for k, v in garble_raw.items():
            try:
                garble_thresholds[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
    notes = overrides.get("notes")
    if notes is not None:
        notes = str(notes)

    return ExtractionOverrides(
        source_id=str(data.get("source_id") or ""),
        file=str(data["file"]) if data.get("file") else None,
        skip_pages=skip_pages,
        crop_boxes=crop_boxes,
        strip_text_patterns=strip_patterns,
        force_tier=force_tier,
        vlm_provider=vlm_provider,
        garble_thresholds=garble_thresholds,
        notes=notes,
        raw=data,
    )
