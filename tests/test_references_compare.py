"""Tests for scripts.references.compare."""
from __future__ import annotations

from scripts.references import compare


def _sidecar(source_id: str, sha: str, readable: str) -> dict:
    return {
        "source_id": source_id,
        "source_sha256": sha,
        "source_origin": "fetched",
        "source_url": "https://example.gov/x",
        "fetched_at": "2026-04-30T00:00:00+00:00",
        "readable_path": readable,
        "citation": "C",
        "kind": "statute",
        "jurisdiction": "MD",
    }


def test_hash_equal_collapse() -> None:
    a = _sidecar("aa", "sha-a", "references/readable/a.txt")
    b = _sidecar("aa", "sha-a", "references/readable/b.txt")
    text = "Same body."
    report = compare.compare(a, b, text_a=text, text_b=text)
    assert report["raw_sha256_equal"]
    assert report["readable_text_equal"]
    assert report["diff_lines"] == []


def test_hash_differ_text_differ() -> None:
    a = _sidecar("aa", "sha-a", "references/readable/a.txt")
    b = _sidecar("bb", "sha-b", "references/readable/b.txt")
    text_a = "(a) The text reads thus.\n(b) Effective date 2017."
    text_b = "(a) The text reads thus, with edits.\n(b) Effective date 2017."
    report = compare.compare(a, b, text_a=text_a, text_b=text_b)
    assert not report["raw_sha256_equal"]
    assert not report["readable_text_equal"]
    assert report["char_delta"] == len(text_b) - len(text_a)
    assert any("with edits" in line for line in report["diff_lines"])


def test_hash_differ_text_equal() -> None:
    """PDF vs HTML containers can have the same extracted text."""
    a = _sidecar("aa", "sha-a", "references/readable/a.txt")
    b = _sidecar("bb", "sha-b", "references/readable/b.txt")
    text = "Identical extracted text."
    report = compare.compare(a, b, text_a=text, text_b=text)
    assert not report["raw_sha256_equal"]
    assert report["readable_text_equal"]


def test_render_markdown_includes_disclaimer_and_verdict() -> None:
    a = _sidecar("aa", "sha-a", "references/readable/a.txt")
    b = _sidecar("aa", "sha-a", "references/readable/b.txt")
    report = compare.compare(a, b, text_a="X", text_b="X")
    md = compare.render_markdown(report)
    assert "This is reference information, not legal advice." in md
    assert "byte-identical" in md


def test_render_markdown_warns_on_mismatched_citation() -> None:
    a = _sidecar("aa", "sha-a", "references/readable/a.txt")
    b = dict(_sidecar("bb", "sha-b", "references/readable/b.txt"))
    b["citation"] = "Different Citation"
    report = compare.compare(a, b, text_a="X", text_b="Y")
    md = compare.render_markdown(report)
    assert "different citations" in md
