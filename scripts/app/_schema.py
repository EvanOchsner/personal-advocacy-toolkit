"""Dataclasses and validators for entities.yaml and events.yaml.

Pattern mirrors scripts/packet/_manifest.py: eager loader, a single
CaseMapError exception, small private parsers per section. Fixed-
vocabulary fields are validated against a set here so the UI never
has to handle unknown roles / icons / kinds at render time.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$")

ROLES = frozenset({"self", "ally", "neutral", "adversary"})
ICONS = frozenset(
    {"person", "org", "court", "regulator", "witness", "counsel", "journalist", "venue"}
)
RELATIONSHIP_KINDS = frozenset(
    {
        "adverse_to",
        "represented_by",
        "retained_by",
        "witness_to",
        "venue_for",
        "regulates",
        "allied_with",
        "other",
    }
)
EVENT_KINDS = frozenset({"incident", "filing", "hearing", "call", "meeting", "other"})

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CaseMapError(ValueError):
    """Raised for any entities.yaml / events.yaml shape problem."""


@dataclass
class EntityMatch:
    emails: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)


@dataclass
class Entity:
    id: str
    role: str
    display_name: str | None = None
    labels: list[str] = field(default_factory=list)
    color: str | None = None
    icon: str | None = None
    ref: str | None = None
    match: EntityMatch = field(default_factory=EntityMatch)
    notes_file: str | None = None


@dataclass
class Relationship:
    source: str  # "from" in YAML; "from" is a Python keyword
    target: str
    kind: str
    summary: str | None = None


@dataclass
class EventRefs:
    correspondence: list[str] = field(default_factory=list)
    letters: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


@dataclass
class Event:
    id: str
    date: str  # ISO-8601 YYYY-MM-DD
    kind: str
    title: str
    entities: list[str] = field(default_factory=list)
    summary: str | None = None
    refs: EventRefs = field(default_factory=EventRefs)


@dataclass
class CaseMap:
    entities: list[Entity]
    relationships: list[Relationship]
    events: list[Event]

    @property
    def entity_ids(self) -> set[str]:
        return {e.id for e in self.entities}


def parse_entities_file(data: Any, *, source: Path) -> tuple[list[Entity], list[Relationship]]:
    if not isinstance(data, dict):
        raise CaseMapError(f"{source}: top-level must be a mapping.")
    entities = _parse_entities(data.get("entities") or [])
    relationships = _parse_relationships(data.get("relationships") or [], entities)
    return entities, relationships


def parse_events_file(data: Any, *, source: Path, known_ids: set[str]) -> list[Event]:
    if not isinstance(data, dict):
        raise CaseMapError(f"{source}: top-level must be a mapping.")
    raw = data.get("events") or []
    if not isinstance(raw, list):
        raise CaseMapError(f"{source}: `events` must be a list.")
    events: list[Event] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        event = _parse_event(item, index=i, known_ids=known_ids)
        if event.id in seen:
            raise CaseMapError(f"{source}: duplicate event id {event.id!r}.")
        seen.add(event.id)
        events.append(event)
    return events


def _parse_entities(raw: Any) -> list[Entity]:
    if not isinstance(raw, list):
        raise CaseMapError("`entities` must be a list.")
    entities: list[Entity] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise CaseMapError(f"entities[{i}] must be a mapping.")
        eid = str(item.get("id") or "").strip()
        if not ID_RE.match(eid):
            raise CaseMapError(
                f"entities[{i}].id {eid!r} must match {ID_RE.pattern!r} "
                "(lowercase letters, digits, hyphens, underscores; leading alnum)."
            )
        if eid in seen:
            raise CaseMapError(f"entities[{i}]: duplicate id {eid!r}.")
        seen.add(eid)

        role = str(item.get("role") or "").strip()
        if role not in ROLES:
            raise CaseMapError(
                f"entities[{eid}].role {role!r} must be one of {sorted(ROLES)}."
            )

        display_name = _opt_str(item.get("display_name"))
        ref = _opt_str(item.get("ref"))
        if display_name is None and ref is None:
            raise CaseMapError(
                f"entities[{eid}]: either `display_name` or `ref` is required."
            )

        icon = _opt_str(item.get("icon"))
        if icon is not None and icon not in ICONS:
            raise CaseMapError(
                f"entities[{eid}].icon {icon!r} must be one of {sorted(ICONS)}."
            )

        color = _opt_str(item.get("color"))
        if color is not None and not HEX_COLOR_RE.match(color):
            raise CaseMapError(
                f"entities[{eid}].color {color!r} must be a CSS hex colour "
                "like #2a7 or #22aa77."
            )

        labels_raw = item.get("labels") or []
        if not isinstance(labels_raw, list) or not all(isinstance(x, str) for x in labels_raw):
            raise CaseMapError(f"entities[{eid}].labels must be a list of strings.")

        match = _parse_match(item.get("match"), eid=eid)
        notes_file = _opt_str(item.get("notes_file"))

        entities.append(
            Entity(
                id=eid,
                role=role,
                display_name=display_name,
                labels=[str(x) for x in labels_raw],
                color=color,
                icon=icon,
                ref=ref,
                match=match,
                notes_file=notes_file,
            )
        )
    return entities


def _parse_match(raw: Any, *, eid: str) -> EntityMatch:
    if raw is None:
        return EntityMatch()
    if not isinstance(raw, dict):
        raise CaseMapError(f"entities[{eid}].match must be a mapping.")
    emails = raw.get("emails") or []
    names = raw.get("names") or []
    if not isinstance(emails, list) or not all(isinstance(x, str) for x in emails):
        raise CaseMapError(f"entities[{eid}].match.emails must be a list of strings.")
    if not isinstance(names, list) or not all(isinstance(x, str) for x in names):
        raise CaseMapError(f"entities[{eid}].match.names must be a list of strings.")
    return EntityMatch(emails=[e.lower() for e in emails], names=list(names))


def _parse_relationships(raw: Any, entities: list[Entity]) -> list[Relationship]:
    if not isinstance(raw, list):
        raise CaseMapError("`relationships` must be a list.")
    valid = {e.id for e in entities}
    out: list[Relationship] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise CaseMapError(f"relationships[{i}] must be a mapping.")
        source = str(item.get("from") or "").strip()
        target = str(item.get("to") or "").strip()
        kind = str(item.get("kind") or "").strip()
        if source not in valid:
            raise CaseMapError(f"relationships[{i}].from {source!r} is not a known entity id.")
        if target not in valid:
            raise CaseMapError(f"relationships[{i}].to {target!r} is not a known entity id.")
        if kind not in RELATIONSHIP_KINDS:
            raise CaseMapError(
                f"relationships[{i}].kind {kind!r} must be one of {sorted(RELATIONSHIP_KINDS)}."
            )
        out.append(
            Relationship(
                source=source,
                target=target,
                kind=kind,
                summary=_opt_str(item.get("summary")),
            )
        )
    return out


def _parse_event(item: Any, *, index: int, known_ids: set[str]) -> Event:
    if not isinstance(item, dict):
        raise CaseMapError(f"events[{index}] must be a mapping.")
    eid = str(item.get("id") or "").strip()
    if not ID_RE.match(eid):
        raise CaseMapError(f"events[{index}].id {eid!r} must match {ID_RE.pattern!r}.")

    date = str(item.get("date") or "").strip()
    if not ISO_DATE_RE.match(date):
        raise CaseMapError(f"events[{eid}].date {date!r} must be ISO-8601 YYYY-MM-DD.")

    kind = str(item.get("kind") or "").strip()
    if kind not in EVENT_KINDS:
        raise CaseMapError(
            f"events[{eid}].kind {kind!r} must be one of {sorted(EVENT_KINDS)}."
        )

    title = str(item.get("title") or "").strip()
    if not title:
        raise CaseMapError(f"events[{eid}].title is required.")

    ents_raw = item.get("entities") or []
    if not isinstance(ents_raw, list) or not all(isinstance(x, str) for x in ents_raw):
        raise CaseMapError(f"events[{eid}].entities must be a list of strings.")
    for eref in ents_raw:
        if eref not in known_ids:
            raise CaseMapError(
                f"events[{eid}].entities references unknown entity id {eref!r}."
            )

    refs = _parse_event_refs(item.get("refs"), eid=eid)
    return Event(
        id=eid,
        date=date,
        kind=kind,
        title=title,
        entities=list(ents_raw),
        summary=_opt_str(item.get("summary")),
        refs=refs,
    )


def _parse_event_refs(raw: Any, *, eid: str) -> EventRefs:
    if raw is None:
        return EventRefs()
    if not isinstance(raw, dict):
        raise CaseMapError(f"events[{eid}].refs must be a mapping.")
    out = EventRefs()
    for key in ("correspondence", "letters", "evidence"):
        vals = raw.get(key) or []
        if not isinstance(vals, list) or not all(isinstance(x, str) for x in vals):
            raise CaseMapError(f"events[{eid}].refs.{key} must be a list of strings.")
        setattr(out, key, list(vals))
    return out


def _opt_str(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s or None
