"""Shared helpers for scripts/intake/*.

Kept tiny: load data/*.yaml relative to repo root, with a small fallback
YAML parser import pattern that matches the rest of the codebase.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

DISCLAIMER = "This is reference information, not legal advice."


def find_repo_root(start: Path | None = None) -> Path:
    """Walk upward looking for a repo marker (pyproject.toml / .git)."""
    cur = (start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            return candidate
    return cur


def data_dir(root: Path | None = None) -> Path:
    return find_repo_root(root) / "data"


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file. PyYAML is a declared dep (see pyproject.toml)."""
    import yaml  # type: ignore

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"expected top-level mapping in {path}, got {type(data).__name__}")
    return data
