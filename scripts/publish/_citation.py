"""Citation footer formatting for specialist replies.

The `docx-comment-roundtrip` skill requires every factual / analysis
specialist reply that cites a project source to end with a citation
footer of the form:

    Source: <path>:<line>  sha256=<hex>@<provenance>

Where <provenance> is:

    git:<short-sha>                 — tracked and clean
    git:<short-sha>+uncommitted     — tracked with uncommitted changes
    mtime:<ISO-8601>                — not git-tracked (free file on disk)

Sources outside the repository root are refused — advocacy-toolkit
thesis is that every cited source should be under provenance control.
"""
from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path


class CitationError(Exception):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_short_sha(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _git_file_is_tracked_and_clean(
    repo_root: Path, rel_path: Path
) -> tuple[bool, bool]:
    """Return (is_tracked, is_clean)."""
    try:
        ls = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "--error-unmatch",
             str(rel_path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, False
    if ls.returncode != 0:
        return False, False
    try:
        status = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain",
             str(rel_path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return True, False
    return True, status.stdout.strip() == ""


def format_citation(
    path: Path,
    *,
    repo_root: Path,
    line: int | str | None = None,
) -> str:
    """Build a `Source: <path>:<line>  sha256=<hex>@<provenance>` footer.

    Raises CitationError if path is outside repo_root.
    """
    path = path.resolve()
    repo_root = repo_root.resolve()
    try:
        rel = path.relative_to(repo_root)
    except ValueError as exc:
        raise CitationError(
            f"refusing to cite {path}: outside project root {repo_root}. "
            "Copy the file into the repo before citing."
        ) from exc
    if not path.exists():
        raise CitationError(f"cannot cite missing file: {path}")

    digest = _sha256(path)
    is_tracked, is_clean = _git_file_is_tracked_and_clean(repo_root, rel)
    if is_tracked:
        short = _git_short_sha(repo_root)
        if short is None:
            provenance = "git:unknown"
        elif is_clean:
            provenance = f"git:{short}"
        else:
            provenance = f"git:{short}+uncommitted"
    else:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        provenance = f"mtime:{mtime.strftime('%Y-%m-%dT%H:%M:%SZ')}"

    locator = f":{line}" if line is not None else ""
    return f"Source: {rel.as_posix()}{locator}  sha256={digest}@{provenance}"


# Regex patterns the driver uses to validate citation footers in
# specialist output. Any non-trivial reply that mentions a file path must
# include at least one matching footer line.
CITATION_LINE_RE = (
    r"Source: \S+(?::\S+)?\s+sha256=[0-9a-f]{64}@"
    r"(?:git:[0-9a-f]+(?:\+uncommitted)?|git:unknown|mtime:[0-9T:\-Z]+)"
)

# Heuristic: a reply "cites a file path" if it contains a slash followed
# by a filename with a common extension. Keep the allowlist tight — if
# we expand it, verify in docx_apply_replies.CITATION_PATHS updates too.
FILE_PATH_RE = r"[\w./\-]+\.(?:md|pdf|docx|txt|json|yaml|yml|csv|html?)"
