"""Pipeline-provenance dispatchers for scripts.provenance.

A "pipeline handler" surfaces content-type-specific provenance for a
file based on its path and extension. The source lucy-repair-fight
project hardcoded three types (email / policy / legal-research); this
module generalizes them as a registry driven by
`data/pipeline_dispatch.yaml`.

Rule shape:

    - path_prefix: "emails/"             # matches rel-to-evidence-root prefix
      extensions: [".eml", ".json", ".txt"]
      handler: email_three_layer
      config:
        filename_stem_re: "^(\\d+)_(\\d{4}-\\d{2}-\\d{2})_(.+)$"
        json_layer_dir: "structured"
        raw_layer_dir: "raw"
        readable_layer_dir: "readable"

Handlers take `(path, config, report)` and return a dict with a `kind:`
key plus whatever type-specific fields they surface. Unknown / no-match
files return `{"kind": "none"}`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

try:
    import yaml  # type: ignore[import-not-found]
except ModuleNotFoundError:
    yaml = None  # type: ignore[assignment]


HandlerFn = Callable[[Path, dict[str, Any], Any], dict[str, Any]]


# -----------------------------------------------------------------------------
# Handlers
# -----------------------------------------------------------------------------


def _rel_to_evidence(path: Path, report: Any) -> str | None:
    try:
        return path.resolve().relative_to(report.evidence_root.resolve()).as_posix()
    except (ValueError, OSError):
        return None


def email_three_layer(
    path: Path, config: dict[str, Any], report: Any
) -> dict[str, Any]:
    """Three-layer email pipeline: raw/ .eml → structured/ .json → readable/ .txt.

    All three layers share a filename stem. Parses the stem with
    `filename_stem_re`, finds the sibling `.json` in `json_layer_dir`,
    and surfaces Message-ID + headers summary + extraction metadata.
    """
    info: dict[str, Any] = {"kind": "email-three-layer", "stem": path.stem}
    stem_re = config.get("filename_stem_re") or r"^(\d+)_(\d{4}-\d{2}-\d{2})_(.+)$"
    m = re.match(stem_re, path.stem)
    if not m:
        report.warn(
            f"filename {path.name} does not match stem pattern {stem_re!r}"
        )
        return info
    info["index"] = int(m.group(1)) if m.group(1).isdigit() else m.group(1)
    if m.lastindex is not None and m.lastindex >= 2:
        info["date"] = m.group(2)
    if m.lastindex is not None and m.lastindex >= 3:
        info["slug"] = m.group(3)

    # Find sibling .json across the three layers.
    rel = _rel_to_evidence(path, report)
    json_layer = config.get("json_layer_dir") or "structured"
    if rel:
        # Walk up until we find a segment matching any known layer dir, then
        # swap it for json_layer.
        parts = Path(rel).parts
        layer_dirs = {
            config.get("json_layer_dir") or "structured",
            config.get("raw_layer_dir") or "raw",
            config.get("readable_layer_dir") or "readable",
        }
        swapped = False
        if path.suffix.lower() == ".json":
            json_sibling = path
        else:
            new_parts: list[str] = []
            for part in parts:
                if part in layer_dirs and not swapped:
                    new_parts.append(json_layer)
                    swapped = True
                else:
                    new_parts.append(part)
            json_sibling = (
                report.evidence_root / Path(*new_parts).with_suffix(".json")
            )
    else:
        json_sibling = path.with_suffix(".json")

    if json_sibling.exists():
        try:
            data = json.loads(json_sibling.read_text(encoding="utf-8"))
            info["json_sibling"] = str(json_sibling)
            info["message_id"] = data.get("message_id") or (
                (data.get("headers") or {}).get("Message-ID")
            )
            for k in ("from", "to", "cc", "date", "subject"):
                v = data.get(k) or (data.get("headers") or {}).get(k.capitalize())
                if v:
                    info.setdefault("headers_summary", {})[k] = v
            em = data.get("extraction_metadata")
            if em:
                info["extraction_metadata"] = em
        except (OSError, json.JSONDecodeError) as exc:
            report.warn(f"could not parse sibling .json {json_sibling}: {exc}")
    else:
        report.warn(f"no sibling .json found at {json_sibling}")
    return info


def readme_catalog(
    path: Path, config: dict[str, Any], report: Any
) -> dict[str, Any]:
    """Catalog lookup: surface every line of the configured catalog file
    that mentions this file's basename."""
    catalog_rel = config.get("catalog_path")
    if not catalog_rel:
        report.warn("readme_catalog handler missing catalog_path config")
        return {"kind": "catalog", "catalog_path": None}
    catalog = report.evidence_root / catalog_rel
    info: dict[str, Any] = {"kind": "catalog", "catalog_path": str(catalog)}
    if not catalog.exists():
        report.warn(f"catalog file missing at {catalog}")
        return info
    try:
        text = catalog.read_text(encoding="utf-8")
    except OSError as exc:
        report.warn(f"cannot read catalog {catalog}: {exc}")
        return info
    mentions = [line.strip() for line in text.splitlines() if path.name in line]
    info["mentions"] = mentions
    if not mentions:
        report.warn(f"{path.name} not mentioned in {catalog_rel}")
    return info


