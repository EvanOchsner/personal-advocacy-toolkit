"""Tests for scripts/app/server.py and _markdown.py.

Uses wsgiref's own call pattern (no requests lib); each test invokes
the WSGI callable directly and asserts on the captured status +
headers + body.
"""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from scripts.app._markdown import render as render_markdown
from scripts.app.server import BIND_HOST, CSP, make_app


CASE_DIR = Path(__file__).parent.parent / "examples" / "mustang-in-maryland"


@pytest.fixture(scope="module")
def app():
    return make_app(CASE_DIR)


def _call(app, path: str, method: str = "GET") -> tuple[str, dict[str, str], bytes]:
    env = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "8765",
        "wsgi.input": BytesIO(b""),
        "wsgi.errors": BytesIO(),
        "wsgi.url_scheme": "http",
    }
    captured: dict = {}

    def start_response(status, headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = {k.lower(): v for (k, v) in headers}

    chunks = app(env, start_response)
    body = b"".join(chunks)
    return captured["status"], captured["headers"], body


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #


def test_index_returns_html_with_csp(app) -> None:
    status, headers, body = _call(app, "/")
    assert status.startswith("200")
    assert headers["content-type"].startswith("text/html")
    assert headers["content-security-policy"] == CSP
    assert headers["x-frame-options"] == "DENY"
    text = body.decode("utf-8")
    assert "case map" in text.lower()
    assert "Delia Vance" in text or "Mustang in Maryland" in text


def test_graph_api(app) -> None:
    status, headers, body = _call(app, "/api/graph")
    assert status.startswith("200")
    assert headers["content-type"].startswith("application/json")
    assert headers["content-security-policy"] == CSP
    payload = json.loads(body)
    ids = {e["id"] for e in payload["entities"]}
    assert {"self", "cim", "mia"}.issubset(ids)
    for rel in payload["relationships"]:
        assert {"from", "to", "kind"}.issubset(rel.keys())
    for e in payload["entities"]:
        assert e["color"].startswith("#")
        assert e["role"] in {"self", "ally", "neutral", "adversary"}


def test_entity_api_resolves_case_facts(app) -> None:
    status, headers, body = _call(app, "/api/entity/self")
    assert status.startswith("200")
    payload = json.loads(body)
    assert payload["id"] == "self"
    assert payload["display_name"] == "Delia Vance"
    # resolved should carry through case-facts.yaml claimant fields.
    assert payload["resolved"].get("email") == "delia.vance@example.com"
    # self is the `from` of the adverse_to cim relationship.
    kinds = {(r["to"], r["kind"]) for r in payload["relationships_out"]}
    assert ("cim", "adverse_to") in kinds
    # And self appears on many events.
    assert len(payload["events"]) >= 1


def test_entity_api_unknown_returns_404(app) -> None:
    status, _, body = _call(app, "/api/entity/does_not_exist")
    assert status.startswith("404")
    assert b"unknown entity" in body


def test_entity_api_bad_path_shape_returns_404(app) -> None:
    # Path must match the ID regex via the route; slashes mean 404.
    status, _, _ = _call(app, "/api/entity/../secret")
    assert status.startswith("404")


def test_timeline_api(app) -> None:
    status, headers, body = _call(app, "/api/timeline")
    assert status.startswith("200")
    assert headers["content-type"].startswith("application/json")
    payload = json.loads(body)
    assert "markers" in payload
    assert len(payload["markers"]) >= 15  # at least the events.yaml set
    for m in payload["markers"]:
        assert m["date"]
        assert m["kind"] in {"event", "correspondence", "deadline"}


def test_timeline_is_sorted(app) -> None:
    _, _, body = _call(app, "/api/timeline")
    markers = json.loads(body)["markers"]
    dates = [m["date"] for m in markers]
    assert dates == sorted(dates)


def test_case_file_serves_text(app) -> None:
    status, headers, body = _call(app, "/file/case-facts.yaml")
    assert status.startswith("200")
    assert headers["content-type"].startswith("text/") or "yaml" in headers["content-type"]
    assert headers["content-disposition"].startswith("inline")
    assert b"Delia Vance" in body


def test_case_file_path_traversal_blocked(app) -> None:
    status, _, _ = _call(app, "/file/../../../etc/passwd")
    assert status.startswith("404")


def test_case_file_absolute_path_blocked(app) -> None:
    status, _, _ = _call(app, "/file//etc/passwd")
    assert status.startswith("404")


def test_case_file_extension_not_allowlisted(app, tmp_path: Path) -> None:
    # Drop a .sh file into the case dir and confirm the server refuses.
    case_dir = CASE_DIR
    sentinel = case_dir / "_serve_test.sh"
    sentinel.write_text("echo hi\n", encoding="utf-8")
    try:
        status, _, body = _call(app, "/file/_serve_test.sh")
        assert status.startswith("403")
        assert b"extension not allowed" in body
    finally:
        sentinel.unlink()


def test_case_file_missing_is_404(app) -> None:
    status, _, _ = _call(app, "/file/does/not/exist.pdf")
    assert status.startswith("404")


def test_unknown_route_is_404(app) -> None:
    status, _, _ = _call(app, "/nope")
    assert status.startswith("404")


def test_non_get_is_405(app) -> None:
    status, _, _ = _call(app, "/", method="POST")
    assert status.startswith("405")


# --------------------------------------------------------------------------- #
# Static serving
# --------------------------------------------------------------------------- #


def test_static_css_served(app) -> None:
    status, headers, body = _call(app, "/static/css/app.css")
    assert status.startswith("200")
    assert headers["content-type"].startswith("text/css")
    assert headers["content-security-policy"] == CSP
    assert b"--ally" in body


def test_static_js_served(app) -> None:
    status, headers, body = _call(app, "/static/js/app.js")
    assert status.startswith("200")
    assert "javascript" in headers["content-type"]
    assert b"selectEntity" in body


def test_static_path_traversal_blocked(app) -> None:
    status, _, _ = _call(app, "/static/../server.py")
    assert status.startswith("404")


def test_static_unknown_extension_blocked(app) -> None:
    # The server only allows a fixed extension set.
    status, _, _ = _call(app, "/static/js/../../../etc/passwd")
    assert status.startswith("404")


# --------------------------------------------------------------------------- #
# Airgap structural checks
# --------------------------------------------------------------------------- #


def test_bind_host_is_loopback() -> None:
    # Guards against a future change silently widening the bind.
    assert BIND_HOST == "127.0.0.1"


def test_csp_does_not_allow_external_origins() -> None:
    for directive in ("default-src", "script-src", "connect-src", "style-src"):
        # Each directive should be 'self'-only or 'self' + 'unsafe-inline'.
        segment = next(
            s for s in CSP.split(";") if s.strip().startswith(directive)
        )
        assert "https:" not in segment
        assert "http:" not in segment
        assert "*" not in segment


def test_no_external_urls_in_static_tree() -> None:
    """Mirror of the CI grep step — kept here so local test runs catch it too."""
    static_root = Path(__file__).parent.parent / "scripts" / "app" / "static"
    tpl_root = Path(__file__).parent.parent / "scripts" / "app" / "templates"
    offenders: list[tuple[Path, str]] = []
    # Any URL with a scheme that would cross the airgap. We require
    # `://` after http/https so illustrative mentions in comments
    # (e.g. 'fetch("http' describing the grep rule itself) don't flag.
    patterns = ("http://", "https://", "//cdn.", "//fonts.")
    for root in (static_root, tpl_root):
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix not in {".html", ".css", ".js"}:
                continue
            # W3C XML namespace URIs (e.g. the SVG namespace) are identifiers,
            # not fetch targets — browsers do not resolve them. Strip them
            # before the URL scan.
            text = p.read_text(encoding="utf-8").replace(
                "http://www.w3.org/", ""
            )
            for pat in patterns:
                if pat in text:
                    offenders.append((p, pat))
    assert not offenders, f"external URLs found: {offenders}"


# --------------------------------------------------------------------------- #
# Markdown renderer
# --------------------------------------------------------------------------- #


def test_markdown_heading_and_bold() -> None:
    out = render_markdown("# Title\n\nSome **bold** text.")
    assert "<h1>Title</h1>" in out
    assert "<strong>bold</strong>" in out


def test_markdown_escapes_raw_html() -> None:
    out = render_markdown("<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_markdown_internal_link_only() -> None:
    out = render_markdown("[link](relative/path.md)")
    assert '<a href="relative/path.md">link</a>' in out


def test_markdown_external_link_rendered_as_text() -> None:
    out = render_markdown("[bad](https://evil.example/)")
    # No anchor tag; scheme-bearing URL passes through as escaped source text.
    assert "<a " not in out
    assert "https://evil.example" in out


def test_markdown_list_items() -> None:
    out = render_markdown("- one\n- two\n- three")
    assert out.startswith("<ul>")
    assert "<li>one</li>" in out
    assert "<li>three</li>" in out


def test_markdown_inline_code() -> None:
    out = render_markdown("use `foo()` to call")
    assert "<code>foo()</code>" in out


def test_markdown_empty_string() -> None:
    assert render_markdown("") == ""
