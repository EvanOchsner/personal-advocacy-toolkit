"""Tests for scripts/letters/draft.py.

Each of the 5 letter kinds is rendered against a Mustang-in-Maryland
synthetic fixture. We assert recipient name, sender name, disclaimer,
and the per-kind signature phrase are present in the rendered body.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("jinja2")

import yaml  # noqa: E402

from scripts.letters import draft  # noqa: E402


# Synthetic Mustang-in-Maryland intake (fields the drafter reads).
MUSTANG_INTAKE = {
    "schema_version": "0.1",
    "synthetic": True,
    "case_name": "Mustang in Maryland",
    "case_slug": "mustang-in-maryland",
    "situation_type": "insurance_dispute",
    "claimant": {
        "name": "Delia Vance",
        "address": {
            "street": "414 Aigburth Vale",
            "city": "Towson",
            "state": "MD",
            "zip": "21204",
        },
        "email": "delia.vance@example.com",
        "phone": "+1-410-555-0142",
    },
    "jurisdiction": {"state": "MD"},
    "parties": {
        "insurer": {
            "name": "Chesapeake Indemnity Mutual",
            "address": "PO Box 0000, Baltimore, MD 21201",
        },
        "adjuster": {
            "name": "Harlan Whitlock",
            "email": "harlan.whitlock@chesapeake-indemnity-mutual.example",
        },
    },
    "loss": {
        "date": "2025-03-15",
        "description": "Rear-ended while stopped at a traffic signal.",
    },
    "policy": {
        "policy_number": "CIM-CLS-0000-0000",
        "agreed_value_usd": 58000,
    },
    "disputed_amounts": {
        "insurer_deduction_usd": 5280.50,
    },
    "regulator": {
        "name": "Maryland Insurance Administration",
        "short_name": "MIA",
        "case_number": "MIA-SYN-0000-0000",
    },
}


@pytest.fixture
def intake_path(tmp_path: Path) -> Path:
    p = tmp_path / "case-intake.yaml"
    p.write_text(yaml.safe_dump(MUSTANG_INTAKE, sort_keys=False))
    return p


@pytest.mark.parametrize("kind", list(draft.KINDS))
def test_draft_each_kind_txt(tmp_path: Path, intake_path: Path, kind: str) -> None:
    out = tmp_path / f"{kind}.txt"
    result = draft.draft_letter(
        kind=kind,
        intake_path=intake_path,
        out=out,
        interactive=False,
    )
    body = out.read_text(encoding="utf-8")
    # Sender name present.
    assert "Delia Vance" in body, f"sender name missing in {kind}"
    # Disclaimer present.
    assert draft.LETTER_DISCLAIMER in body, f"disclaimer missing in {kind}"
    assert "not legal advice" in body.lower()
    # Per-kind signature phrase.
    phrase = draft.SIGNATURE_PHRASES[kind]
    assert phrase.lower() in body.lower(), (
        f"signature phrase {phrase!r} missing in {kind} letter"
    )
    # Recipient name: for FOIA the default pulls from authorities.yaml
    # (MD insurance_dispute -> MIA); for counterparty-addressed kinds
    # it pulls from parties.insurer (Chesapeake Indemnity Mutual).
    assert "Maryland Insurance Administration" in body or "Chesapeake Indemnity Mutual" in body


@pytest.mark.parametrize("kind", list(draft.KINDS))
def test_draft_each_kind_docx(tmp_path: Path, intake_path: Path, kind: str) -> None:
    pytest.importorskip("docx")
    out = tmp_path / f"{kind}.docx"
    result = draft.draft_letter(
        kind=kind,
        intake_path=intake_path,
        out=out,
        interactive=False,
    )
    assert out.exists()
    assert out.stat().st_size > 0
    # Rendered text is returned in the result; check signature + disclaimer.
    rendered = result["rendered_text"]
    assert draft.LETTER_DISCLAIMER in rendered
    assert draft.SIGNATURE_PHRASES[kind].lower() in rendered.lower()
    assert "Delia Vance" in rendered


def test_strict_fails_on_missing_required(tmp_path: Path) -> None:
    # Minimal intake missing claimant.name and counterparty.
    bad = {"situation_type": "insurance_dispute", "jurisdiction": {"state": "MD"}}
    p = tmp_path / "case-intake.yaml"
    p.write_text(yaml.safe_dump(bad))
    with pytest.raises(ValueError, match="missing required fields"):
        draft.draft_letter(
            kind="demand",
            intake_path=p,
            out=tmp_path / "out.txt",
            strict=True,
            interactive=False,
        )


def test_recipient_override(tmp_path: Path, intake_path: Path) -> None:
    out = tmp_path / "demand.txt"
    draft.draft_letter(
        kind="demand",
        intake_path=intake_path,
        out=out,
        interactive=False,
        recipient_name="Override Recipient Inc.",
        recipient_address="1 Override Way",
    )
    body = out.read_text(encoding="utf-8")
    assert "Override Recipient Inc." in body
    assert "1 Override Way" in body


def test_unknown_kind_rejected(tmp_path: Path, intake_path: Path) -> None:
    with pytest.raises(ValueError):
        draft.draft_letter(
            kind="bogus",
            intake_path=intake_path,
            out=tmp_path / "x.txt",
            interactive=False,
        )


def test_cli_happy_path(tmp_path: Path, intake_path: Path, capsys) -> None:
    out = tmp_path / "out.txt"
    rc = draft.main(
        [
            "--kind", "foia",
            "--intake", str(intake_path),
            "--out", str(out),
            "--non-interactive",
        ]
    )
    assert rc == 0
    assert out.exists()
    body = out.read_text(encoding="utf-8")
    assert draft.LETTER_DISCLAIMER in body
    assert "public records request" in body.lower()
