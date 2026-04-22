#!/usr/bin/env python3
"""Compute a SHA-256 manifest for an evidence tree.

Usage:
    python -m scripts.evidence_hash [--root DIR] [--manifest FILE]
                                    [--config advocacy.toml]
                                    [--verify] [--check]

Modes:
    (default)  Regenerate the manifest on disk. Safe to re-run.
    --verify   Re-hash every tracked file and compare to the manifest. Exits
               non-zero on any mismatch or missing file.
    --check    Like --verify but also flags untracked files under root.

The manifest format is one line per file:
    <sha256-hex>  <relative-path>

Paths are POSIX-style, sorted, and relative to `--root`. This matches the
output shape of `shasum -a 256` / `sha256sum`, so the manifest is portable
and human-inspectable.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from fnmatch import fnmatch
from pathlib import Path

from scripts._config import Config, load_config


CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def iter_files(root: Path, exclude: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if any(fnmatch(rel, pat) or fnmatch(p.name, pat) for pat in exclude):
            continue
        out.append(p)
    return out


def build_manifest(root: Path, exclude: list[str]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for p in iter_files(root, exclude):
        rel = p.relative_to(root).as_posix()
        rows.append((sha256_file(p), rel))
    rows.sort(key=lambda r: r[1])
    return rows


def write_manifest(manifest_path: Path, rows: list[tuple[str, str]]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        for digest, rel in rows:
            fh.write(f"{digest}  {rel}\n")


def read_manifest(manifest_path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if not manifest_path.exists():
        return rows
    with open(manifest_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            # Format: "<hex>  <path>" (two spaces, matching shasum).
            if "  " not in line:
                continue
            digest, rel = line.split("  ", 1)
            rows.append((digest.strip(), rel.strip()))
    return rows


def verify(cfg: Config, *, include_untracked: bool) -> int:
    expected = {rel: digest for digest, rel in read_manifest(cfg.manifest_path)}
    if not expected:
        print(f"no manifest found at {cfg.manifest_path}", file=sys.stderr)
        return 2

    problems: list[str] = []
    seen: set[str] = set()

    for rel, want in expected.items():
        p = cfg.evidence_root / rel
        if not p.exists():
            problems.append(f"missing: {rel}")
            continue
        got = sha256_file(p)
        seen.add(rel)
        if got != want:
            problems.append(f"hash-mismatch: {rel}\n  expected {want}\n  actual   {got}")

    if include_untracked:
        for p in iter_files(cfg.evidence_root, cfg.exclude):
            rel = p.relative_to(cfg.evidence_root).as_posix()
            if rel not in expected:
                problems.append(f"untracked: {rel}")

    if problems:
        for line in problems:
            print(line, file=sys.stderr)
        return 1
    print(f"ok: {len(expected)} files verified against {cfg.manifest_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, help="Evidence root (overrides config).")
    ap.add_argument("--manifest", type=Path, help="Manifest path (overrides config).")
    ap.add_argument("--config", type=Path, help="Path to advocacy.toml.")
    ap.add_argument("--repo-root", type=Path, help="Repo root (defaults to cwd walk).")
    ap.add_argument("--verify", action="store_true", help="Verify only; do not rewrite.")
    ap.add_argument(
        "--check",
        action="store_true",
        help="Verify AND fail on untracked files under root.",
    )
    args = ap.parse_args(argv)

    cfg = load_config(repo_root=args.repo_root, config_path=args.config)
    if args.root is not None:
        cfg.evidence_root = args.root.resolve()
    if args.manifest is not None:
        cfg.manifest_path = args.manifest.resolve()

    if not cfg.evidence_root.exists():
        print(f"evidence root does not exist: {cfg.evidence_root}", file=sys.stderr)
        return 2

    if args.verify or args.check:
        return verify(cfg, include_untracked=args.check)

    rows = build_manifest(cfg.evidence_root, cfg.exclude)
    write_manifest(cfg.manifest_path, rows)
    print(f"wrote {len(rows)} entries to {cfg.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
