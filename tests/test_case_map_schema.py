"""Tests for scripts/app/_schema.py and scripts/app/_loaders.py."""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

yaml = pytest.importorskip("yaml")

from scripts.app._loaders import load_case_map, resolve_dotted_path
from scripts.app._schema import CaseMapError


MIN_CASE_FACTS = dedent(
    """\
    claimant:
      name: Sally Ridesdale
      email: sally@example.com
    parties:
      insurer:
        name: Chesapeake Indemnity Mutual
        email: claims@cim.example
    regulator:
      name: Maryland Insurance Administration
      short_name: MIA
    """
)

MIN_ENTITIES = dedent(
    """\
    entities:
      - id: self
        role: self
        ref: claimant
      - id: cim
        role: adversary
        ref: parties.insurer
      - id: mia
        role: neutral
        ref: regulator
    """
)


def _write_case(tmp_path: Path, entities: str, events: str | None = None) -> Path:
    (tmp_path / "case-facts.yaml").write_text(MIN_CASE_FACTS, encoding="utf-8")
    (tmp_path / "entities.yaml").write_text(entities, encoding="utf-8")
    if events is not None:
        (tmp_path / "events.yaml").write_text(events, encoding="utf-8")
    return tmp_path


def test_load_minimal_case(tmp_path: Path) -> None:
    _write_case(tmp_path, MIN_ENTITIES)
    loaded = load_case_map(tmp_path)
    assert loaded.case_map.entity_ids == {"self", "cim", "mia"}
    assert loaded.events == []
    assert loaded.resolved["self"].display_name == "Sally Ridesdale"
    assert loaded.resolved["cim"].display_name == "Chesapeake Indemnity Mutual"


def test_missing_entities_file(tmp_path: Path) -> None:
    (tmp_path / "case-facts.yaml").write_text(MIN_CASE_FACTS, encoding="utf-8")
    with pytest.raises(CaseMapError, match="entities.yaml not found"):
        load_case_map(tmp_path)


def test_invalid_role(tmp_path: Path) -> None:
    bad = dedent(
        """\
        entities:
          - id: foo
            role: enemy
            ref: claimant
        """
    )
    _write_case(tmp_path, bad)
    with pytest.raises(CaseMapError, match="role 'enemy' must be one of"):
        load_case_map(tmp_path)


def test_invalid_icon(tmp_path: Path) -> None:
    bad = dedent(
        """\
        entities:
          - id: foo
            role: ally
            ref: claimant
            icon: wombat
        """
    )
    _write_case(tmp_path, bad)
    with pytest.raises(CaseMapError, match="icon 'wombat' must be one of"):
        load_case_map(tmp_path)


def test_invalid_color(tmp_path: Path) -> None:
    bad = dedent(
        """\
        entities:
          - id: foo
            role: ally
            ref: claimant
            color: "not-a-colour"
        """
    )
    _write_case(tmp_path, bad)
    with pytest.raises(CaseMapError, match="must be a CSS hex colour"):
        load_case_map(tmp_path)


def test_duplicate_id(tmp_path: Path) -> None:
    bad = dedent(
        """\
        entities:
          - id: x
            role: self
            display_name: A
          - id: x
            role: ally
            display_name: B
        """
    )
    _write_case(tmp_path, bad)
    with pytest.raises(CaseMapError, match="duplicate id 'x'"):
        load_case_map(tmp_path)


def test_bad_id_pattern(tmp_path: Path) -> None:
    bad = dedent(
        """\
        entities:
          - id: "BadID!"
            role: self
            display_name: A
        """
    )
    _write_case(tmp_path, bad)
    with pytest.raises(CaseMapError, match="must match"):
        load_case_map(tmp_path)


def test_ref_not_in_case_facts(tmp_path: Path) -> None:
    bad = dedent(
        """\
        entities:
          - id: foo
            role: ally
            ref: parties.does_not_exist
        """
    )
    _write_case(tmp_path, bad)
    with pytest.raises(CaseMapError, match="does not resolve"):
        load_case_map(tmp_path)


