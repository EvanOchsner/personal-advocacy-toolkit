"""Build a unified, entity-tagged timeline from multiple sources.

Sources, in this order of priority when the same date/title collides:
    1. events.yaml           (user-authored; highest fidelity)
    2. correspondence manifest entries (date + from/to headers)
    3. deadlines from scripts.intake.deadline_calc.compute_deadlines

Evidence manifest entries are intentionally excluded — they carry
SHAs, not dates, and joining them to a timeline reliably is out of
scope for v1.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from scripts.app._loaders import LoadedCaseMap


EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


@dataclass
class TimelineMarker:
    date: str  # ISO-8601
    kind: str  # event | correspondence | deadline
    source: str  # events.yaml | correspondence | deadlines
    title: str
    summary: str | None = None
    entity_ids: list[str] = field(default_factory=list)
    ref: dict[str, Any] = field(default_factory=dict)  # pointer back to source

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_timeline(
    loaded: LoadedCaseMap,
    *,
    correspondence_manifest: dict[str, Any] | None = None,
    deadlines: dict[str, Any] | None = None,
) -> list[TimelineMarker]:
    markers: list[TimelineMarker] = []

    # 1. events.yaml
    for event in loaded.events:
        markers.append(
            TimelineMarker(
                date=event.date,
                kind="event",
                source="events.yaml",
                title=event.title,
                summary=event.summary,
                entity_ids=list(event.entities),
                ref={
                    "event_id": event.id,
                    "event_kind": event.kind,
                    "refs": {
                        "correspondence": list(event.refs.correspondence),
                        "letters": list(event.refs.letters),
                        "evidence": list(event.refs.evidence),
                    },
                },
            )
        )

    # 2. correspondence manifest
    if correspondence_manifest:
        entries = correspondence_manifest.get("entries") or []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            dt = str(entry.get("date") or "").strip()
            if not dt:
                continue
            dt_iso = _coerce_date(dt)
            if not dt_iso:
                continue
            entity_ids = _match_correspondence(entry, loaded)
            subject = str(entry.get("subject") or "").strip() or "(no subject)"
            from_hdr = str(entry.get("from") or "").strip()
            to_hdr = str(entry.get("to") or "").strip()
            summary_bits = []
            if from_hdr:
                summary_bits.append(f"from: {from_hdr}")
            if to_hdr:
                summary_bits.append(f"to: {to_hdr}")
            markers.append(
                TimelineMarker(
                    date=dt_iso,
                    kind="correspondence",
                    source="correspondence",
                    title=subject,
                    summary=" · ".join(summary_bits) or None,
                    entity_ids=entity_ids,
                    ref={
                        "message_id": entry.get("message_id"),
                        "source_path": entry.get("source"),
                        "from": from_hdr,
                        "to": to_hdr,
                    },
                )
            )

    # 3. deadlines
    if deadlines:
        for d in deadlines.get("deadlines") or []:
            if not isinstance(d, dict):
                continue
            dt = str(d.get("deadline_date") or "").strip()
            dt_iso = _coerce_date(dt)
            if not dt_iso:
                continue
            label = str(d.get("label") or "(unlabeled deadline)").strip()
            verify = str(d.get("verify") or "").strip()
            notes = str(d.get("notes") or "").strip() or None
            status = str(d.get("status") or "").strip()
            title = f"[DEADLINE] {label}"
            if status and status != "populated":
                title += f" ({status})"
            markers.append(
                TimelineMarker(
                    date=dt_iso,
                    kind="deadline",
                    source="deadlines",
                    title=title,
                    summary=notes,
                    entity_ids=[],
                    ref={
                        "deadline_kind": d.get("kind"),
                        "clock_starts": d.get("clock_starts"),
                        "clock_date": d.get("clock_date"),
                        "status": status,
                        "verify": verify,
                        "authority_ref": d.get("authority_ref"),
                    },
                )
            )

    markers.sort(key=lambda m: (m.date, m.kind, m.title))
    return markers


def _match_correspondence(entry: dict[str, Any], loaded: LoadedCaseMap) -> list[str]:
    """Return the entity ids whose `match` rules hit this correspondence entry.

    A hit is: any email address in the `from`/`to` headers matches an
    `entities[*].match.emails` item (case-insensitive), OR any
    `entities[*].match.names` substring appears in from/to (case-insensitive).
    """
    hay = " ".join(
        str(entry.get(k) or "") for k in ("from", "to", "subject")
    )
    hay_lower = hay.lower()
    emails_in_entry = {e.lower() for e in EMAIL_RE.findall(hay)}

    hits: list[str] = []
    for ent in loaded.entities:
        matched = False
        for em in ent.match.emails:
            if em in emails_in_entry:
                matched = True
                break
        if not matched:
            for nm in ent.match.names:
                if nm.lower() in hay_lower:
                    matched = True
                    break
        if matched:
            hits.append(ent.id)
    return hits


def _coerce_date(raw: str) -> str | None:
    """Accept ISO-8601 dates or datetimes; return YYYY-MM-DD or None."""
    raw = raw.strip()
    if not raw:
        return None
    # Fast path: pure date
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        try:
            date.fromisoformat(raw[:10])
            return raw[:10]
        except ValueError:
            return None
    return None
