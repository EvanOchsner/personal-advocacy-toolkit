"""Append-only manifest helper for ``<case>/references/``.

Mirrors the contract of ``scripts.ingest._manifest`` but writes a
references-specific YAML file (default
``<case-root>/references/.references-manifest.yaml``) plus the SHA-256
text manifest at ``<case-root>/.references-manifest.sha256``.

The YAML manifest carries one entry per ingested document (raw +
structured + readable triple). The SHA-256 manifest is the same shape
as the evidence manifest produced by ``scripts.evidence_hash`` and is
what downstream provenance joins on.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CHUNK = 1024 * 1024


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        return {}
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return loaded if isinstance(loaded, dict) else {}


def _dump_yaml(path: Path, data: dict[str, Any]) -> None:
    import yaml  # type: ignore

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def existing_source_ids(manifest_path: Path) -> set[str]:
    ids: set[str] = set()
    data = _load_yaml(manifest_path)
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
    exists and ``force`` is False.
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

    data = _load_yaml(manifest_path)
    entries = list(data.get("entries", []) or [])
    entries = [e for e in entries if e.get("source_id") != sid]
    entries.append(entry)
    data["entries"] = entries
    data.setdefault("schema_version", "0.1")
    _dump_yaml(manifest_path, data)


def list_entries(manifest_path: Path) -> list[dict[str, Any]]:
    """Return all entries from the manifest, in append order."""
    data = _load_yaml(manifest_path)
    out = list(data.get("entries", []) or [])
    jsonl = manifest_path.with_suffix(manifest_path.suffix + ".jsonl")
    if jsonl.exists():
        for line in jsonl.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


# ---------------------------------------------------------------------------
# SHA-256 text manifest (parallels scripts.evidence_hash output)
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def refresh_sha256_manifest(references_root: Path, manifest_path: Path) -> int:
    """Re-hash every file under ``references_root`` and write the manifest.

    Returns the number of files hashed.

    Skips the manifest files themselves (``.references-manifest.*``).
    Paths in the output are POSIX, sorted, relative to ``references_root``.
    """
    rows: list[tuple[str, str]] = []
    skip_names = {
        ".references-manifest.yaml",
        ".references-manifest.yaml.jsonl",
        ".references-manifest.sha256",
    }
    for p in sorted(references_root.rglob("*")):
        if not p.is_file():
            continue
        if p.name in skip_names:
            continue
        rel = p.relative_to(references_root).as_posix()
        rows.append((_sha256_file(p), rel))
    rows.sort(key=lambda r: r[1])
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as fh:
        for digest, rel in rows:
            fh.write(f"{digest}  {rel}\n")
    return len(rows)
