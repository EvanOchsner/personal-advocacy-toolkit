"""Init_case must create the references/ tree."""
from __future__ import annotations

from pathlib import Path

from scripts import init_case


def test_create_tree_includes_references_dirs(tmp_path: Path) -> None:
    case = tmp_path / "case"
    case.mkdir()
    dirs = init_case._create_tree(case)
    for sub in ("references/raw", "references/structured", "references/readable"):
        assert (case / sub).is_dir()
        assert sub in dirs
    # The README is dropped explaining the layout.
    readme = case / "references" / "README.md"
    assert readme.is_file()
    body = readme.read_text(encoding="utf-8")
    assert "trusted reference documents" in body.lower()


def test_create_tree_includes_notes_references_dir(tmp_path: Path) -> None:
    case = tmp_path / "case"
    case.mkdir()
    init_case._create_tree(case)
    assert (case / "notes" / "references").is_dir()