def yaml_frontmatter_sibling(
    path: Path, config: dict[str, Any], report: Any
) -> dict[str, Any]:
    """Parse YAML frontmatter from a sibling file (typically the .md
    companion of a rendered PDF or downloaded HTML)."""
    sibling_suffix = config.get("sibling_suffix") or ".md"
    surface_keys = config.get("surface_keys") or [
        "pdf_sha256",
        "source_url",
        "retrieved_date",
        "citation",
        "authority",
    ]
    sibling = path.with_suffix(sibling_suffix)
    info: dict[str, Any] = {
        "kind": "yaml-frontmatter-sibling",
        "sibling": str(sibling),
    }
    if not sibling.exists():
        report.warn(f"no sibling {sibling_suffix} found next to {path.name}")
        return info
    try:
        text = sibling.read_text(encoding="utf-8")
    except OSError as exc:
        report.warn(f"cannot read sibling {sibling}: {exc}")
        return info
    m = re.match(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
    if not m:
        report.warn(f"sibling {sibling.name} has no YAML frontmatter")
        return info
    fm_text = m.group(1)
    fm: dict[str, Any] = {}
    if yaml is not None:
        try:
            loaded = yaml.safe_load(fm_text)
            if isinstance(loaded, dict):
                fm = loaded
        except Exception:  # pragma: no cover
            fm = {}
    else:
        # Stdlib fallback: simple "key: value" parse (no nesting).
        for line in fm_text.splitlines():
            mm = re.match(r"^([a-zA-Z0-9_]+):\s*(.*)$", line)
            if mm:
                fm[mm.group(1)] = mm.group(2).strip().strip('"').strip("'")
    info["frontmatter"] = {k: fm[k] for k in surface_keys if k in fm}
    if not info["frontmatter"]:
        report.warn(
            f"sibling {sibling.name} frontmatter lacks any of the "
            f"surfaced keys: {surface_keys}"
        )
    return info


# Registry — string names map to callables. Extend here when adding a
# new handler to data/pipeline_dispatch.yaml.
HANDLERS: dict[str, HandlerFn] = {
    "email_three_layer": email_three_layer,
    "readme_catalog": readme_catalog,
    "yaml_frontmatter_sibling": yaml_frontmatter_sibling,
}


# -----------------------------------------------------------------------------
# Dispatcher
# -----------------------------------------------------------------------------


def _load_rules(pipeline_config: Path) -> list[dict[str, Any]]:
    if not pipeline_config.exists() or yaml is None:
        return []
    try:
        data = yaml.safe_load(pipeline_config.read_text(encoding="utf-8")) or {}
    except Exception:  # pragma: no cover
        return []
    rules = data.get("rules") or []
    if not isinstance(rules, list):
        return []
    return rules


def _match(path: Path, rel_to_evidence: str | None, rule: dict[str, Any]) -> bool:
    prefix = rule.get("path_prefix")
    extensions = rule.get("extensions") or []
    if extensions and path.suffix.lower() not in [e.lower() for e in extensions]:
        return False
    if prefix:
        if not rel_to_evidence:
            return False
        if not rel_to_evidence.startswith(prefix):
            return False
    return True


def dispatch(path: Path, pipeline_config: Path, report: Any) -> dict[str, Any]:
    """Find the first matching rule and invoke its handler."""
    rel_to_evidence = _rel_to_evidence(path, report)
    for rule in _load_rules(pipeline_config):
        if not _match(path, rel_to_evidence, rule):
            continue
        handler_name = rule.get("handler")
        fn = HANDLERS.get(handler_name) if handler_name else None
        if fn is None:
            report.warn(
                f"pipeline rule matched but handler {handler_name!r} "
                "is not registered"
            )
            return {"kind": "none", "note": f"unknown handler {handler_name!r}"}
        return fn(path, rule.get("config") or {}, report)
    return {"kind": "none", "note": "no pipeline rule matched this path"}
