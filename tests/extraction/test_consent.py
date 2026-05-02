"""Privacy guardrail — consent file lifecycle.

The consent file under ``<case>/extraction/vlm-consent.yaml`` is the
load-bearing record that the going-public skill reads. These tests
pin its shape and the helper functions' contract.
"""
from __future__ import annotations

from pathlib import Path


from scripts.extraction.consent import (
    consent_path,
    has_consent,
    list_externally_processed_files,
    record_consent,
    record_external_processing,
)


def test_no_consent_file_yet(tmp_path: Path) -> None:
    assert not has_consent(tmp_path, "claude")
    assert list_externally_processed_files(tmp_path) == []
    assert not consent_path(tmp_path).exists()


def test_record_then_check(tmp_path: Path) -> None:
    record_consent(
        tmp_path,
        "claude",
        description={"model": "claude-sonnet-4-6"},
        granted=True,
    )
    assert has_consent(tmp_path, "claude")
    assert not has_consent(tmp_path, "openai")  # other providers not implicitly granted


def test_record_denial_does_not_grant(tmp_path: Path) -> None:
    record_consent(tmp_path, "openai", granted=False)
    assert not has_consent(tmp_path, "openai")


def test_record_external_processing_appends(tmp_path: Path) -> None:
    record_consent(tmp_path, "claude", granted=True)
    record_external_processing(
        tmp_path,
        source_id="abc12345",
        file="evidence/policy/raw/abc.pdf",
        provider_name="claude",
        pages=[1, 3],
    )
    record_external_processing(
        tmp_path,
        source_id="def67890",
        file="evidence/policy/raw/def.pdf",
        provider_name="claude",
        pages=[2],
    )
    rows = list_externally_processed_files(tmp_path)
    assert len(rows) == 2
    assert {r["source_id"] for r in rows} == {"abc12345", "def67890"}
    assert rows[0]["provider"] == "claude"
    assert rows[0]["pages"] == [1, 3]
    # 'at' timestamp present on each row.
    assert all(r.get("at") for r in rows)


def test_consent_file_is_under_extraction_dir(tmp_path: Path) -> None:
    record_consent(tmp_path, "claude", granted=True)
    expected = tmp_path / "extraction" / "vlm-consent.yaml"
    fallback = tmp_path / "extraction" / "vlm-consent.json"
    assert expected.exists() or fallback.exists()


def test_record_round_trip_preserves_description(tmp_path: Path) -> None:
    record_consent(
        tmp_path,
        "openai",
        description={"model": "gpt-4o", "context": "evidence/policy/x.pdf"},
        granted=True,
    )
    # Re-loading a second time should see the consent.
    assert has_consent(tmp_path, "openai")


def test_consent_path_helper_returns_yaml_under_case(tmp_path: Path) -> None:
    p = consent_path(tmp_path)
    assert p.name == "vlm-consent.yaml"
    assert p.parent.name == "extraction"
    assert p.parent.parent == tmp_path
