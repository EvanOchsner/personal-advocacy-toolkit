"""Tests for scripts/intake/deadline_calc.py.

Covers:
  - MD + insurance_dispute happy path using the Mustang-in-Maryland
    synthetic loss date 2025-03-15.
  - Calendar arithmetic at month/year boundaries (leap years, Jan 31).
  - Missing jurisdiction falls back gracefully.
  - Unknown situation raises DeadlineError.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

yaml = pytest.importorskip("yaml")

from scripts.intake import deadline_calc as dc
from scripts.intake._common import data_dir, load_yaml


DATA = load_yaml(data_dir() / "deadlines.yaml")


# --------------------------------------------------------------------------- #
# add_duration / SOL edges
# --------------------------------------------------------------------------- #


def test_add_duration_years_simple() -> None:
    # 2025-03-15 + 3 years = 2028-03-15
    assert dc.add_duration(date(2025, 3, 15), {"years": 3}) == date(2028, 3, 15)


def test_add_duration_leap_day_fallback() -> None:
    # 2024-02-29 + 1 year clamps to 2025-02-28
    assert dc.add_duration(date(2024, 2, 29), {"years": 1}) == date(2025, 2, 28)


def test_add_duration_months_clamps_to_last_day() -> None:
    # 2025-01-31 + 1 month -> 2025-02-28 (non-leap)
    assert dc.add_duration(date(2025, 1, 31), {"months": 1}) == date(2025, 2, 28)
    # 2024-01-31 + 1 month -> 2024-02-29 (leap)
    assert dc.add_duration(date(2024, 1, 31), {"months": 1}) == date(2024, 2, 29)


def test_add_duration_days() -> None:
    assert dc.add_duration(date(2025, 3, 15), {"days": 60}) == date(2025, 5, 14)


def test_add_duration_rejects_empty_or_multi() -> None:
    with pytest.raises(dc.DeadlineError):
        dc.add_duration(date(2025, 1, 1), {})
    with pytest.raises(dc.DeadlineError):
        dc.add_duration(date(2025, 1, 1), {"days": 1, "months": 1})


# --------------------------------------------------------------------------- #
# compute_deadlines
# --------------------------------------------------------------------------- #


def _mustang_inputs() -> dc.ClockInputs:
    return dc.ClockInputs(
        loss_date=date(2025, 3, 15),
        notice_of_loss=date(2025, 3, 16),
        denial_date=date(2025, 5, 9),
        last_act=date(2025, 6, 24),
    )


def test_md_insurance_happy_path() -> None:
    result = dc.compute_deadlines(DATA, "insurance_dispute", "MD", _mustang_inputs())
    assert result["situation"] == "insurance_dispute"
    assert result["jurisdiction"] == "MD"
    assert result["warnings"] == []
    labels = [d["label"] for d in result["deadlines"]]
    # All four MD populated deadlines should be present.
    assert any("statute of limitations" in l.lower() for l in labels)
    assert any("administrative complaint" in l.lower() for l in labels)
    assert any("prompt-payment" in l.lower() or "claim acknowledgment" in l.lower() for l in labels)
    assert any("proof-of-loss" in l.lower() for l in labels)

    by_label = {d["label"]: d for d in result["deadlines"]}
    # 3-year SOL from 2025-03-15 -> 2028-03-15
    sol = next(d for d in result["deadlines"] if d["kind"] == "sol")
    assert sol["deadline_date"] == "2028-03-15"
    assert sol["verify"] == dc.VERIFY_TAG

    # 15-day insurer-side response from notice_of_loss 2025-03-16 -> 2025-03-31
    pn = next(d for d in result["deadlines"] if d["kind"] == "notice" and d["clock_starts"] == "notice_of_loss")
    assert pn["deadline_date"] == "2025-03-31"
    assert pn["used_fallback_loss_date"] is False


def test_fallback_to_loss_date_when_clock_input_missing() -> None:
    # No denial_date / notice_of_loss provided — notice-of-loss-based deadlines
    # must fall back to loss_date and flag it.
    inputs = dc.ClockInputs(loss_date=date(2025, 3, 15))
    result = dc.compute_deadlines(DATA, "insurance_dispute", "MD", inputs)
    pn = next(d for d in result["deadlines"] if d["clock_starts"] == "notice_of_loss")
    assert pn["used_fallback_loss_date"] is True
    # 2025-03-15 + 15 days -> 2025-03-30
    assert pn["deadline_date"] == "2025-03-30"


def test_missing_jurisdiction_graceful() -> None:
    inputs = dc.ClockInputs(loss_date=date(2025, 3, 15))
    result = dc.compute_deadlines(DATA, "insurance_dispute", "ZZ", inputs)
    assert result["deadlines"] == []
    assert any("ZZ" in w for w in result["warnings"])


def test_unknown_situation_raises() -> None:
    inputs = dc.ClockInputs(loss_date=date(2025, 3, 15))
    with pytest.raises(dc.DeadlineError):
        dc.compute_deadlines(DATA, "bogus_situation", "MD", inputs)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def test_cli_text_includes_verify_tag(capsys) -> None:
    rc = dc.main(
        [
            "--situation", "insurance_dispute",
            "--jurisdiction", "MD",
            "--loss-date", "2025-03-15",
            "--notice-of-loss", "2025-03-16",
            "--denial-date", "2025-05-09",
            "--last-act", "2025-06-24",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert dc.VERIFY_TAG in out
    assert "not legal advice" in out
    # Every DEADLINE line should carry the verify tag.
    for line in out.splitlines():
        if "DEADLINE:" in line:
            assert dc.VERIFY_TAG in line


def test_cli_json_output(capsys) -> None:
    rc = dc.main(
        [
            "--situation", "insurance_dispute",
            "--jurisdiction", "MD",
            "--loss-date", "2025-03-15",
            "--format", "json",
        ]
    )
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["jurisdiction"] == "MD"
    assert parsed["loss_date"] == "2025-03-15"
    assert all(d["verify"] == dc.VERIFY_TAG for d in parsed["deadlines"])


def test_cli_bad_date_errors(capsys) -> None:
    rc = dc.main(
        [
            "--situation", "insurance_dispute",
            "--jurisdiction", "MD",
            "--loss-date", "not-a-date",
        ]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "bad date" in err
