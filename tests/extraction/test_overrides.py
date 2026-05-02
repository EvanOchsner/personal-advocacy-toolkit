"""ExtractionOverrides — sidecar loading and apply semantics.

The override sidecar is the manual escape hatch. Tests cover (a) the
parser is forgiving about missing/malformed input and (b) overrides
that survive parsing produce the documented effects.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.extraction.overrides import (
    ExtractionOverrides,
    load_overrides,
    overrides_path,
)


def test_overrides_path_is_under_case_extraction_overrides(tmp_path: Path) -> None:
    p = overrides_path(tmp_path, "abc123")
    assert p == tmp_path / "extraction" / "overrides" / "abc123.yaml"


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    ovr = load_overrides(tmp_path / "no-such.yaml")
    assert ovr.is_empty()
    assert ovr.force_tier is None


def test_load_json_sidecar(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    p.write_text(
        json.dumps(
            {
                "source_id": "abc",
                "file": "evidence/foo.pdf",
                "overrides": {
                    "skip_pages": [1, 14],
                    "strip_text_patterns": ["CONFIDENTIAL", r"Page \d+ of \d+"],
                    "force_tier": 2,
                    "vlm_provider": "olmocr",
                    "garble_thresholds": {"min_chars_per_page": 30},
                    "notes": "watermark",
                },
            }
        ),
        encoding="utf-8",
    )
    ovr = load_overrides(p)
    assert ovr.source_id == "abc"
    assert ovr.skip_pages == [1, 14]
    assert ovr.strip_text_patterns == ["CONFIDENTIAL", r"Page \d+ of \d+"]
    assert ovr.force_tier == 2
    assert ovr.vlm_provider == "olmocr"
    assert ovr.garble_thresholds == {"min_chars_per_page": 30.0}
    assert ovr.notes == "watermark"
    assert not ovr.is_empty()


def test_load_yaml_sidecar(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    p = tmp_path / "x.yaml"
    p.write_text(
        "source_id: zzz\n"
        "overrides:\n"
        "  skip_pages: [3]\n"
        "  vlm_provider: tesseract\n",
        encoding="utf-8",
    )
    ovr = load_overrides(p)
    assert ovr.source_id == "zzz"
    assert ovr.skip_pages == [3]
    assert ovr.vlm_provider == "tesseract"


def test_load_yaml_with_malformed_yaml_returns_empty(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    p = tmp_path / "bad.yaml"
    p.write_text("nope: this is: malformed:\n  - [unclosed", encoding="utf-8")
    ovr = load_overrides(p)
    assert ovr.is_empty()


def test_load_json_with_malformed_json_returns_empty(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{nope}", encoding="utf-8")
    ovr = load_overrides(p)
    assert ovr.is_empty()


def test_unrecognized_field_types_are_skipped_not_crashed(tmp_path: Path) -> None:
    p = tmp_path / "loose.json"
    p.write_text(
        json.dumps(
            {
                "source_id": "abc",
                "overrides": {
                    "skip_pages": ["one", 2, None, "3"],   # mixed: only ints + numeric strings keep
                    "crop_boxes": {"3": [10, 20, 30, 40], "bad": "no"},
                    "vlm_provider": 12345,                  # wrong type → ignored
                    "force_tier": "definitely not an int",  # wrong type → None
                    "garble_thresholds": {"min_chars_per_page": "wat"},  # wrong → skipped
                },
            }
        ),
        encoding="utf-8",
    )
    ovr = load_overrides(p)
    assert ovr.skip_pages == [2, 3]                         # "one" and None dropped
    assert ovr.crop_boxes == {3: (10.0, 20.0, 30.0, 40.0)}  # bad key dropped
    assert ovr.vlm_provider is None
    assert ovr.force_tier is None
    assert ovr.garble_thresholds == {}


def test_apply_text_strip_uses_regex() -> None:
    ovr = ExtractionOverrides(
        strip_text_patterns=["CONFIDENTIAL — DO NOT DISTRIBUTE", r"Page \d+ of \d+"]
    )
    out = ovr.apply_text_strip(
        "CONFIDENTIAL — DO NOT DISTRIBUTE\nReal body.\nPage 3 of 17"
    )
    assert "CONFIDENTIAL" not in out
    assert "Page 3 of 17" not in out
    assert "Real body." in out


def test_apply_text_strip_no_patterns_is_no_op() -> None:
    ovr = ExtractionOverrides()
    text = "anything goes"
    assert ovr.apply_text_strip(text) == text


def test_apply_text_strip_falls_back_on_invalid_regex() -> None:
    # An invalid regex should fall through to literal replace, not crash.
    ovr = ExtractionOverrides(strip_text_patterns=["[unclosed"])
    out = ovr.apply_text_strip("foo [unclosed bar")
    assert "[unclosed" not in out
    assert "foo " in out and "bar" in out


def test_to_dict_round_trip_only_includes_set_fields() -> None:
    ovr = ExtractionOverrides(skip_pages=[1], notes="x")
    d = ovr.to_dict()
    assert d == {"skip_pages": [1], "notes": "x"}
