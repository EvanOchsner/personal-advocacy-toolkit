"""Tests for scripts/intake/authorities_lookup.py."""
from __future__ import annotations

import json

import pytest

yaml = pytest.importorskip("yaml")

from scripts.intake import authorities_lookup as al
from scripts.intake._common import DISCLAIMER, data_dir, load_yaml


DATA = load_yaml(data_dir() / "authorities.yaml")


def test_md_insurance_happy_path() -> None:
    result = al.lookup(DATA, "insurance_dispute", "MD")
    assert result["disclaimer"] == DISCLAIMER
    names = [a["short_name"] for a in result["authorities"]]
    assert "MIA" in names
    assert "MD AG CPD" in names
    # Federal results also surface.
    assert "CFPB" in names
    # MD result is populated (no warnings about missing jurisdiction).
    assert result["warnings"] == []


def test_unknown_situation_raises() -> None:
    with pytest.raises(al.LookupError_) as exc:
        al.lookup(DATA, "not_a_real_situation", "MD")
    assert "unknown situation" in str(exc.value)


def test_missing_jurisdiction_falls_back_to_federal() -> None:
    result = al.lookup(DATA, "insurance_dispute", "ZZ")
    assert any("ZZ" in w for w in result["warnings"])
    # Federal results still present.
    assert any(a["scope"] == "federal" for a in result["authorities"])
    # No state-scoped results.
    assert not any(a["scope"] == "ZZ" for a in result["authorities"])


def test_text_format_includes_disclaimer_banner() -> None:
    result = al.lookup(DATA, "insurance_dispute", "MD")
    text = al.format_text(result)
    assert DISCLAIMER in text
    # Disclaimer appears at top and bottom.
    assert text.count(DISCLAIMER) >= 2


def test_cli_json_output(capsys, tmp_path) -> None:
    rc = al.main(
        [
            "--situation", "insurance_dispute",
            "--jurisdiction", "MD",
            "--format", "json",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["situation"] == "insurance_dispute"
    assert parsed["jurisdiction"] == "MD"
    assert parsed["disclaimer"] == DISCLAIMER


def test_cli_unknown_situation_exits_nonzero(capsys) -> None:
    rc = al.main(
        ["--situation", "bogus", "--jurisdiction", "MD"]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "unknown situation" in err
    assert "known jurisdictions" in err
