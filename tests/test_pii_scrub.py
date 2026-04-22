"""Tests for scripts.publish.pii_scrub.

The post-check (banned-term survivors) is the primary contract. We construct
inputs that visually look scrubbed but still contain a banned term and
assert the post-check surfaces them.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("yaml")

from scripts.publish import pii_scrub  # noqa: E402
from scripts.publish._substitutions import Substitutions  # noqa: E402


def _write_subs(tmp_path: Path, mapping: dict[str, str] | None = None,
                patterns: list[str] | None = None,
                extra: list[str] | None = None) -> Path:
    import yaml
    p = tmp_path / "substitutions.yaml"
    p.write_text(
        yaml.safe_dump(
            {
                "substitutions": mapping or {},
                "policy_number_patterns": patterns or [],
                "extra_banned": extra or [],
            }
        ),
        encoding="utf-8",
    )
    return p


def test_substitution_replaces_literal(tmp_path: Path) -> None:
    subs = Substitutions(mapping={"John Doe": "John Synthetic"})
    text = "Hello John Doe, please contact John Doe again."
    out, changes = pii_scrub.scrub_text(text, subs, [])
    assert "John Doe" not in out
    assert out.count("John Synthetic") == 2
    assert len(changes) == 2
    assert all(c.detector == "substitution" for c in changes)


def test_longest_key_wins(tmp_path: Path) -> None:
    # If "John" and "John Doe" are both keys, "John Doe" must win.
    subs = Substitutions(mapping={"John": "J.", "John Doe": "John Synthetic"})
    text = "John Doe and John Smith."
    out, _ = pii_scrub.scrub_text(text, subs, [])
    assert "John Synthetic and J. Smith." == out


def test_email_phone_vin_detectors() -> None:
    subs = Substitutions()
    text = (
        "Contact jdoe@example.com or 555-123-4567 today. "
        "VIN: 1HGBH41JXMN109186 on the title."
    )
    out, changes = pii_scrub.scrub_text(text, subs, [])
    assert "jdoe@example.com" not in out
    assert "555-123-4567" not in out
    assert "1HGBH41JXMN109186" not in out
    kinds = {c.detector for c in changes}
    assert {"email", "phone", "vin"} <= kinds


def test_policy_number_pattern() -> None:
    subs = Substitutions(policy_number_patterns=[r"CIM-VEH-\d{4}"])
    import re
    pats = [re.compile(p) for p in subs.policy_number_patterns]
    text = "Policy CIM-VEH-2023 issued to you."
    out, changes = pii_scrub.scrub_text(text, subs, pats)
    assert "CIM-VEH-2023" not in out
    assert any(c.detector == "policy_number" for c in changes)


def test_address_best_effort() -> None:
    subs = Substitutions()
    text = "Mailing: 742 Evergreen Terrace. Other stuff."
    out, changes = pii_scrub.scrub_text(text, subs, [])
    assert "742 Evergreen Terrace" not in out
    assert any(c.detector == "address" for c in changes)


def test_refuses_to_scrub_under_evidence(tmp_path: Path) -> None:
    ev = tmp_path / "evidence" / "drafts"
    ev.mkdir(parents=True)
    (ev / "a.txt").write_text("John Doe")
    subs = Substitutions(mapping={"John Doe": "John Synthetic"})
    with pytest.raises(RuntimeError, match="evidence"):
        pii_scrub.scrub_tree(ev, subs, apply=False)


def test_dry_run_does_not_mutate(tmp_path: Path) -> None:
    root = tmp_path / "drafts"
    root.mkdir()
    f = root / "letter.txt"
    f.write_text("Dear John Doe,")
    subs = Substitutions(mapping={"John Doe": "John Synthetic"})
    changes, survivors = pii_scrub.scrub_tree(root, subs, apply=False)
    assert len(changes) == 1
    assert f.read_text() == "Dear John Doe,"
    assert survivors == []


def test_apply_mutates_and_reports(tmp_path: Path) -> None:
    root = tmp_path / "drafts"
    root.mkdir()
    f = root / "letter.txt"
    f.write_text("Dear John Doe, call 555-123-4567 or jdoe@example.com.\n")
    subs = Substitutions(mapping={"John Doe": "John Synthetic"})
    changes, survivors = pii_scrub.scrub_tree(root, subs, apply=True)
    out = f.read_text()
    assert "John Doe" not in out
    assert "555-123-4567" not in out
    assert "jdoe@example.com" not in out
    assert survivors == []
    # Three distinct detectors fired.
    assert {c.detector for c in changes} >= {"substitution", "phone", "email"}


def test_post_check_catches_survivor(tmp_path: Path) -> None:
    """The critical test: a banned term that our literal scrubber misses
    (because the user spelled it slightly differently in the file) must
    still be caught by the banned-term post-check."""
    root = tmp_path / "drafts"
    root.mkdir()
    f = root / "leak.txt"
    # The user's substitutions list bans "742 Evergreen Terrace" as a home
    # address, but extra_banned catches variants our detectors wouldn't.
    # Here the file contains an exact banned literal that has no substitution
    # entry — only an extra_banned entry. Our category detectors also miss
    # it (no "St/Ave/Rd" suffix → ADDRESS_RE won't fire).
    f.write_text("My secret code phrase: OPERATION NIGHTHAWK.\n")
    subs = Substitutions(extra_banned=["OPERATION NIGHTHAWK"])
    changes, survivors = pii_scrub.scrub_tree(root, subs, apply=True)
    assert len(survivors) == 1
    assert "banned-term-survived" in survivors[0]
    assert str(f) in survivors[0]


def test_cli_main_writes_report(tmp_path: Path) -> None:
    root = tmp_path / "drafts"
    root.mkdir()
    (root / "a.txt").write_text("jdoe@example.com")
    subs_path = _write_subs(tmp_path, mapping={})
    report = tmp_path / "r.json"
    rc = pii_scrub.main([
        "--root", str(root),
        "--substitutions", str(subs_path),
        "--report", str(report),
    ])
    assert rc == 0
    data = json.loads(report.read_text())
    assert any(c["detector"] == "email" for c in data["changes"])
    assert data["survivors"] == []


def test_cli_returns_1_on_survivor(tmp_path: Path) -> None:
    root = tmp_path / "drafts"
    root.mkdir()
    (root / "a.txt").write_text("The code is HOTEL-MIKE.\n")
    subs_path = _write_subs(tmp_path, extra=["HOTEL-MIKE"])
    report = tmp_path / "r.json"
    rc = pii_scrub.main([
        "--root", str(root),
        "--substitutions", str(subs_path),
        "--report", str(report),
        "--apply",
    ])
    assert rc == 1
    data = json.loads(report.read_text())
    assert len(data["survivors"]) == 1
