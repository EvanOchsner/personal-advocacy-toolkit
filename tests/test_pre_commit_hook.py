"""Smoke tests for scripts.hooks.pre_commit.

Uses a real, isolated git repo under tmp_path — no network, no fixtures
outside the test.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from scripts.hooks import pre_commit


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
        env=full_env,
    )


def _have_git() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


pytestmark = pytest.mark.skipif(not _have_git(), reason="git not available")


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "Test")
    # advocacy.toml: protect `evidence/`.
    (repo / "advocacy.toml").write_text(
        '[hooks]\n'
        'protected_paths = ["evidence"]\n'
        'enforce_manifest_consistency = false\n'
        '[evidence]\n'
        'root = "evidence"\n'
        'manifest = "evidence/MANIFEST.sha256"\n'
    )
    (repo / "evidence").mkdir()
    (repo / "evidence" / "a.txt").write_bytes(b"original")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    return repo


def test_addition_allowed(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "evidence" / "new.txt").write_bytes(b"new file")
    _git(repo, "add", "evidence/new.txt")
    rc = pre_commit.check(repo)
    assert rc == 0


def test_modification_blocked(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "evidence" / "a.txt").write_bytes(b"tampered")
    _git(repo, "add", "evidence/a.txt")
    rc = pre_commit.check(repo)
    assert rc == 1


def test_deletion_blocked(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "evidence" / "a.txt").unlink()
    _git(repo, "add", "-A")
    rc = pre_commit.check(repo)
    assert rc == 1


def test_override_env_allows_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _init_repo(tmp_path)
    (repo / "evidence" / "a.txt").write_bytes(b"tampered")
    _git(repo, "add", "evidence/a.txt")
    monkeypatch.setenv(pre_commit.ALLOW_ENV, "1")
    rc = pre_commit.check(repo)
    assert rc == 0


def test_unprotected_path_unaffected(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "notes.md").write_text("hello")
    _git(repo, "add", "notes.md")
    rc = pre_commit.check(repo)
    assert rc == 0


def test_manifest_consistency_enforced(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    # Flip the consistency flag on.
    (repo / "advocacy.toml").write_text(
        '[hooks]\n'
        'protected_paths = ["evidence"]\n'
        'enforce_manifest_consistency = true\n'
        '[evidence]\n'
        'root = "evidence"\n'
        'manifest = "evidence/MANIFEST.sha256"\n'
    )
    # Stage a new evidence file WITHOUT updating manifest.
    (repo / "evidence" / "new.txt").write_bytes(b"added")
    _git(repo, "add", "evidence/new.txt")
    rc = pre_commit.check(repo)
    assert rc == 1

    # Now also stage a manifest update — should pass.
    (repo / "evidence" / "MANIFEST.sha256").write_text("fake-digest  new.txt\n")
    _git(repo, "add", "evidence/MANIFEST.sha256")
    rc = pre_commit.check(repo)
    assert rc == 0
