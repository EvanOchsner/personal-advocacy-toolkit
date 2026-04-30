"""Tests for scripts.references.fetch.

The fetcher is exercised via mocked urlopen — these tests don't make
real network calls.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

yaml = pytest.importorskip("yaml")

from scripts.references import fetch


SAMPLE_YAML = """\
schema_version: "0.1"
allowlist_domains:
  - { domain: "*.gov",          trust: "primary" }
  - { domain: "law.cornell.edu", trust: "secondary-trusted" }
  - { domain: "web.archive.org", trust: "secondary-confirm" }
denylist_domains:
  - { domain: "*.wikipedia.org", reason: "secondary aggregator" }
"""


@pytest.fixture
def yaml_path(tmp_path: Path) -> Path:
    p = tmp_path / "reference_sources.yaml"
    p.write_text(SAMPLE_YAML)
    return p


class _FakeResponse:
    def __init__(self, body: bytes, content_type: str, final_url: str):
        self._body = body
        self._content_type = content_type
        self._final_url = final_url
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def read(self, n: int = -1) -> bytes:
        return self._body

    def geturl(self) -> str:
        return self._final_url


def test_fetch_allowlisted_primary(yaml_path: Path) -> None:
    body = b"<html><body>statute</body></html>"
    with patch("urllib.request.urlopen") as urlopen:
        urlopen.return_value = _FakeResponse(
            body, "text/html; charset=utf-8", "https://www.govinfo.gov/x"
        )
        result = fetch.fetch(
            "https://www.govinfo.gov/x",
            source_path=yaml_path,
        )
    assert result.raw_bytes == body
    assert result.host == "www.govinfo.gov"
    assert result.classification.verdict == "primary"


def test_fetch_denied_host_refuses(yaml_path: Path) -> None:
    with pytest.raises(fetch.FetchRefused) as exc:
        fetch.fetch("https://en.wikipedia.org/wiki/X", source_path=yaml_path)
    assert "denylist" in str(exc.value)


def test_fetch_unknown_host_refuses(yaml_path: Path) -> None:
    with pytest.raises(fetch.FetchRefused) as exc:
        fetch.fetch("https://example.com/x", source_path=yaml_path)
    assert "trusted-source allowlist" in str(exc.value)


def test_fetch_unknown_host_with_allow_unknown(yaml_path: Path) -> None:
    body = b"<p>data</p>"
    with patch("urllib.request.urlopen") as urlopen:
        urlopen.return_value = _FakeResponse(body, "text/html", "https://example.com/x")
        result = fetch.fetch(
            "https://example.com/x",
            source_path=yaml_path,
            allow_unknown=True,
        )
    assert result.raw_bytes == body
    assert result.classification.verdict == "unknown"


def test_fetch_secondary_confirm_requires_allow_unknown(yaml_path: Path) -> None:
    with pytest.raises(fetch.FetchRefused):
        fetch.fetch("https://web.archive.org/web/2020/foo", source_path=yaml_path)


def test_fetch_oversize_response_refused(yaml_path: Path) -> None:
    body = b"a" * 100
    with patch("urllib.request.urlopen") as urlopen:
        urlopen.return_value = _FakeResponse(body, "text/plain", "https://www.govinfo.gov/x")
        with pytest.raises(fetch.FetchError) as exc:
            fetch.fetch(
                "https://www.govinfo.gov/x",
                source_path=yaml_path,
                max_bytes=10,
            )
    assert "exceeds" in str(exc.value)


def test_describe_shape(yaml_path: Path) -> None:
    body = b"x" * 5
    with patch("urllib.request.urlopen") as urlopen:
        urlopen.return_value = _FakeResponse(body, "text/html", "https://www.govinfo.gov/x")
        result = fetch.fetch("https://www.govinfo.gov/x", source_path=yaml_path)
    desc = fetch.describe(result)
    assert desc["host"] == "www.govinfo.gov"
    assert desc["size_bytes"] == 5
    assert desc["trust"] == "primary"
