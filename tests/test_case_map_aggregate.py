"""Tests for scripts/app/_aggregate.py."""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

yaml = pytest.importorskip("yaml")

from scripts.app._aggregate import build_timeline
from scripts.app._loaders import load_case_map


CASE_FACTS = dedent(
    """\
    claimant:
      name: Sally Ridesdale
      email: sally@example.com
    parties:
      insurer:
        name: Chesapeake Indemnity Mutual
        email: claims@cim.example
    """
)

ENTITIES = dedent(
    """\
    entities:
      - id: self
        role: self
        ref: claimant
        match:
          emails: [sally@example.com]
          names: [Sally Ridesdale]
      - id: cim
        role: adversary
        ref: parties.insurer
        match:
          emails: [claims@cim.example]
          names: [Chesapeake Indemnity Mutual]
    """
)

EVENTS = dedent(
    """\
    events:
      - id: collision
        date: 2025-03-15
        kind: incident
        title: Collision
        entities: [self]
      - id: salvage
        date: 2025-06-24
        kind: incident
        title: Salvage transfer
        entities: [self, cim]
    """
)


def _prepare(tmp_path: Path) -> Path:
    (tmp_path / "case-facts.yaml").write_text(CASE_FACTS, encoding="utf-8")
    (tmp_path / "entities.yaml").write_text(ENTITIES, encoding="utf-8")
    (tmp_path / "events.yaml").write_text(EVENTS, encoding="utf-8")
    return tmp_path


def test_events_only(tmp_path: Path) -> None:
    _prepare(tmp_path)
    loaded = load_case_map(tmp_path)
    markers = build_timeline(loaded)
    assert [m.date for m in markers] == ["2025-03-15", "2025-06-24"]
    assert all(m.source == "events.yaml" for m in markers)
    assert markers[1].entity_ids == ["self", "cim"]


def test_correspondence_matching_by_email(tmp_path: Path) -> None:
    _prepare(tmp_path)
    loaded = load_case_map(tmp_path)
    corresp = {
        "entries": [
            {
                "date": "2025-04-01",
                "subject": "Your claim CIM-2025-03-5517",
                "from": "Harlan Whitlock <claims@cim.example>",
                "to": "Sally Ridesdale <sally@example.com>",
                "message_id": "<a1@cim.example>",
                "source": "corresp/2025-04-01.eml",
            }
        ]
    }
    markers = build_timeline(loaded, correspondence_manifest=corresp)
    corresp_markers = [m for m in markers if m.source == "correspondence"]
    assert len(corresp_markers) == 1
    m = corresp_markers[0]
    assert m.date == "2025-04-01"
    assert set(m.entity_ids) == {"self", "cim"}
    assert m.ref["message_id"] == "<a1@cim.example>"


def test_correspondence_matching_by_name_when_no_email_hit(tmp_path: Path) -> None:
    _prepare(tmp_path)
    loaded = load_case_map(tmp_path)
    corresp = {
        "entries": [
            {
                "date": "2025-04-02",
                "subject": "Re: Chesapeake Indemnity Mutual position",
                "from": "someone@unrelated.example",
                "to": "Sally Ridesdale <sally@example.com>",
                "source": "corresp/2025-04-02.eml",
            }
        ]
    }
    markers = build_timeline(loaded, correspondence_manifest=corresp)
    m = [x for x in markers if x.source == "correspondence"][0]
    # cim matched via name substring in subject; self matched via email.
    assert set(m.entity_ids) == {"self", "cim"}


def test_correspondence_skipped_when_date_missing(tmp_path: Path) -> None:
    _prepare(tmp_path)
    loaded = load_case_map(tmp_path)
    corresp = {
        "entries": [
            {"subject": "undated", "from": "x@y.example", "to": "z@y.example"}
        ]
    }
    markers = build_timeline(loaded, correspondence_manifest=corresp)
    assert not any(m.source == "correspondence" for m in markers)


def test_deadlines_integration(tmp_path: Path) -> None:
    _prepare(tmp_path)
    loaded = load_case_map(tmp_path)
    deadlines = {
        "deadlines": [
            {
                "label": "Statute of limitations (breach of contract)",
                "kind": "statute_of_limitations",
                "deadline_date": "2028-03-15",
                "clock_starts": "loss_date",
                "clock_date": "2025-03-15",
                "status": "populated",
                "verify": "VERIFY WITH COUNSEL",
                "authority_ref": "MD Cts. & Jud. Proc. §5-101",
                "notes": None,
            }
        ]
    }
    markers = build_timeline(loaded, deadlines=deadlines)
    dm = [m for m in markers if m.source == "deadlines"]
    assert len(dm) == 1
    assert dm[0].title.startswith("[DEADLINE]")
    assert dm[0].ref["authority_ref"] == "MD Cts. & Jud. Proc. §5-101"


def test_deadline_stub_status_in_title(tmp_path: Path) -> None:
    _prepare(tmp_path)
    loaded = load_case_map(tmp_path)
    deadlines = {
        "deadlines": [
            {
                "label": "Unknown deadline",
                "kind": "other",
                "deadline_date": "2026-01-01",
                "status": "stub",
                "verify": "VERIFY WITH COUNSEL",
            }
        ]
    }
    markers = build_timeline(loaded, deadlines=deadlines)
    dm = [m for m in markers if m.source == "deadlines"]
    assert len(dm) == 1
    assert "(stub)" in dm[0].title.lower()


def test_chronological_sort(tmp_path: Path) -> None:
    _prepare(tmp_path)
    loaded = load_case_map(tmp_path)
    corresp = {
        "entries": [
            {
                "date": "2025-04-15",
                "subject": "middle",
                "from": "claims@cim.example",
                "to": "sally@example.com",
            }
        ]
    }
    markers = build_timeline(loaded, correspondence_manifest=corresp)
    dates = [m.date for m in markers]
    assert dates == sorted(dates)


def test_mustang_seed_timeline(tmp_path: Path) -> None:
    case_dir = Path(__file__).parent.parent / "examples" / "maryland-mustang"
    loaded = load_case_map(case_dir)
    markers = build_timeline(loaded)
    assert len(markers) == 15  # one per event in events.yaml
    assert all(m.source == "events.yaml" for m in markers)
    # collision is first
    assert markers[0].title.startswith("Collision")
