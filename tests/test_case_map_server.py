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


CASE_DIR = Path(__file__).parent.parent / "examples" / "maryland-mustang"


@pytest.fixture(scope="module", autouse=True)
def _build_case_map_cache():
    """Ensure the case-map cache exists before tests run.

    The viewer is read-only; it refuses to start without a precomputed
    cache under <case>/.case-map/. We build it once per test session
    against the synthetic example case.
    """
    from scripts.case_map_build.__main__ import main as build_main
    rc = build_main(["--case-dir", str(CASE_DIR)])
    assert rc == 0


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
    # Caption comes from case_name (or claimant) in case-facts.yaml.
    assert "Maryland Mustang" in text or "Sally Ridesdale" in text
    # Sector containers should be in the rendered shell.
    assert "sector-allies" in text
    assert "sector-adversaries" in text
    # Plotly is loaded from the vendor path.
    assert "/static/vendor/plotly-basic.min.js" in text


def test_dashboard_api(app) -> None:
    status, headers, body = _call(app, "/api/dashboard")
    assert status.startswith("200")
    assert headers["content-type"].startswith("application/json")
    assert headers["content-security-policy"] == CSP
    payload = json.loads(body)
    # Top-level keys for the four sectors plus the disclaimer.
    for k in ("central_issue", "parties", "references", "adjudicators", "disclaimer"):
        assert k in payload, k
    parties = payload["parties"]
    for bucket in ("allies", "neutrals", "adversaries"):
        assert isinstance(parties[bucket], list)
    # Allies should include the claimant ("self") card.
    ally_ids = {c["id"] for c in parties["allies"]}
    assert "self" in ally_ids
    # Adversaries should include cim.
    adv_ids = {c["id"] for c in parties["adversaries"]}
    assert "cim" in adv_ids
    # Adjudicators carry the regulator card.
    assert any("Maryland Insurance Administration" in c.get("name", "") for c in payload["adjudicators"]["cards"])


def test_entity_api_uses_cache(app) -> None:
    status, headers, body = _call(app, "/api/entity/self")
    assert status.startswith("200")
    payload = json.loads(body)
    assert payload["id"] == "self"
    assert payload["display_name"] == "Sally Ridesdale"
    # resolved should carry through case-facts.yaml claimant fields.
    assert payload["resolved"].get("email") == "sally.ridesdale@example.com"
    # `events` here is the slice of timeline markers tagged with this entity.
    assert any(ev.get("title", "").startswith("Collision") for ev in payload["events"])


def test_entity_api_unknown_returns_404(app) -> None:
    status, _, body = _call(app, "/api/entity/does_not_exist")
    assert status.startswith("404")
    assert b"unknown entity" in body


def test_entity_api_bad_path_shape_returns_404(app) -> None:
    status, _, _ = _call(app, "/api/entity/../secret")
    assert status.startswith("404")


def test_timeline_api(app) -> None:
    status, headers, body = _call(app, "/api/timeline")
    assert status.startswith("200")
    assert headers["content-type"].startswith("application/json")
    payload = json.loads(body)
    # Plotly figure spec.
    assert "figure" in payload
    assert "data" in payload["figure"]
    assert "layout" in payload["figure"]
    assert payload["figure"]["data"]  # at least one trace
    # The mirror list of markers should also be present.
    assert "markers" in payload
    assert len(payload["markers"]) >= 15  # at least the events.yaml set
    for m in payload["markers"]:
        assert m["date"]
        assert m["kind"] in {"event", "correspondence", "deadline"}


def test_timeline_markers_sorted(app) -> None:
    _, _, body = _call(app, "/api/timeline")
    markers = json.loads(body)["markers"]
    dates = [m["date"] for m in markers]
    assert dates == sorted(dates)


def test_case_file_serves_text(app) -> None:
    status, headers, body = _call(app, "/file/case-facts.yaml")
    assert status.startswith("200")
    assert headers["content-type"].startswith("text/") or "yaml" in headers["content-type"]
    assert headers["content-disposition"].startswith("inline")
    assert b"Sally Ridesdale" in body


