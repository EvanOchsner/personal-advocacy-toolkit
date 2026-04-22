"""Shared helpers for non-email ingesters (Phase 3 / track B).

The Phase 1 email pipeline's `_append_to_manifest` is private to
`email_eml_to_json.py`; it has served the repo well but doesn't do
clobber-protection (the caller chooses via `--overwrite` on the JSON
write, and the manifest is append-only). For the Phase 3 non-email
ingesters we want a slightly stricter contract:

  - Every record has a stable `source_id` (typically sha256 of the
    canonical raw artifact, optionally suffixed for multi-record
    sources like an SMS export that contains hundreds of messages).
  - `append_entry` refuses to overwrite an existing entry with the
    same `source_id` unless `force=True`.
  - Fallback-to-JSONL when PyYAML isn't available matches the email
    pipeline's behavior so downstream tooling works either way.

This module is intentionally tiny and dependency-light.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_yaml_manifest(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text()) or {}
    return loaded if isinstance(loaded, dict) else {}


def _dump_yaml_manifest(path: Path, data: dict[str, Any]) -> None:
    import yaml  # type: ignore

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def existing_source_ids(manifest_path: Path) -> set[str]:
    """Return the set of source_ids already in the manifest.

    Looks at both YAML (preferred) and the JSONL sidecar fallback so
    callers can detect collisions regardless of which path is active.
    """
    ids: set[str] = set()
    data = _load_yaml_manifest(manifest_path)
    for e in data.get("entries", []) or []:
        sid = e.get("source_id")
        if sid:
            ids.add(sid)
    jsonl = manifest_path.with_suffix(manifest_path.suffix + ".jsonl")
    if jsonl.exists():
        for line in jsonl.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = e.get("source_id")
            if sid:
                ids.add(sid)
    return ids


def append_entry(
    manifest_path: Path,
    entry: dict[str, Any],
    *,
    force: bool = False,
) -> None:
    """Append one entry to the manifest keyed on entry['source_id'].

    Raises FileExistsError if an entry with the same source_id already
    exists and `force` is False.
    """
    sid = entry.get("source_id")
    if not sid:
        raise ValueError("entry missing 'source_id'")

    if not force and sid in existing_source_ids(manifest_path):
        raise FileExistsError(
            f"manifest entry with source_id={sid!r} already exists in "
            f"{manifest_path}; pass --force to overwrite."
        )

    try:
        import yaml  # type: ignore  # noqa: F401
    except ImportError:
        _append_jsonl(manifest_path, entry)
        return

    data = _load_yaml_manifest(manifest_path)
    entries = list(data.get("entries", []) or [])
    # Drop any existing entry with the same source_id (force=True path).
    entries = [e for e in entries if e.get("source_id") != sid]
    entries.append(entry)
    data["entries"] = entries
    _dump_yaml_manifest(manifest_path, data)
