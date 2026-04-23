"""Unit tests for docx_edit_ops.

Covers the guardrails: find-empty, anchor-missing, find-not-in-anchor,
find-ambiguous, find-spans-runs, find-in-compound-run. Also verifies
the successful tracked-edit and silent-edit XML shapes.
"""
from __future__ import annotations

from scripts.publish.docx_edit_ops import (
    apply_silent_edit,
    apply_tracked_edit,
    count_claude_revisions,
    find_anchor_runs,
    next_revision_id,
)


def _wrap(runs_xml: str, comment_id: int = 7) -> str:
    return (
        f'<w:p>'
        f'<w:commentRangeStart w:id="{comment_id}"/>'
        f'{runs_xml}'
        f'<w:commentRangeEnd w:id="{comment_id}"/>'
        f'<w:r><w:commentReference w:id="{comment_id}"/></w:r>'
        f'</w:p>'
    )


def test_next_revision_id_empty() -> None:
    assert next_revision_id("<w:document/>") == 1


def test_next_revision_id_picks_max() -> None:
    xml = (
        '<w:document>'
        '<w:ins w:id="2" w:author="Claude" w:date="x"/>'
        '<w:del w:id="5" w:author="Claude" w:date="x"/>'
        '<w:ins w:id="3" w:author="Claude" w:date="x"/>'
        '</w:document>'
    )
    assert next_revision_id(xml) == 6


def test_find_anchor_runs_happy_path() -> None:
    doc = _wrap('<w:r><w:t>hello world</w:t></w:r>', comment_id=1)
    out = find_anchor_runs(doc, 1)
    assert out is not None
    start, end, runs = out
    assert len(runs) == 1
    assert runs[0].is_simple is True
    assert runs[0].text_escaped == "hello world"


def test_find_anchor_runs_missing() -> None:
    doc = "<w:p><w:r><w:t>no markers</w:t></w:r></w:p>"
    assert find_anchor_runs(doc, 1) is None


def test_tracked_edit_simple_replace() -> None:
    doc = _wrap('<w:r><w:t>amount: $36,321.40 shown</w:t></w:r>', comment_id=1)
    new_doc, ok, reason = apply_tracked_edit(
        doc, 1, "$36,321.40", "$36,321.00", 1, "Claude", "2026-04-22T00:00:00Z"
    )
    assert ok, reason
    assert "<w:del " in new_doc
    assert "<w:ins " in new_doc
    assert "$36,321.40" in new_doc  # still present inside <w:delText>
    assert "$36,321.00" in new_doc
    ins, dels = count_claude_revisions(new_doc)
    assert ins == 1
    assert dels == 1


def test_tracked_edit_pure_deletion() -> None:
    doc = _wrap('<w:r><w:t>keep this drop this keep</w:t></w:r>', comment_id=1)
    new_doc, ok, _ = apply_tracked_edit(
        doc, 1, " drop this", "", 1, "Claude", "2026-04-22T00:00:00Z"
    )
    assert ok
    # Pure deletion: del block present, ins block absent.
    assert "<w:del " in new_doc
    assert "<w:ins " not in new_doc


def test_tracked_edit_rejects_empty_find() -> None:
    doc = _wrap('<w:r><w:t>hello</w:t></w:r>', comment_id=1)
    _, ok, reason = apply_tracked_edit(
        doc, 1, "", "x", 1, "Claude", "t"
    )
    assert not ok
    assert reason == "find-empty"


def test_tracked_edit_rejects_missing_anchor() -> None:
    doc = "<w:p><w:r><w:t>no anchor</w:t></w:r></w:p>"
    _, ok, reason = apply_tracked_edit(
        doc, 1, "no", "yes", 1, "Claude", "t"
    )
    assert not ok
    assert reason == "anchor-markers-missing"


def test_tracked_edit_rejects_find_not_in_anchor() -> None:
    doc = _wrap('<w:r><w:t>hello world</w:t></w:r>', comment_id=1)
    _, ok, reason = apply_tracked_edit(
        doc, 1, "xyz", "abc", 1, "Claude", "t"
    )
    assert not ok
    assert reason == "find-not-in-anchor"


def test_tracked_edit_rejects_ambiguous_find() -> None:
    doc = _wrap('<w:r><w:t>cat cat cat</w:t></w:r>', comment_id=1)
    _, ok, reason = apply_tracked_edit(
        doc, 1, "cat", "dog", 1, "Claude", "t"
    )
    assert not ok
    assert reason == "find-ambiguous"


def test_tracked_edit_rejects_cross_run_find() -> None:
    doc = _wrap(
        '<w:r><w:t>hello </w:t></w:r><w:r><w:t>world</w:t></w:r>',
        comment_id=1,
    )
    _, ok, reason = apply_tracked_edit(
        doc, 1, "hello world", "hi earth", 1, "Claude", "t"
    )
    assert not ok
    assert reason == "find-spans-runs"


def test_tracked_edit_rejects_compound_run() -> None:
    # Run contains text + a tab; not simple.
    doc = _wrap(
        '<w:r><w:t>prefix</w:t><w:tab/><w:t>suffix</w:t></w:r>',
        comment_id=1,
    )
    _, ok, reason = apply_tracked_edit(
        doc, 1, "prefix", "foo", 1, "Claude", "t"
    )
    assert not ok
    assert reason == "find-in-compound-run"


def test_silent_edit_replaces_inline() -> None:
    doc = _wrap('<w:r><w:t>amount: $36,321.40 shown</w:t></w:r>', comment_id=1)
    new_doc, ok, _ = apply_silent_edit(doc, 1, "$36,321.40", "$36,321.00")
    assert ok
    assert "<w:del " not in new_doc
    assert "<w:ins " not in new_doc
    assert "$36,321.00" in new_doc
    assert "$36,321.40" not in new_doc


def test_silent_edit_preserves_rpr() -> None:
    doc = _wrap(
        '<w:r><w:rPr><w:b/></w:rPr><w:t>bold amount 100 here</w:t></w:r>',
        comment_id=1,
    )
    new_doc, ok, _ = apply_silent_edit(doc, 1, "100", "250")
    assert ok
    assert "<w:rPr><w:b/></w:rPr>" in new_doc