def test_case_file_path_traversal_blocked(app) -> None:
    status, _, _ = _call(app, "/file/../../../etc/passwd")
    assert status.startswith("404")


def test_case_file_absolute_path_blocked(app) -> None:
    status, _, _ = _call(app, "/file//etc/passwd")
    assert status.startswith("404")


def test_case_file_extension_not_allowlisted(app, tmp_path: Path) -> None:
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


def test_graph_api_is_gone(app) -> None:
    # /api/graph was removed when the case map switched to a sector dashboard.
    # If it ever comes back, that's a regression — the dashboard is the
    # canonical entry point now.
    status, _, _ = _call(app, "/api/graph")
    assert status.startswith("404")


def test_missing_cache_raises_clear_error(tmp_path: Path) -> None:
    # A case directory with no .case-map/ should fail fast with a pointer
    # to the build command; the viewer must not silently regenerate.
    (tmp_path / "case-facts.yaml").write_text(
        "claimant:\n  name: Test\n", encoding="utf-8"
    )
    (tmp_path / "entities.yaml").write_text(
        "entities:\n  - id: self\n    role: self\n    display_name: Test\n",
        encoding="utf-8",
    )
    from scripts.app.server import CacheNotBuiltError
    with pytest.raises(CacheNotBuiltError, match="case_map_build"):
        make_app(tmp_path)


# --------------------------------------------------------------------------- #
# Static serving
# --------------------------------------------------------------------------- #


def test_static_css_served(app) -> None:
    status, headers, body = _call(app, "/static/css/dashboard.css")
    assert status.startswith("200")
    assert headers["content-type"].startswith("text/css")
    assert headers["content-security-policy"] == CSP
    assert b"--ally" in body


def test_static_js_served(app) -> None:
    status, headers, body = _call(app, "/static/js/app.js")
    assert status.startswith("200")
    assert "javascript" in headers["content-type"]
    assert b"selectEntity" in body


def test_static_vendor_plotly_served(app) -> None:
    status, headers, _ = _call(app, "/static/vendor/plotly-basic.min.js")
    assert status.startswith("200")
    assert "javascript" in headers["content-type"]


def test_static_path_traversal_blocked(app) -> None:
    status, _, _ = _call(app, "/static/../server.py")
    assert status.startswith("404")


def test_static_unknown_extension_blocked(app) -> None:
    status, _, _ = _call(app, "/static/js/../../../etc/passwd")
    assert status.startswith("404")


# --------------------------------------------------------------------------- #
# Airgap structural checks
# --------------------------------------------------------------------------- #


def test_bind_host_is_loopback() -> None:
    assert BIND_HOST == "127.0.0.1"


def test_csp_does_not_allow_external_origins() -> None:
    for directive in ("default-src", "script-src", "connect-src", "style-src"):
        segment = next(
            s for s in CSP.split(";") if s.strip().startswith(directive)
        )
        assert "https:" not in segment
        assert "http:" not in segment
        assert "*" not in segment


def test_no_external_urls_in_static_tree() -> None:
    """Mirror of the CI grep step — kept here so local test runs catch it too.

    `static/vendor/` is excluded by policy: minified third-party bundles
    contain URL string literals (doc links, MathJax CDN, XML namespaces)
    that are not network calls. The CSP and 127.0.0.1 bind block any
    actual fetch. See scripts/app/static/vendor/README.md.
    """
    static_root = Path(__file__).parent.parent / "scripts" / "app" / "static"
    tpl_root = Path(__file__).parent.parent / "scripts" / "app" / "templates"
    offenders: list[tuple[Path, str]] = []
    patterns = ("http://", "https://", "//cdn.", "//fonts.")
    for root in (static_root, tpl_root):
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix not in {".html", ".css", ".js"}:
                continue
            # Skip vendored third-party bundles — see docstring.
            if "vendor" in p.relative_to(root).parts:
                continue
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
