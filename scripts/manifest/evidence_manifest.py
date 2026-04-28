#!/usr/bin/env python3
"""Build a unified evidence-manifest.yaml for the dashboard.

The dashboard (`scripts/status/case_dashboard.py`) and other downstream
tools expect a single YAML shape:

    entries:
      - path: evidence/emails/raw/001_*.eml
        kind: email_raw
        sha256: <hex>
        ...

This module scans an evidence tree and infers `kind` for every file
from `data/kind_inference.yaml` (first-match-wins glob rules). It can
optionally merge in per-ingester manifests produced by the Phase 3B
non-email ingesters (SMS / screenshot / voicemail / EOB) via `--merge`.

Usage:
    uv run python -m scripts.manifest.evidence_manifest \\
        --root examples/maryland-mustang/evidence \\
        --out  examples/maryland-mustang/evidence-manifest.yaml

    # Optionally merge Phase 3B manifests:
    uv run python -m scripts.manifest.evidence_manifest \\
        --root examples/maryland-mustang/evidence \\
        --merge examples/maryland-mustang/ingest/sms-manifest.yaml \\
        --merge examples/maryland-mustang/ingest/eob-manifest.yaml \\
        --out  examples/maryland-mustang/evidence-manifest.yaml

Idempotent: running twice on the same tree produces byte-identical
output modulo the `generated_at` timestamp field.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.intake._common import data_dir, find_repo_root, load_yaml

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


DEFAULT_KIND = "unknown"


def _load_rules(rules_path: Path | None = None) -> list[dict[str, str]]:
    """Load ordered glob → kind rules from data/kind_inference.yaml."""
    if rules_path is None:
        repo = find_repo_root()
        rules_path = data_dir(repo) / "kind_inference.yaml"
    raw = load_yaml(rules_path)
    rules = raw.get("rules") or []
    out: list[dict[str, str]] = []
    for r in rules:
        glob = r.get("glob")
        kind = r.get("kind")
        if glob and kind:
            out.append({"glob": glob, "kind": kind})
    return out


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a shell-style glob to a regex, with proper `**` semantics.

    - ``**/`` matches zero or more path segments (including none).
    - ``**`` matches anything including path separators.
    - ``*`` matches any run of characters except ``/``.
    - ``?`` matches a single character except ``/``.
    - Everything else is literal.
    """
    i = 0
    out: list[str] = []
    p = pattern
    while i < len(p):
        if p[i : i + 3] == "**/":
            out.append("(?:.*/)?")
            i += 3
        elif p[i : i + 2] == "**":
            out.append(".*")
            i += 2
        elif p[i] == "*":
            out.append("[^/]*")
            i += 1
        elif p[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(p[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$", re.IGNORECASE)


_PATTERN_CACHE: dict[str, re.Pattern[str]] = {}


def _match(path: str, pattern: str) -> bool:
    rx = _PATTERN_CACHE.get(pattern)
    if rx is None:
        rx = _glob_to_regex(pattern)
        _PATTERN_CACHE[pattern] = rx
    return rx.match(path) is not None


def infer_kind(rel_path: str, rules: list[dict[str, str]]) -> str:
    """First-match-wins glob match against the ordered rule list."""
    rp = rel_path.replace("\\", "/")
    for r in rules:
        if _match(rp, r["glob"]):
            return r["kind"]
    return DEFAULT_KIND


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_evidence_files(root: Path) -> list[Path]:
    """Walk root; yield regular files only, sorted for determinism."""
    if not root.exists():
        return []
    files: list[Path] = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and not p.name.startswith("."):
            files.append(p)
    return files


def scan_tree(
    root: Path,
    rules: list[dict[str, str]],
    *,
    compute_hashes: bool = True,
) -> list[dict[str, Any]]:
    """Return one entry per regular file under `root`, sorted by path."""
    entries: list[dict[str, Any]] = []
    for p in _iter_evidence_files(root):
        rel = p.relative_to(root).as_posix()
        entry: dict[str, Any] = {
            "path": rel,
            "kind": infer_kind(rel, rules),
            "size": p.stat().st_size,
        }
        if compute_hashes:
            entry["sha256"] = _sha256(p)
        entries.append(entry)
    return entries


def _merge_external(
    entries: list[dict[str, Any]],
    merge_paths: list[Path],
) -> list[dict[str, Any]]:
    """Fold in entries from Phase 3B per-ingester manifests.

    External entries are appended (not deduped against scanned entries);
    they typically describe derived artifacts that live outside the
    evidence/ tree (SMS-export rows, screenshot captures, EOB rows).
    Each external entry is tagged with `source_manifest` so downstream
    tooling can tell where it came from.
    """
    out = list(entries)
    for mp in merge_paths:
        if not mp.exists():
            print(f"warning: --merge file not found: {mp}", file=sys.stderr)
            continue
        data = load_yaml(mp)
        ext = data.get("entries") or []
        for e in ext:
            e = dict(e)
            e.setdefault("source_manifest", str(mp))
            if "kind" not in e:
                e["kind"] = e.get("source_type") or "unknown"
            out.append(e)
    return out


def build_manifest(
    root: Path,
    merge_paths: list[Path] | None = None,
    *,
    rules_path: Path | None = None,
    compute_hashes: bool = True,
) -> dict[str, Any]:
    rules = _load_rules(rules_path)
    entries = scan_tree(root, rules, compute_hashes=compute_hashes)
    if merge_paths:
        entries = _merge_external(entries, merge_paths)
    return {
        "schema": "evidence-manifest/1.0",
        "root": str(root),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entries": entries,
    }


def write_manifest(manifest: dict[str, Any], out: Path) -> None:
    if yaml is None:
        raise RuntimeError("PyYAML is required to write an evidence manifest")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(manifest, sort_keys=False))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--root", type=Path, required=True, help="evidence tree to scan")
    p.add_argument("--out", type=Path, required=True, help="output manifest YAML")
    p.add_argument(
        "--merge",
        type=Path,
        action="append",
        default=[],
        help="additional manifest YAML to fold in (Phase 3B ingesters). Repeatable.",
    )
    p.add_argument(
        "--no-hash",
        action="store_true",
        help="skip SHA-256 (faster; pairs with a separate evidence_hash run)",
    )
    p.add_argument("--rules", type=Path, default=None, help="override kind_inference.yaml")
    args = p.parse_args(argv)

    if not args.root.exists():
        print(f"error: root does not exist: {args.root}", file=sys.stderr)
        return 2

    manifest = build_manifest(
        args.root,
        merge_paths=args.merge,
        rules_path=args.rules,
        compute_hashes=not args.no_hash,
    )
    write_manifest(manifest, args.out)
    kinds = sorted({e["kind"] for e in manifest["entries"]})
    print(
        f"wrote {len(manifest['entries'])} entries ({len(kinds)} kinds) to {args.out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
