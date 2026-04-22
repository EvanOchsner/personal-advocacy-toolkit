"""End-to-end regression: California insurance-dispute authorities and deadlines.

Exercises scripts.intake.authorities_lookup and scripts.intake.deadline_calc
against the populated (CA, insurance_dispute) data. Asserts that:

- CDI appears in the authorities list for CA insurance_dispute.
- The 4-year SOL (Cal. Code Civ. Proc. § 337) resolves to a date
  computed correctly from a synthetic loss date.

Reference material, not legal advice — these tests verify the data
lookup plumbing, not the legal accuracy of any specific date.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from scripts.intake._common import load_yaml
from scripts.intake.authorities_lookup import lookup as authorities_lookup
from scripts.intake.deadline_calc import ClockInputs, compute_deadlines


REPO_ROOT = Path(__file__).resolve().parent.parent
AUTHORITIES_YAML = REPO_ROOT / "data" / "authorities.yaml"
DEADLINES_YAML = REPO_ROOT / "data" / "deadlines.yaml"


def test_ca_insurance_authorities_include_cdi():
    data = load_yaml(AUTHORITIES_YAML)
    result = authorities_lookup(data, "insurance_dispute", "CA")
    names = [a["name"] for a in result["authorities"]]
    short_names = [a.get("short_name") for a in result["authorities"]]

    assert "California Department of Insurance" in names
    assert "CDI" in short_names

    # Status should be populated (not a stub).
    ca_entries = [a for a in result["authorities"] if a.get("scope") == "CA"]
    assert ca_entries, "no CA-scoped authorities returned"
    assert all(a.get("status") == "populated" for a in ca_entries), ca_entries

    # Federal fallbacks still come through (CFPB, FTC).
    assert any(a.get("scope") == "federal" for a in result["authorities"])


def test_ca_insurance_sol_four_years_from_loss_date():
    data = load_yaml(DEADLINES_YAML)
    loss = date(2025, 3, 15)
    inputs = ClockInputs(loss_date=loss)
    result = compute_deadlines(data, "insurance_dispute", "CA", inputs)

    assert result["jurisdiction"] == "CA"
    deadlines = result["deadlines"]
    assert deadlines, "expected populated CA insurance_dispute deadlines"

    sol_entries = [d for d in deadlines if d["kind"] == "sol"]
    assert sol_entries, "expected a SOL entry"
    sol = sol_entries[0]
    assert sol["status"] == "populated"
    assert sol["duration"] == {"years": 4}
    assert sol["deadline_date"] == "2029-03-15"
    assert "337" in (sol.get("authority_ref") or "")


def test_ca_insurance_acknowledgment_window_15_days():
    data = load_yaml(DEADLINES_YAML)
    loss = date(2025, 3, 15)
    notice = date(2025, 3, 16)
    inputs = ClockInputs(loss_date=loss, notice_of_loss=notice)
    result = compute_deadlines(data, "insurance_dispute", "CA", inputs)

    ack = [
        d for d in result["deadlines"]
        if d["kind"] == "notice" and d["duration"] == {"days": 15}
    ]
    assert ack, "expected the 15-day acknowledgment window entry"
    # 2025-03-16 + 15 days = 2025-03-31
    assert ack[0]["deadline_date"] == "2025-03-31"
    assert ack[0]["clock_starts"] == "notice_of_loss"
    assert ack[0]["used_fallback_loss_date"] is False
