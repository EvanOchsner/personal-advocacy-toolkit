#!/usr/bin/env python3
"""Pre-commit hook enforcing evidence-tree immutability.

The hook refuses to let a commit land if it would:

1. Modify or delete any file under a path listed in
   `hooks.protected_paths` (config-driven, no `evidence/` hardcoding).
2. Modify the hash manifest without a corresponding manifest regeneration
   (when `hooks.enforce_manifest_consistency` is True).

Override: setting `ADVOCACY_ALLOW_EVIDENCE_MUTATION=1` in the environment
skips check #1 for one commit. This is intentionally loud — the env var
name, not a `--force` flag, so the act of overriding is visible in shell
history or CI logs.

Usage:
    python -m scripts.hooks.pre_commit           # invoked from .git/hooks
    python -m scripts.hooks.pre_commit --staged  # explicit (default)

The hook reads staged file changes from `git diff --cached --name-status`,
so it is safe to invoke from any git hook entry point.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from scripts._config import load_config


ALLOW_ENV = "ADVOCACY_ALLOW_EVIDENCE_MUTATION"


def staged_changes(repo_root: Path) -> list[tuple[str, str]]:
    """Return list of (status, path) for files staged in the index."""
    res = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "--cached", "--name-status"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        return []
    rows: list[tuple[str, str]] = []
    for line in res.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        # Renames: "R100\told\tnew" — treat as (D, old) + (A, new).
        if status.startswith("R") and len(parts) == 3:
            rows.append(("D", parts[1]))
            rows.append(("A", parts[2]))
        elif len(parts) >= 2:
            rows.append((status, parts[1]))
    return rows


def is_under(path: str, protected: list[str]) -> bool:
    p = Path(path).as_posix().rstrip("/")
    for base in protected:
        b = Path(base).as_posix().rstrip("/")
        if p == b or p.startswith(b + "/"):
            return True
    return False


def check(repo_root: Path) -> int:
    cfg = load_config(repo_root=repo_root)
    allow = os.environ.get(ALLOW_ENV) == "1"

    changes = staged_changes(cfg.repo_root)
    if not changes:
        return 0

    violations: list[str] = []
    manifest_rel = None
    try:
        manifest_rel = cfg.manifest_path.relative_to(cfg.repo_root).as_posix()
    except ValueError:
        manifest_rel = None

    manifest_touched = False
    protected_touched = False

    for status, path in changes:
        if manifest_rel and path == manifest_rel:
            manifest_touched = True
            continue
        if not is_under(path, cfg.protected_paths):
            continue
        # Any touch under a protected path (incl. additions) is relevant to
        # the manifest-consistency check.
        protected_touched = True
        # Additions are allowed; modifications and deletions are not
        # (unless overridden).
        if status.startswith("A"):
            continue
        if not allow:
            violations.append(f"  {status}\t{path}")

    if violations:
        joined = "\n".join(violations)
        print(
            "advocacy-toolkit pre-commit: refusing commit.\n"
            "The following staged changes would modify or delete files under a\n"
            f"protected path ({', '.join(cfg.protected_paths)}):\n\n{joined}\n\n"
            f"If this is truly intentional (e.g. redaction with notice), re-run the\n"
            f"commit with {ALLOW_ENV}=1 set. That override is loud by design.",
            file=sys.stderr,
        )
        return 1

    if (
        cfg.enforce_manifest_consistency
        and protected_touched
        and not manifest_touched
    ):
        print(
            "advocacy-toolkit pre-commit: protected-path additions were staged but\n"
            f"the hash manifest ({manifest_rel}) was not updated. Run\n"
            "  python -m scripts.evidence_hash\n"
            "and re-stage the manifest before committing.",
            file=sys.stderr,
        )
        return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, help="Repo root (defaults to cwd walk).")
    ap.add_argument(
        "--staged",
        action="store_true",
        help="Check staged changes (the default and only mode).",
    )
    args = ap.parse_args(argv)
    repo_root = args.repo_root or Path.cwd()
    return check(repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
