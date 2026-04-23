"""WSGI app for the case-map browser UI.

Airgap posture (see scripts/app/__init__.py for full docstring):
    - Bind host is a module-level constant, not a CLI flag.
    - Every response carries a restrictive Content-Security-Policy.
    - Static assets and templates live inside this package; NO CDN
      references are permitted (enforced by a CI grep step).
    - The markdown renderer used for entity notes does NOT emit
      anchor tags for external URL schemes.

Routes (PR 2 scope — timeline + file-serving land in PR 3):
    GET /                    -> rendered index.html
    GET /static/<path>       -> read-only static asset
    GET /api/graph           -> {entities, relationships}
    GET /api/entity/<id>     -> entity drilldown JSON
"""
from __future__ import annotations

import json
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from scripts.intake._common import DISCLAIMER

from scripts.app._loaders import LoadedCaseMap, load_case_map
from scripts.app._markdown import render as render_markdown


BIND_HOST = "127.0.0.1"  # DO NOT parameterize. See airgap notes above.
DEFAULT_PORT = 8765

CSP = (
    "default-src 'self'; "
    "connect-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

_PACKAGE_ROOT = Path(__file__).parent
_TEMPLATES_DIR = _PACKAGE_ROOT / "templates"
_STATIC_DIR = _PACKAGE_ROOT / "static"

_STATIC_EXT_ALLOWLIST = frozenset({".css", ".js", ".svg", ".png", ".ico", ".woff2"})

_ENTITY_API_RE = re.compile(r"^/api/entity/([A-Za-z0-9][A-Za-z0-9_-]*)$")


@dataclass
class Response:
    status: str
    headers: list[tuple[str, str]]
    body: bytes


def make_app(case_dir: Path) -> Callable[[dict, Callable], Iterable[bytes]]:
    """Return a WSGI callable bound to the given case directory.

    The case is loaded once at app-construction time. Users who edit
    entities.yaml / events.yaml must restart the server. This keeps the
    app stateless and avoids partial-reload races.
    """
    loaded = load_case_map(case_dir)

    def app(environ: dict, start_response: Callable) -> Iterable[bytes]:
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/") or "/"
        resp = _route(method, path, loaded)
        start_response(resp.status, _with_defaults(resp.headers))
        return [resp.body]

    return app


def _route(method: str, path: str, loaded: LoadedCaseMap) -> Response:
    if method not in ("GET", "HEAD"):
        return _text_response("405 Method Not Allowed", "method not allowed")

    if path == "/":
        return _render_index(loaded)

    if path.startswith("/static/"):
        return _serve_static(path[len("/static/") :])

    if path == "/api/graph":
        return _json_response(_graph_payload(loaded))

    m = _ENTITY_API_RE.match(path)
    if m:
        return _entity_payload(loaded, m.group(1))

    return _text_response("404 Not Found", "not found")


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #


def _render_index(loaded: LoadedCaseMap) -> Response:
    import jinja2

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=True,
        undefined=jinja2.StrictUndefined,
    )
    template = env.get_template("index.html")
    caption = _case_caption(loaded)
    html = template.render(
        caption=caption,
        disclaimer=DISCLAIMER,
        entity_count=len(loaded.entities),
        relationship_count=len(loaded.relationships),
        event_count=len(loaded.events),
    )
    return Response(
        status="200 OK",
        headers=[("Content-Type", "text/html; charset=utf-8")],
        body=html.encode("utf-8"),
    )


def _serve_static(rel: str) -> Response:
    if ".." in rel.split("/") or rel.startswith("/"):
        return _text_response("404 Not Found", "not found")
    target = (_STATIC_DIR / rel).resolve()
    try:
        target.relative_to(_STATIC_DIR)
    except ValueError:
        return _text_response("404 Not Found", "not found")
    if target.suffix not in _STATIC_EXT_ALLOWLIST or not target.is_file():
        return _text_response("404 Not Found", "not found")
    mime, _ = mimetypes.guess_type(str(target))
    return Response(
        status="200 OK",
        headers=[("Content-Type", mime or "application/octet-stream")],
        body=target.read_bytes(),
    )


