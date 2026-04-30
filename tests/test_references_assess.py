"""Tests for scripts.references.assess."""
from __future__ import annotations

from scripts.references import assess


COMPLETE_STATUTE = """\
§ 27-303. Unfair claim settlement practices.

(a) In general. — A person may not engage in any of the following practices
in the business of insurance:

  (1) misrepresenting pertinent facts or policy provisions that relate
      to the claim or coverage at issue;
  (2) failing to acknowledge and act with reasonable promptness on
      communications about claims arising under policies;
  (3) failing to adopt and implement reasonable standards for the prompt
      investigation of claims arising under policies; or
  (4) refusing to pay a claim without conducting a reasonable
      investigation based on all available information.

(b) Effective date. — This section is effective as of October 1, 2017.
"""

EXCERPT = """EXCERPT — § 27-303. Unfair claims..."""

TRUNCATED = """\
§ 27-303. Unfair claim settlement practices.
(a) In general. A person may not engage in any of the following
practices in the business of insurance, including but not limited to
misrepresenting pertinent facts or policy provisions that relate to
the claim or coverage at issue, and"""


def test_complete_statute_passes() -> None:
    a = assess.assess(COMPLETE_STATUTE, kind="statute")
    assert a.appears_complete
    warns = [f for f in a.flags if f.level == "warn"]
    assert warns == []


def test_excerpt_flagged() -> None:
    a = assess.assess(EXCERPT, kind="statute")
    codes = {f.code for f in a.flags}
    assert "looks-like-excerpt" in codes


def test_truncation_flagged() -> None:
    a = assess.assess(TRUNCATED, kind="statute")
    codes = {f.code for f in a.flags}
    assert "truncation-suspected" in codes


def test_short_for_kind_flagged() -> None:
    a = assess.assess("Section 1. Short.", kind="statute")
    codes = {f.code for f in a.flags}
    assert "short-for-kind" in codes


def test_no_section_numbers_flagged_for_statute() -> None:
    a = assess.assess(
        "This is a long paragraph of text without any section markers. " * 30,
        kind="statute",
    )
    codes = {f.code for f in a.flags}
    assert "no-section-numbers" in codes


def test_no_section_numbers_not_flagged_for_tos() -> None:
    a = assess.assess(
        "This is a long paragraph of TOS text without any section markers. " * 30,
        kind="tos",
    )
    codes = {f.code for f in a.flags}
    assert "no-section-numbers" not in codes


def test_watermark_flagged_as_info() -> None:
    text = COMPLETE_STATUTE + "\nDRAFT — internal review only.\n"
    a = assess.assess(text, kind="statute")
    flag = next(f for f in a.flags if f.code == "has-watermark")
    assert flag.level == "info"


def test_no_effective_date_flagged_as_info() -> None:
    text = "§ 1. " + ("blah blah. " * 100)
    a = assess.assess(text, kind="statute")
    flag = next(f for f in a.flags if f.code == "no-effective-date")
    assert flag.level == "info"


def test_empty_text_marked_incomplete() -> None:
    a = assess.assess("", kind="statute")
    assert not a.appears_complete
    assert any(f.code == "empty" for f in a.flags)


def test_truncation_marker_flag() -> None:
    text = (COMPLETE_STATUTE + "\n[truncated]\n").replace(
        "(b) Effective date.", "[...]"
    )
    a = assess.assess(text, kind="statute")
    codes = {f.code for f in a.flags}
    assert "has-truncation-marker" in codes
