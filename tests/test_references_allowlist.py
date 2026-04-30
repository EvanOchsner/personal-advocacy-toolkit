"""Tests for scripts.references._allowlist."""
from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from scripts.references import _allowlist


SAMPLE = """\
schema_version: "0.1"
allowlist_domains:
  - { domain: "*.gov",          trust: "primary" }
  - { domain: "law.cornell.edu", trust: "secondary-trusted" }
  - { domain: "web.archive.org", trust: "secondary-confirm" }
denylist_domains:
  - { domain: "*.wikipedia.org", reason: "secondary aggregator" }
source_directory:
  statute:
    federal:
      label: "Federal statutes"
      sources:
        - { name: "GovInfo", url: "https://www.govinfo.gov/" }
    "MD":
      label: "Maryland statutes"
      sources:
        - { name: "MGA", url: "https://mgaleg.maryland.gov/" }
  tos:
    "*":
      label: "Terms of Service"
      sources:
        - { name: "Platform legal page", url: "" }
"""


@pytest.fixture
def yaml_path(tmp_path: Path) -> Path:
    p = tmp_path / "reference_sources.yaml"
    p.write_text(SAMPLE)
    return p


def test_classify_primary(yaml_path: Path) -> None:
    cls = _allowlist.classify("www.govinfo.gov", source_path=yaml_path)
    assert cls.verdict == "primary"
    assert cls.matched_pattern == "*.gov"


def test_classify_secondary_trusted(yaml_path: Path) -> None:
    cls = _allowlist.classify("law.cornell.edu", source_path=yaml_path)
    assert cls.verdict == "secondary-trusted"


def test_classify_denied_takes_precedence(yaml_path: Path) -> None:
    cls = _allowlist.classify("en.wikipedia.org", source_path=yaml_path)
    assert cls.verdict == "denied"
    assert cls.reason


def test_classify_unknown(yaml_path: Path) -> None:
    cls = _allowlist.classify("example.com", source_path=yaml_path)
    assert cls.verdict == "unknown"


def test_classify_url_extracts_host(yaml_path: Path) -> None:
    cls = _allowlist.classify_url(
        "https://www.govinfo.gov/app/collection/uscode",
        source_path=yaml_path,
    )
    assert cls.verdict == "primary"


def test_lookup_directory_specific_jurisdiction(yaml_path: Path) -> None:
    entry = _allowlist.lookup_directory("statute", "MD", source_path=yaml_path)
    assert entry is not None
    assert entry["sources"][0]["name"] == "MGA"


def test_lookup_directory_wildcard_fallback(yaml_path: Path) -> None:
    # tos has only "*", lookup with a specific jurisdiction should fall back.
    entry = _allowlist.lookup_directory("tos", "MD", source_path=yaml_path)
    assert entry is not None
    assert entry["label"] == "Terms of Service"


def test_lookup_directory_missing_returns_none(yaml_path: Path) -> None:
    assert _allowlist.lookup_directory("nonexistent", "MD", source_path=yaml_path) is None


def test_real_data_file_loads() -> None:
    """The shipped data/reference_sources.yaml must parse cleanly."""
    cls = _allowlist.classify("www.ecfr.gov")
    assert cls.verdict in {"primary", "unknown"}  # depends on whether *.gov pattern is present
    # Confirm the directory has expected entries.
    directory = _allowlist.load_directory()
    assert ("statute", "MD") in directory
    assert ("regulation", "federal") in directory
