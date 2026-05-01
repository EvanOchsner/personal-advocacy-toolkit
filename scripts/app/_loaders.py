"""Load and resolve a CaseMap from a case directory.

A case directory is expected to contain:
    - case-facts.yaml       (existing schema; used for ref: resolution)
    - entities.yaml         (new)
    - events.yaml           (new; optional — missing → empty events list)
    - notes/entities/*.md   (optional; referenced by entities[*].notes_file)

`load_case_map(case_dir)` returns a fully-populated CaseMap with all
`ref:` fields resolved against case-facts.yaml via dotted-path lookup
(e.g. ref: parties.insurer -> case_facts["parties"]["insurer"]).
Resolved facts are attached to each Entity via `resolved` attribute so
the UI can render them without re-walking case-facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.intake._common import load_yaml

from scripts.app._schema import (
    CaseMap,
    CaseMapError,
    Entity,
    parse_entities_file,
    parse_events_file,
)


_CACHE_DIR_NAME = ".case-map"


@dataclass
class ResolvedEntity:
    """Entity plus the fact block resolved from case-facts.yaml."""

    entity: Entity
    resolved: dict[str, Any] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        if self.entity.display_name:
            return self.entity.display_name
        name = self.resolved.get("name") if isinstance(self.resolved, dict) else None
        if name:
            return str(name)
        return self.entity.id


@dataclass
class LoadedCaseMap:
    case_dir: Path
    case_map: CaseMap
    case_facts: dict[str, Any]
    resolved: dict[str, ResolvedEntity]  # keyed by entity id

    @property
    def entities(self) -> list[Entity]:
        return self.case_map.entities

    @property
    def events(self):
        return self.case_map.events

    @property
    def cache_dir(self) -> Path:
        return self.case_dir / _CACHE_DIR_NAME


def load_case_map(case_dir: str | Path) -> LoadedCaseMap:
    case_dir = Path(case_dir).resolve()
    if not case_dir.is_dir():
        raise CaseMapError(f"case directory not found: {case_dir}")

    entities_path = case_dir / "entities.yaml"
    if not entities_path.is_file():
        raise CaseMapError(f"entities.yaml not found in {case_dir}")

    case_facts_path = case_dir / "case-facts.yaml"
    case_facts: dict[str, Any] = {}
    if case_facts_path.is_file():
        case_facts = load_yaml(case_facts_path)

    entities_raw = load_yaml(entities_path)
    entities = parse_entities_file(entities_raw, source=entities_path)

    known_ids = {e.id for e in entities}
    events_path = case_dir / "events.yaml"
    if events_path.is_file():
        events_raw = load_yaml(events_path)
        events = parse_events_file(events_raw, source=events_path, known_ids=known_ids)
    else:
        events = []

    resolved = {e.id: _resolve_entity(e, case_facts, source=entities_path) for e in entities}

    # Notes-file paths, when declared, must exist inside the case dir.
    for ent in entities:
        if ent.notes_file:
            note_path = (case_dir / ent.notes_file).resolve()
            if not _is_within(note_path, case_dir):
                raise CaseMapError(
                    f"entities[{ent.id}].notes_file {ent.notes_file!r} escapes case directory."
                )
            # Missing notes file is tolerated (treated as empty by the UI).
            # Only path escape is a hard error.

    return LoadedCaseMap(
        case_dir=case_dir,
        case_map=CaseMap(entities=entities, events=events),
        case_facts=case_facts,
        resolved=resolved,
    )


def resolve_dotted_path(data: Any, dotted: str) -> Any:
    """Walk `data` by dotted path ('parties.insurer'). Returns None if missing.

    Only mapping traversal is supported — lists are not indexed.
    """
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur


def _resolve_entity(entity: Entity, case_facts: dict[str, Any], *, source: Path) -> ResolvedEntity:
    resolved: dict[str, Any] = {}
    if entity.ref:
        val = resolve_dotted_path(case_facts, entity.ref)
        if val is None:
            raise CaseMapError(
                f"{source}: entities[{entity.id}].ref {entity.ref!r} does not resolve "
                "against case-facts.yaml."
            )
        if not isinstance(val, dict):
            raise CaseMapError(
                f"{source}: entities[{entity.id}].ref {entity.ref!r} must resolve "
                f"to a mapping; got {type(val).__name__}."
            )
        resolved = val
    return ResolvedEntity(entity=entity, resolved=resolved)


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False
