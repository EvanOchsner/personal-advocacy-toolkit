"""WSGI app for the case-map browser UI.

Airgap posture (see scripts/app/__init__.py for full docstring):
    - Bind host is a module-level constant, not a CLI flag.
    - Every response carries a restrictive Content-Security-Policy.
    - Static assets and templates live inside this package; NO CDN
      references are permitted (enforced by a CI grep step).
    - The markdown renderer used for entity notes does NOT emit
      anchor tags for external URL schemes.

Routes:
    GET /                    -> rendered index.html
    GET /static/<path>       -> read-only static asset
    GET /api/graph           -> {entities, relationships}
    GET /api/entity/<id>     -> entity drilldown JSON
    GET /api/timeline        -> aggregated timeline markers (events +
                                correspondence + deadlines) as JSON
    GET /file/<rel-path>     -> read-only case file, extension-allowlisted
"""
from __future__ import annotations

import json
import mimetypes
import re
import urllib.parse
from dataclasses import dataclass
from datetime import date as date_cls
from pathlib import Path
from typing import Any, Callable, Iterable

from scripts.intake._common import DISCLAIMER, data_dir, load_yaml

from scripts.app._aggregate import build_timeline
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

# Force sensible text MIME types for extensions Python's mimetypes
# module doesn't know about reliably across platforms, so the browser
# displays them inline instead of offering a download.
_MIME_OVERRIDES = {
    ".yaml": "text/yaml; charset=utf-8",
    ".yml": "text/yaml; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".eml": "message/rfc822",
    ".txt": "text/plain; charset=utf-8",
}

# Case-file serving allowlist. Users should be able to open primary
# source materials; anything outside this set (scripts, binaries,
# dotfiles) is refused.
_FILE_EXT_ALLOWLIST = frozenset(
    {
        ".pdf", ".txt", ".md", ".yaml", ".yml",
        ".eml", ".json", ".html", ".csv",
        ".png", ".jpg", ".jpeg", ".gif", ".svg",
        ".docx",
    }
)

_ENTITY_API_RE = re.compile(r"^/api/entity/([A-Za-z0-9][A-Za-z0-9_-]*)$")


@dataclass
class Response:
    status: str
    headers: list[tuple[str, str]]
    body: bytes


def make_app(
    case_dir: Path,
    *,
    correspondence_manifest: Path | None = None,
) -> Callable[[dict, Callable], Iterable[bytes]]:
    """Return a WSGI callable bound to the given case directory.

    The case is loaded once at app-construction time. Users who edit
    entities.yaml / events.yaml must restart the server. This keeps the
    app stateless and avoids partial-reload races.

    If `correspondence_manifest` is given, its entries contribute to
    the /api/timeline aggregation. Deadlines are auto-computed from
    case-facts.yaml when it carries situation_type + jurisdiction.state
    + loss.date.
    """
    loaded = load_case_map(case_dir)

    corresp: dict[str, Any] | None = None
    if correspondence_manifest is not None:
        corresp_path = Path(correspondence_manifest).resolve()
        if corresp_path.is_file():
            corresp = load_yaml(corresp_path)

    deadlines = _compute_case_deadlines(loaded)

    markers = build_timeline(
        loaded,
        correspondence_manifest=corresp,
        deadlines=deadlines,
    )

    def app(environ: dict, start_response: Callable) -> Iterable[bytes]:
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/") or "/"
        resp = _route(method, path, loaded, markers)
        start_response(resp.status, _with_defaults(resp.headers))
        return [resp.body]

    return app


def _route(method: str, path: str, loaded: LoadedCaseMap, markers) -> Response:
    if method not in ("GET", "HEAD"):
        return _text_response("405 Method Not Allowed", "method not allowed")

    if path == "/":
        return _render_index(loaded)

    if path.startswith("/static/"):
        return _serve_static(path[len("/static/") :])

    if path == "/api/graph":
        return _json_response(_graph_payload(loaded))

    if path == "/api/timeline":
        return _json_response(_timeline_payload(markers))

    if path.startswith("/file/"):
        return _serve_case_file(loaded, path[len("/file/") :])

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


def _timeline_payload(markers) -> dict[str, Any]:
    return {
        "markers": [m.to_dict() for m in markers],
        "disclaimer": DISCLAIMER,
    }


def _serve_case_file(loaded: LoadedCaseMap, rel: str) -> Response:
    # URL-decode (tests exercise both decoded and raw paths).
    rel = urllib.parse.unquote(rel)
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        return _text_response("404 Not Found", "not found")
    target = (loaded.case_dir / rel).resolve()
    try:
        target.relative_to(loaded.case_dir)
    except ValueError:
        return _text_response("404 Not Found", "not found")
    if not target.is_file():
        return _text_response("404 Not Found", "not found")
    ext = target.suffix.lower()
    if ext not in _FILE_EXT_ALLOWLIST:
        return _text_response("403 Forbidden", f"extension not allowed: {ext}")
    mime = _MIME_OVERRIDES.get(ext)
    if mime is None:
        guessed, _ = mimetypes.guess_type(str(target))
        mime = guessed or "application/octet-stream"
    return Response(
        status="200 OK",
        headers=[
            ("Content-Type", mime),
            # `inline` so the browser renders the file in-tab; PDFs,
            # text, images, and HTML all behave sensibly here.
            ("Content-Disposition", f'inline; filename="{target.name}"'),
        ],
        body=target.read_bytes(),
    )


def _compute_case_deadlines(loaded: LoadedCaseMap) -> dict[str, Any] | None:
    cf = loaded.case_facts or {}
    situation = cf.get("situation_type")
    jurisdiction = (cf.get("jurisdiction") or {}).get("state")
    loss_date_str = ((cf.get("loss") or {}).get("date")) or ""
    if not (situation and jurisdiction and loss_date_str):
        return None
    try:
        loss_date = date_cls.fromisoformat(str(loss_date_str))
    except (ValueError, TypeError):
        return None
    # deadline_calc is best-effort: if the deadlines table is missing
    # or the (situation, jurisdiction) pair is unknown, skip without
    # breaking the timeline.
    try:
        from scripts.intake import deadline_calc as dc
        # data_dir() walks up from cwd; anchor explicitly from this file
        # so it also works when the case dir lives outside the repo.
        repo_data_dir = data_dir(Path(__file__).parent)
        data = load_yaml(repo_data_dir / "deadlines.yaml")
        inputs = dc.ClockInputs(loss_date=loss_date)
        return dc.compute_deadlines(data, situation, str(jurisdiction), inputs)
    except Exception:
        return None


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
