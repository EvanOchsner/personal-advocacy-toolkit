#!/usr/bin/env python3
"""Wrap `git filter-repo` with a substitutions file and a post-check.

Usage:
    python -m scripts.publish.history_sanitizer \\
        --scratch-dir /abs/path/to/fresh-clone \\
        --substitutions substitutions.yaml

Safety rails:
    - This tool is destructive: `git filter-repo` rewrites history.
    - It REFUSES to run unless `--scratch-dir` points to a directory that:
        * exists
        * is a git repo
        * is NOT the caller's cwd (you must clone into a scratch path first)
    - All shell calls use `subprocess.run(..., shell=False)` with argv lists
      — no string interpolation into a shell. Substitution replacements are
      written to a temp expressions file, not passed on argv.

Post-check (mandatory):
    After filter-repo completes, walk every blob in the rewritten repo
    (`git rev-list --all` → `git ls-tree -r` → `git cat-file blob`) and
    search for any banned term. If any term survives in any blob, exit
    non-zero with the offending commit + path + term hash. The calling
    workflow must treat a non-zero exit as "do NOT push this scratch repo
    anywhere."
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.publish._substitutions import load_substitutions


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _run(argv: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    """Safe subprocess runner — shell=False, argv list only, no string interp."""
    return subprocess.run(argv, cwd=str(cwd), check=check, capture_output=True)


def _is_git_repo(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        cp = _run(["git", "rev-parse", "--git-dir"], cwd=path, check=False)
    except FileNotFoundError:
        return False
    return cp.returncode == 0


def _scratch_is_safe(scratch_dir: Path, caller_cwd: Path) -> None:
    """Raise if scratch_dir is the caller's repo itself."""
    scratch_resolved = scratch_dir.resolve()
    caller_resolved = caller_cwd.resolve()
    if scratch_resolved == caller_resolved:
        raise RuntimeError(
            "refusing to operate on caller's own checkout; "
            "--scratch-dir must point to a fresh clone at a different path."
        )
    # Also refuse if the caller is inside the scratch (or vice versa).
    try:
        caller_resolved.relative_to(scratch_resolved)
        raise RuntimeError(
            "refusing: caller cwd is inside the scratch dir. "
            "Run this tool from outside the scratch clone."
        )
    except ValueError:
        pass


def _write_expressions_file(subs_map: dict[str, str], path: Path) -> None:
    """git filter-repo --replace-text expressions format.

    Each non-blank line is either:
        LITERAL==>REPLACEMENT
        regex:PATTERN==>REPLACEMENT

    We write LITERAL lines only — users who want regex should add them
    explicitly and we write them through. To keep the writer dumb, we treat
    every key as a literal.
    """
    lines: list[str] = []
    for key, val in subs_map.items():
        if "\n" in key or "\n" in val:
            raise ValueError(f"substitution contains newline; refusing: {key!r}")
        if "==>" in key:
            raise ValueError(f"substitution key contains '==>'; refusing: {key!r}")
        lines.append(f"literal:{key}==>{val}\n")
    path.write_text("".join(lines), encoding="utf-8")


def _all_blob_ids(repo: Path) -> list[tuple[str, str, str]]:
    """Return [(commit, path, blob_sha)] across every commit in the rewritten repo."""
    out: list[tuple[str, str, str]] = []
    cp = _run(["git", "rev-list", "--all"], cwd=repo)
    for commit in cp.stdout.decode("utf-8", errors="replace").splitlines():
        commit = commit.strip()
        if not commit:
            continue
        tree_cp = _run(["git", "ls-tree", "-r", commit], cwd=repo)
        for line in tree_cp.stdout.decode("utf-8", errors="replace").splitlines():
            # "<mode> blob <sha>\t<path>"
            if "\tblob " in line or " blob " in line:
                parts = line.split("\t", 1)
                if len(parts) != 2:
                    continue
                meta, path = parts
                fields = meta.split()
                if len(fields) >= 3 and fields[1] == "blob":
                    out.append((commit, path, fields[2]))
    return out


def _scan_blobs_for_banned(
    repo: Path, banned_terms: list[str]
) -> list[tuple[str, str, str, str]]:
    """Return [(commit, path, blob_sha, sha256_of_term)] for every surviving hit."""
    survivors: list[tuple[str, str, str, str]] = []
    seen_blobs: set[str] = set()
    for commit, path, blob in _all_blob_ids(repo):
        if blob in seen_blobs:
            # Same blob can appear in many commits; scan once.
            continue
        seen_blobs.add(blob)
        try:
            cp = _run(["git", "cat-file", "blob", blob], cwd=repo, check=False)
        except FileNotFoundError:
            continue
        if cp.returncode != 0:
            continue
        data = cp.stdout
        # Decode best-effort; a banned term that's a string literal should
        # survive latin-1 round-trip for ASCII content.
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1", errors="replace")
        for term in banned_terms:
            if term and term in text:
                survivors.append((commit, path, blob, _sha(term)))
    return survivors


def sanitize(
    scratch_dir: Path,
    subs_path: Path,
    *,
    caller_cwd: Path | None = None,
) -> list[tuple[str, str, str, str]]:
    """Run the full sanitize + post-check. Returns survivor list (empty = clean)."""
    caller_cwd = caller_cwd or Path.cwd()
    _scratch_is_safe(scratch_dir, caller_cwd)
    if not _is_git_repo(scratch_dir):
        raise RuntimeError(f"--scratch-dir is not a git repo: {scratch_dir}")

    subs = load_substitutions(subs_path)

    # Write expressions to a temp file (never interpolated into a shell).
    with tempfile.TemporaryDirectory() as td:
        expr_path = Path(td) / "replace-text.txt"
        _write_expressions_file(subs.mapping, expr_path)

        # Invoke filter-repo. We use `--force` because the scratch repo
        # is already a fresh clone by contract.
        cp = _run(
            [
                "git",
                "filter-repo",
                "--force",
                "--replace-text",
                str(expr_path),
            ],
            cwd=scratch_dir,
            check=False,
        )
        if cp.returncode != 0:
            raise RuntimeError(
                f"git filter-repo failed (rc={cp.returncode}): "
                f"{cp.stderr.decode('utf-8', errors='replace')}"
            )

    # Post-check.
    survivors = _scan_blobs_for_banned(scratch_dir, subs.banned_terms)
    return survivors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--scratch-dir",
        type=Path,
        required=True,
        help="Path to a fresh clone (NOT the caller's working tree).",
    )
    ap.add_argument("--substitutions", type=Path, required=True)
    args = ap.parse_args(argv)

    try:
        survivors = sanitize(args.scratch_dir, args.substitutions)
    except RuntimeError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2

    if survivors:
        print(
            f"POST-CHECK FAIL: {len(survivors)} banned-term hits in rewritten history. "
            "Do NOT push this scratch repo.",
            file=sys.stderr,
        )
        for commit, path, blob, term_sha in survivors[:20]:
            print(f"  {commit[:12]} {path} blob={blob[:12]} term_sha256={term_sha}", file=sys.stderr)
        return 1

    print(f"history sanitized + post-check clean: {args.scratch_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
