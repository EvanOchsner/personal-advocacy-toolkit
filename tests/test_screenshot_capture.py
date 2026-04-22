"""Tests for scripts.ingest.screenshot_capture.

The browser is mocked — tests must not require network access or a
Chromium install. We exercise the stub backend (always available) plus
the manifest/clobber contract.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ingest import screenshot_capture


def test_stub_backend_emits_pdf_and_dom(tmp_path: Path) -> None:
    entry = screenshot_capture.capture(
        "https://example.invalid/synthetic",
        tmp_path,
        backend="stub",
    )
    assert entry["backend"] == "stub"
    assert entry["evidence_grade"] is False
    assert Path(entry["pdf_path"]).exists()
    assert Path(entry["dom_path"]).exists()
    assert len(entry["pdf_sha256"]) == 64
    assert len(entry["dom_sha256"]) == 64
    assert entry["url"] == "https://example.invalid/synthetic"
    assert entry["retrieved_at"].endswith("+00:00")


def test_cli_with_manifest(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    out_dir = tmp_path / "caps"
    manifest = tmp_path / "manifest.yaml"
    rc = screenshot_capture.main(
        [
            "https://example.invalid/post/1",
            "--out-dir",
            str(out_dir),
            "--manifest",
            str(manifest),
            "--backend",
            "stub",
        ]
    )
    assert rc == 0
    import yaml

    data = yaml.safe_load(manifest.read_text())
    entries = data["entries"]
    assert len(entries) == 1
    e = entries[0]
    assert e["kind"] == "screenshot_capture"
    assert e["url"] == "https://example.invalid/post/1"
    assert e["backend"] == "stub"
    assert e["evidence_grade"] is False
    assert "pdf_sha256" in e and "dom_sha256" in e


def test_mocked_playwright_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exercise the playwright code path with a fully mocked browser."""
    called: dict[str, object] = {}

    def fake_capture(url: str, pdf_out: Path, dom_out: Path) -> dict[str, object]:
        called["url"] = url
        pdf_out.write_bytes(b"%PDF-1.4\nmock pdf bytes\n")
        dom_out.write_text("<html><body>mock DOM</body></html>", encoding="utf-8")
        return {"backend": "playwright", "http_status": 200}

    monkeypatch.setitem(screenshot_capture.BACKENDS, "playwright", fake_capture)
    entry = screenshot_capture.capture(
        "https://example.invalid/mock", tmp_path, backend="playwright"
    )
    assert called["url"] == "https://example.invalid/mock"
    assert entry["backend"] == "playwright"
    assert entry["http_status"] == 200
    assert entry["evidence_grade"] is True


def test_select_backend_respects_explicit_request() -> None:
    assert screenshot_capture.select_backend("stub") == "stub"
    assert screenshot_capture.select_backend("chrome") == "chrome"


def test_manifest_refuses_clobber(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("yaml")
    # Freeze the timestamp so capture() produces the same source_id twice.
    from datetime import datetime, timezone

    frozen = datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    class _FakeDT:
        @staticmethod
        def now(tz: object = None) -> datetime:
            return frozen

    monkeypatch.setattr(screenshot_capture, "datetime", _FakeDT)

    out_dir = tmp_path / "caps"
    manifest = tmp_path / "manifest.yaml"
    args = [
        "https://example.invalid/freeze",
        "--out-dir",
        str(out_dir),
        "--manifest",
        str(manifest),
        "--backend",
        "stub",
    ]
    assert screenshot_capture.main(args) == 0
    assert screenshot_capture.main(args) == 3  # clobber-refused
    assert screenshot_capture.main(args + ["--force"]) == 0
