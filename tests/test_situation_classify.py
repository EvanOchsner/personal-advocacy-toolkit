"""Tests for scripts/intake/situation_classify.py.

Uses the real data/situation_types.yaml so the rules behave the same
way end users will see. All inputs are synthetic.
"""
from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from scripts.intake import situation_classify as sc
from scripts.intake._common import data_dir, load_yaml


REPO_SITUATIONS = load_yaml(data_dir() / "situation_types.yaml")


def test_md_insurance_happy_path(tmp_path: Path) -> None:
    answers_file = tmp_path / "answers.yaml"
    answers_file.write_text(
        yaml.safe_dump(
            {
                "claimant_name": "Sally Ridesdale",
                "jurisdiction_state": "MD",
                "counterparty_kind": "insurer",
                "situation": "Agreed-value auto claim denied after a total loss; "
                "insurer is an insurance company acting in bad faith.",
                "loss_date": "2025-03-15",
            }
        )
    )
    out = tmp_path / "case-intake.yaml"
    rc = sc.main(["--answers", str(answers_file), "--out", str(out)])
    assert rc == 0
    loaded = yaml.safe_load(out.read_text())
    assert loaded["situation_type"] == "insurance_dispute"
    assert loaded["claimant"]["name"] == "Sally Ridesdale"
    assert loaded["jurisdiction"]["state"] == "MD"
    assert loaded["classifier"]["disclaimer"] == sc.DISCLAIMER
    assert any("counterparty_kind" in m for m in loaded["classifier"]["matched_on"])


def test_unknown_falls_through_to_unknown_slug() -> None:
    answers = sc.Answers.from_dict(
        {
            "situation": "my cat knocked over a vase and I want justice",
            "counterparty_kind": "cat",
        }
    )
    result = sc.classify(answers, REPO_SITUATIONS)
    assert result.situation_slug == "unknown"
    assert result.candidate_scores == {}


def test_keyword_only_match() -> None:
    answers = sc.Answers.from_dict(
        {"situation": "my landlord refuses to return the security deposit"}
    )
    result = sc.classify(answers, REPO_SITUATIONS)
    assert result.situation_slug == "landlord_tenant"
    assert result.candidate_scores["landlord_tenant"] >= 1


def test_non_interactive_without_answers_errors(tmp_path: Path, capsys) -> None:
    out = tmp_path / "case-intake.yaml"
    rc = sc.main(["--out", str(out), "--non-interactive"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "answers" in err.lower()


def test_counterparty_kind_outranks_keyword_ties() -> None:
    # "insurance" keyword and counterparty_kind=insurer both point to the
    # same slug — the result should be deterministic and well-scored.
    answers = sc.Answers.from_dict(
        {
            "counterparty_kind": "insurer",
            "situation": "insurance policy coverage denied",
        }
    )
    result = sc.classify(answers, REPO_SITUATIONS)
    assert result.situation_slug == "insurance_dispute"
    assert result.candidate_scores["insurance_dispute"] >= 3
