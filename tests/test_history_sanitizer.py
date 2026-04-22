"""Tests for scripts.publish.history_sanitizer.

We skip the actual `git filter-repo` invocation if the binary isn't
installed (it's a separate tool, not a Python dep). The critical
unit-testable pieces are:

  1) Scratch-dir safety rails (refuses caller's cwd).
  2) Expressions-file writer (no shell injection, newline-safe).
  3) Blob-scanning post-check — inject a blob that contains a banned
     literal and verify it's detected across every commit that references
     the blob.

For (3) we do NOT need filter-repo: we build a tiny repo, commit a blob
with a banned term, then call the post-check directly. That's the part
that matters — filter-repo is just the rewriter; the post-check is the
safety net.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.publish import history_sanitizer as hs  # noqa: E402


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def _git_env_init(repo: Path) -> None:
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Tester", cwd=repo)
    _git("config", "commit.gpgsign", "false", cwd=repo)


def _has_git() -> bool:
    return shutil.which("git") is not None


pytestmark = pytest.mark.skipif(not _has_git(), reason="git binary not available")


def test_refuses_caller_cwd(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_env_init(repo)
    (repo / "a.txt").write_text("hello")
    _git("add", "a.txt", cwd=repo)
    _git("commit", "-q", "-m", "initial", cwd=repo)

    subs = tmp_path / "subs.yaml"
    subs.write_text("substitutions: {}\n")

    with pytest.raises(RuntimeError, match="caller"):
        hs.sanitize(repo, subs, caller_cwd=repo)


def test_refuses_non_repo(tmp_path: Path) -> None:
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    subs = tmp_path / "subs.yaml"
    subs.write_text("substitutions: {}\n")
    with pytest.raises(RuntimeError, match="not a git repo"):
        hs.sanitize(plain, subs, caller_cwd=tmp_path)


def test_expressions_file_format(tmp_path: Path) -> None:
    path = tmp_path / "exprs.txt"
    hs._write_expressions_file({"John Doe": "John Synthetic", "555-123-4567": "555-000-0000"}, path)
    content = path.read_text()
    assert "literal:John Doe==>John Synthetic" in content
    assert "literal:555-123-4567==>555-000-0000" in content


def test_expressions_rejects_newlines(tmp_path: Path) -> None:
    path = tmp_path / "exprs.txt"
    with pytest.raises(ValueError, match="newline"):
        hs._write_expressions_file({"bad\nkey": "x"}, path)


def test_expressions_rejects_embedded_separator(tmp_path: Path) -> None:
    path = tmp_path / "exprs.txt"
    with pytest.raises(ValueError, match="==>"):
        hs._write_expressions_file({"a==>b": "x"}, path)


def test_post_check_scans_all_blobs_for_banned_term(tmp_path: Path) -> None:
    """The heart of the safety net. We commit a blob containing a banned
    literal, then call the post-check on the repo and verify the term is
    reported — even though the commit is reachable from HEAD and the blob
    is a normal blob, not a 'secret' anywhere special."""
    repo = tmp_path / "scratch"
    repo.mkdir()
    _git_env_init(repo)

    leaked = repo / "notes.txt"
    leaked.write_text("Reminder: contact John Doe at jdoe@example.com.\n")
    _git("add", "notes.txt", cwd=repo)
    _git("commit", "-q", "-m", "add notes", cwd=repo)

    # Simulate a partial scrub: rewrite HEAD file but leave the blob in
    # history (this is the exact failure mode filter-repo protects
    # against; we want to prove the post-check catches it when the
    # rewrite was incomplete).
    leaked.write_text("Reminder: contact [REDACTED] at [REDACTED].\n")
    _git("add", "notes.txt", cwd=repo)
    _git("commit", "-q", "-m", "partial scrub", cwd=repo)

    survivors = hs._scan_blobs_for_banned(repo, ["John Doe", "jdoe@example.com"])
    # Both banned terms survive in the earlier commit's blob.
    terms_found = {row[0] for row in survivors}  # commit shas
    assert len(survivors) >= 2, f"expected survivors from earlier commit, got {survivors}"


def test_post_check_clean_repo(tmp_path: Path) -> None:
    repo = tmp_path / "clean"
    repo.mkdir()
    _git_env_init(repo)
    (repo / "a.txt").write_text("nothing sensitive here\n")
    _git("add", "a.txt", cwd=repo)
    _git("commit", "-q", "-m", "init", cwd=repo)

    survivors = hs._scan_blobs_for_banned(repo, ["John Doe", "ACME-SECRET"])
    assert survivors == []
