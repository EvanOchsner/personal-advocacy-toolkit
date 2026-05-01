"""Hash-based cache invalidation for the case-map build step.

The cache lives at <case>/.case-map/. Layout:

    .case-map/
      manifest.json        — {schema_version, sources: {path: sha256}, widgets: {name: [paths]}}
      dashboard.json       — payload served verbatim by /api/dashboard
      central_issue.json   — per-widget JSON
      parties.json
      references.json
      adjudicators.json
      timeline.json

A widget is regenerated when any of its declared input paths has a
different sha256 than the one recorded in manifest.json. `--force`
discards manifest.json entirely.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CACHE_SCHEMA_VERSION = "1"
MANIFEST_NAME = "manifest.json"
DASHBOARD_NAME = "dashboard.json"


@dataclass
class CacheManifest:
    sources: dict[str, str] = field(default_factory=dict)  # rel-path -> sha256
    widgets: dict[str, list[str]] = field(default_factory=dict)  # widget -> [rel-paths]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CACHE_SCHEMA_VERSION,
            "sources": dict(self.sources),
            "widgets": {k: list(v) for k, v in self.widgets.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CacheManifest":
        if data.get("schema_version") != CACHE_SCHEMA_VERSION:
            return cls()  # incompatible — treat as empty so everything regenerates
        sources = data.get("sources") or {}
        widgets = data.get("widgets") or {}
        return cls(
            sources={str(k): str(v) for k, v in sources.items()},
            widgets={str(k): [str(p) for p in v] for k, v in widgets.items()},
        )


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(cache_dir: Path) -> CacheManifest:
    p = cache_dir / MANIFEST_NAME
    if not p.is_file():
        return CacheManifest()
    try:
        return CacheManifest.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError):
        return CacheManifest()


def write_manifest(cache_dir: Path, manifest: CacheManifest) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def is_widget_stale(
    widget: str,
    inputs: list[Path],
    case_dir: Path,
    manifest: CacheManifest,
    cache_dir: Path,
) -> bool:
    """True if any input has changed or the widget's output file is missing."""
    output = cache_dir / f"{widget}.json"
    if not output.is_file():
        return True
    declared = manifest.widgets.get(widget) or []
    rel_inputs = sorted({str(p.relative_to(case_dir)) for p in inputs})
    if declared != rel_inputs:
        return True
    for p in inputs:
        rel = str(p.relative_to(case_dir))
        prev = manifest.sources.get(rel)
        if prev is None:
            return True
        if hash_file(p) != prev:
            return True
    return False


def record_widget(
    widget: str,
    inputs: list[Path],
    case_dir: Path,
    manifest: CacheManifest,
) -> None:
    manifest.widgets[widget] = sorted({str(p.relative_to(case_dir)) for p in inputs})
    for p in inputs:
        manifest.sources[str(p.relative_to(case_dir))] = hash_file(p)


def write_widget(cache_dir: Path, widget: str, payload: dict[str, Any]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{widget}.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_widget(cache_dir: Path, widget: str) -> dict[str, Any]:
    p = cache_dir / f"{widget}.json"
    return json.loads(p.read_text(encoding="utf-8"))