def test_entity_without_ref_needs_display_name(tmp_path: Path) -> None:
    bad = dedent(
        """\
        entities:
          - id: foo
            role: ally
        """
    )
    _write_case(tmp_path, bad)
    with pytest.raises(CaseMapError, match="display_name` or `ref` is required"):
        load_case_map(tmp_path)


def test_entity_with_display_name_no_ref(tmp_path: Path) -> None:
    ok = dedent(
        """\
        entities:
          - id: journalist_smith
            role: ally
            display_name: Alex Smith (journalist)
            icon: journalist
        """
    )
    _write_case(tmp_path, ok)
    loaded = load_case_map(tmp_path)
    assert loaded.resolved["journalist_smith"].display_name == "Alex Smith (journalist)"
    assert loaded.resolved["journalist_smith"].resolved == {}


def test_relationships_block_rejected_with_migration_message(tmp_path: Path) -> None:
    # The dashboard rewrite removed the graph view; any case file still
    # carrying a `relationships:` block must surface a clear error.
    bad = dedent(
        """\
        entities:
          - id: self
            role: self
            ref: claimant
        relationships:
          - from: self
            to: self
            kind: adverse_to
        """
    )
    _write_case(tmp_path, bad)
    with pytest.raises(CaseMapError, match="relationships.*no longer supported"):
        load_case_map(tmp_path)


def test_events_require_known_entity_ids(tmp_path: Path) -> None:
    events = dedent(
        """\
        events:
          - id: e1
            date: 2025-03-15
            kind: incident
            title: Collision
            entities: [ghost]
        """
    )
    _write_case(tmp_path, MIN_ENTITIES, events=events)
    with pytest.raises(CaseMapError, match="unknown entity id 'ghost'"):
        load_case_map(tmp_path)


def test_events_bad_date(tmp_path: Path) -> None:
    events = dedent(
        """\
        events:
          - id: e1
            date: "15/03/2025"
            kind: incident
            title: Collision
            entities: [self]
        """
    )
    _write_case(tmp_path, MIN_ENTITIES, events=events)
    with pytest.raises(CaseMapError, match="must be ISO-8601"):
        load_case_map(tmp_path)


def test_events_bad_kind(tmp_path: Path) -> None:
    events = dedent(
        """\
        events:
          - id: e1
            date: 2025-03-15
            kind: party
            title: Collision
            entities: [self]
        """
    )
    _write_case(tmp_path, MIN_ENTITIES, events=events)
    with pytest.raises(CaseMapError, match="kind 'party' must be one of"):
        load_case_map(tmp_path)


def test_events_duplicate_id(tmp_path: Path) -> None:
    events = dedent(
        """\
        events:
          - id: e1
            date: 2025-03-15
            kind: incident
            title: A
            entities: [self]
          - id: e1
            date: 2025-03-16
            kind: filing
            title: B
            entities: [self]
        """
    )
    _write_case(tmp_path, MIN_ENTITIES, events=events)
    with pytest.raises(CaseMapError, match="duplicate event id 'e1'"):
        load_case_map(tmp_path)


def test_notes_file_path_escape_rejected(tmp_path: Path) -> None:
    bad = dedent(
        """\
        entities:
          - id: self
            role: self
            ref: claimant
            notes_file: "../escape.md"
        """
    )
    _write_case(tmp_path, bad)
    with pytest.raises(CaseMapError, match="escapes case directory"):
        load_case_map(tmp_path)


def test_resolve_dotted_path() -> None:
    data = {"a": {"b": {"c": 42}}, "x": 1}
    assert resolve_dotted_path(data, "a.b.c") == 42
    assert resolve_dotted_path(data, "x") == 1
    assert resolve_dotted_path(data, "a.missing") is None
    assert resolve_dotted_path(data, "x.y") is None  # walking into non-dict


def test_mustang_seed_loads(tmp_path: Path) -> None:
    # The real Mustang example must load cleanly — it is the CI fixture.
    case_dir = Path(__file__).parent.parent / "examples" / "maryland-mustang"
    loaded = load_case_map(case_dir)
    assert "self" in loaded.resolved
    assert loaded.resolved["self"].display_name == "Sally Ridesdale"
    assert "cim" in loaded.resolved
    assert len(loaded.events) == 15
