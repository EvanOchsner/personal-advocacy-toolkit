"""WSGI app for the case-map dashboard UI.

Airgap posture (see scripts/app/__init__.py for full docstring):
    - Bind host is a module-level constant, not a CLI flag.
    - Every response carries a restrictive Content-Security-Policy.
    - Static assets and templates live inside this package; NO CDN
      references are permitted (enforced by a CI grep step that
      excludes scripts/app/static/vendor/ — see vendor/README.md).
    - The viewer is read-only: it serves a precomputed cache from
      <case>/.case-map/, never writes back, never calls the network.

Routes:
    GET /                    -> rendered index.html (sector dashboard)
    GET /static/<path>       -> read-only static asset
    GET /api/dashboard       -> precomputed dashboard payload (sectors)
    GET /api/timeline        -> Plotly figure spec + markers
    GET /api/entity/<id>     -> entity drilldown JSON
    GET /file/<rel-path>     -> read-only case file, extension-allowlisted
"""
from __future__ import annotations

import json
import mimetypes
import re
import urllib.parse
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

_MIME_OVERRIDES = {
    ".yaml": "text/yaml; charset=utf-8",
    ".yml": "text/yaml; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".eml": "message/rfc822",
    ".txt": "text/plain; charset=utf-8",
}

_FILE_EXT_ALLOWLIST = frozenset(
    {
        ".pdf", ".txt", ".md", ".yaml", ".yml",
        ".eml", ".json", ".html", ".csv",
        ".png", ".jpg", ".jpeg", ".gif", ".svg",
        ".docx",
    }
)

_ENTITY_API_RE = re.compile(r"^/api/entity/([A-Za-z0-9][A-Za-z0-9_-]*)$")


class CacheNotBuiltError(RuntimeError):
    """Raised when the viewer is started against a case with no .case-map/ cache."""


@dataclass
class Response:
    status: str
    headers: list[tuple[str, str]]
    body: bytes


def make_app(
    case_dir: Path,
    *,
    correspondence_manifest: Path | None = None,  # accepted for backwards compat; unused
) -> Callable[[dict, Callable], Iterable[bytes]]:
    """Return a WSGI callable bound to the given case directory.

    Reads <case>/.case-map/dashboard.json and timeline.json at app
    construction time. If the cache is missing, raises CacheNotBuiltError
    with a clear pointer to the build command. The viewer never
    regenerates the cache — that is the job of `scripts.case_map_build`.

    `correspondence_manifest` is accepted but ignored; correspondence is
    folded into the timeline via the build step. The argument exists so
    older invocations from CLAUDE.md / docs continue to parse.
    """
    del correspondence_manifest  # silence unused-warning; kept for API stability
    loaded = load_case_map(case_dir)

    cache_dir = loaded.cache_dir
    dashboard_path = cache_dir / "dashboard.json"
    timeline_path = cache_dir / "timeline.json"
    if not dashboard_path.is_file() or not timeline_path.is_file():
        raise CacheNotBuiltError(
            f"case-map cache not found at {cache_dir}/. "
            f"Run: uv run python -m scripts.case_map_build --case-dir {case_dir}"
        )

    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))

    def app(environ: dict, start_response: Callable) -> Iterable[bytes]:
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/") or "/"
        resp = _route(method, path, loaded, dashboard, timeline)
        start_response(resp.status, _with_defaults(resp.headers))
        return [resp.body]

    return app


def _route(
    method: str,
    path: str,
    loaded: LoadedCaseMap,
    dashboard: dict[str, Any],
    timeline: dict[str, Any],
) -> Response:
    if method not in ("GET", "HEAD"):
        return _text_response("405 Method Not Allowed", "method not allowed")

    if path == "/":
        return _render_index(loaded, dashboard)

    if path.startswith("/static/"):
        return _serve_static(path[len("/static/"):])

    if path == "/api/dashboard":
        return _json_response(dashboard)

    if path == "/api/timeline":
        return _json_response(timeline)

    if path.startswith("/file/"):
        return _serve_case_file(loaded, path[len("/file/"):])

    m = _ENTITY_API_RE.match(path)
    if m:
        return _entity_payload(loaded, dashboard, m.group(1), timeline)

    return _text_response("404 Not Found", "not found")


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #


def _render_index(loaded: LoadedCaseMap, dashboard: dict[str, Any]) -> Response:
    import jinja2

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=True,
        undefined=jinja2.StrictUndefined,
    )
    template = env.get_template("index.html")
    central = dashboard.get("central_issue") or {}
    caption = str(central.get("case_name") or _case_caption(loaded))
    parties = dashboard.get("parties") or {}
    references = dashboard.get("references") or {}
    adjudicators = dashboard.get("adjudicators") or {}
    html = template.render(
        caption=caption,
        disclaimer=DISCLAIMER,
        ally_count=len(parties.get("allies") or []),
        neutral_count=len(parties.get("neutrals") or []),
        adversary_count=len(parties.get("adversaries") or []),
        reference_count=len(references.get("cards") or []),
        adjudicator_count=len(adjudicators.get("cards") or []),
    )
    return Response(
        status="200 OK",
        headers=[("Content-Type", "text/html; charset=utf-8")],
        body=html.encode("utf-8"),
    )


def _serve_case_file(loaded: LoadedCaseMap, rel: str) -> Response:
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
            ("Content-Disposition", f'inline; filename="{target.name}"'),
        ],
        body=target.read_bytes(),
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


def _entity_payload(
    loaded: LoadedCaseMap,
    dashboard: dict[str, Any],
    entity_id: str,
    timeline: dict[str, Any],
) -> Response:
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

    # Timeline events (and correspondence/deadlines) tagged with this entity.
    markers = (timeline or {}).get("markers") or []
    related = [
        {
            "date": m.get("date"),
            "kind": m.get("kind"),
            "title": m.get("title"),
            "summary": m.get("summary"),
            "track": m.get("track"),
        }
        for m in markers
        if entity_id in (m.get("entity_ids") or [])
    ]

    # Find the cached party card if present, so the drilldown gets the
    # same blurb the user clicked.
    parties = dashboard.get("parties") or {}
    blurb = ""
    for bucket in ("allies", "neutrals", "adversaries"):
        for card in parties.get(bucket) or []:
            if card.get("id") == entity_id:
                blurb = card.get("blurb") or ""
                break

    return _json_response(
        {
            "id": ent.id,
            "role": ent.role,
            "display_name": res.display_name,
            "labels": list(ent.labels),
            "icon": ent.icon,
            "blurb": blurb,
            "resolved": res.resolved,
            "notes_html": notes_html,
            "events": related,
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