def _graph_payload(loaded: LoadedCaseMap) -> dict[str, Any]:
    entities = []
    for ent in loaded.entities:
        res = loaded.resolved[ent.id]
        entities.append(
            {
                "id": ent.id,
                "role": ent.role,
                "display_name": res.display_name,
                "labels": list(ent.labels),
                "icon": ent.icon,
                "color": ent.color or _palette_color(ent.id),
            }
        )
    relationships = [
        {
            "from": r.source,
            "to": r.target,
            "kind": r.kind,
            "summary": r.summary,
        }
        for r in loaded.relationships
    ]
    return {
        "caption": _case_caption(loaded),
        "entities": entities,
        "relationships": relationships,
        "disclaimer": DISCLAIMER,
    }


def _entity_payload(loaded: LoadedCaseMap, entity_id: str) -> Response:
    if entity_id not in loaded.resolved:
        return _text_response("404 Not Found", f"unknown entity {entity_id!r}")
    ent = next(e for e in loaded.entities if e.id == entity_id)
    res = loaded.resolved[entity_id]

    notes_html = ""
    if ent.notes_file:
        note_path = (loaded.case_dir / ent.notes_file).resolve()
        try:
            note_path.relative_to(loaded.case_dir)
            if note_path.is_file():
                notes_html = render_markdown(note_path.read_text(encoding="utf-8"))
        except ValueError:
            pass

    rel_in = [
        {"from": r.source, "kind": r.kind, "summary": r.summary}
        for r in loaded.relationships
        if r.target == entity_id
    ]
    rel_out = [
        {"to": r.target, "kind": r.kind, "summary": r.summary}
        for r in loaded.relationships
        if r.source == entity_id
    ]

    events = [
        {
            "id": ev.id,
            "date": ev.date,
            "kind": ev.kind,
            "title": ev.title,
            "summary": ev.summary,
        }
        for ev in loaded.events
        if entity_id in ev.entities
    ]

    return _json_response(
        {
            "id": ent.id,
            "role": ent.role,
            "display_name": res.display_name,
            "labels": list(ent.labels),
            "icon": ent.icon,
            "color": ent.color or _palette_color(ent.id),
            "resolved": res.resolved,
            "notes_html": notes_html,
            "relationships_in": rel_in,
            "relationships_out": rel_out,
            "events": events,
            "disclaimer": DISCLAIMER,
        }
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _json_response(payload: Any, *, status: str = "200 OK") -> Response:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return Response(
        status=status,
        headers=[("Content-Type", "application/json; charset=utf-8")],
        body=body,
    )


def _text_response(status: str, text: str) -> Response:
    return Response(
        status=status,
        headers=[("Content-Type", "text/plain; charset=utf-8")],
        body=text.encode("utf-8"),
    )


def _with_defaults(headers: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [
        *headers,
        ("Content-Security-Policy", CSP),
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "no-referrer"),
        ("Cache-Control", "no-store"),
    ]


def _case_caption(loaded: LoadedCaseMap) -> str:
    cf = loaded.case_facts or {}
    for key in ("case_name", "case_slug"):
        if cf.get(key):
            return str(cf[key])
    claimant = cf.get("claimant") or {}
    if isinstance(claimant, dict) and claimant.get("name"):
        return f"Case of {claimant['name']}"
    return f"Case at {loaded.case_dir.name}"


_PALETTE = [
    "#2a7",  # green
    "#27a",  # blue
    "#a72",  # brown
    "#a27",  # magenta
    "#72a",  # purple
    "#7a2",  # lime
    "#2aa",  # cyan
    "#a22",  # red
    "#aa2",  # mustard
    "#555",  # neutral grey
]


def _palette_color(ent_id: str) -> str:
    """Deterministic palette pick keyed by entity id."""
    h = 0
    for ch in ent_id:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return _PALETTE[h % len(_PALETTE)]
