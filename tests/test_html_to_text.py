"""Tests for scripts.ingest.html_to_text."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.ingest import html_to_text


FIXTURE = Path(__file__).parent / "fixtures" / "sample_email.html"


def test_render_strips_script_and_style() -> None:
    raw = FIXTURE.read_bytes()
    text, _title, _charset = html_to_text.render_html(raw)
    assert "tracker(" not in text
    assert "color: #333" not in text


def test_render_captures_title() -> None:
    raw = FIXTURE.read_bytes()
    _text, title, _charset = html_to_text.render_html(raw)
    # mdash entity decodes to a real em-dash.
    assert title is not None
    assert title.startswith("Claim Update")
    assert "—" in title


def test_render_decodes_entities() -> None:
    raw = FIXTURE.read_bytes()
    text, _title, _charset = html_to_text.render_html(raw)
    assert "police report & repair estimate" in text
    assert "&amp;" not in text
    assert "&copy;" not in text


def test_render_preserves_link_urls() -> None:
    raw = FIXTURE.read_bytes()
    text, _title, _charset = html_to_text.render_html(raw)
    assert "(https://example.com/claims/SYN-12345)" in text
    assert "(mailto:adjuster@example.com)" in text


def test_render_renders_image_alt() -> None:
    raw = FIXTURE.read_bytes()
    text, _title, _charset = html_to_text.render_html(raw)
    assert "[image: Synthetic Insurance Co. logo]" in text


def test_render_handles_list_items() -> None:
    raw = FIXTURE.read_bytes()
    text, _title, _charset = html_to_text.render_html(raw)
    assert "- Submit the attached form" in text
    assert "- Provide a copy" in text
    assert "- Visit our portal" in text


def test_render_detects_charset() -> None:
    raw = FIXTURE.read_bytes()
    _text, _title, charset = html_to_text.render_html(raw)
    assert charset == "utf-8"


def test_render_falls_back_to_utf8_for_unknown_charset() -> None:
    # Declared charset doesn't exist; renderer should swap in UTF-8.
    raw = b'<meta charset="bogus-charset-xyz"><p>plain text</p>'
    text, _title, charset = html_to_text.render_html(raw)
    assert "plain text" in text
    assert charset == "utf-8"


def test_ingest_html_writes_three_layers(tmp_path: Path) -> None:
    record = html_to_text.ingest_html(FIXTURE, tmp_path)
    assert record["text_chars"] > 0
    assert record["title"]

    raw_dir = tmp_path / "raw"
    struct_dir = tmp_path / "structured"
    human_dir = tmp_path / "human"
    assert any(raw_dir.iterdir())
    plaintext = next(human_dir.glob("*.txt"))
    assert plaintext.read_text().strip()
    rec_json = json.loads(next(struct_dir.glob("*.json")).read_text())
    assert rec_json["source_id"] == record["source_id"]
    assert rec_json["charset"] == "utf-8"


def test_cli_writes_manifest(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    import yaml

    manifest = tmp_path / "manifest.yaml"
    rc = html_to_text.main(
        [str(FIXTURE), "--out-dir", str(tmp_path / "out"), "--manifest", str(manifest)]
    )
    assert rc == 0

    data = yaml.safe_load(manifest.read_text())
    e = data["entries"][0]
    assert e["kind"] == "html_to_text"
    assert e["title"]
    assert e["source_id"]


def test_cli_clobber_protection(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    out = tmp_path / "out"
    manifest = tmp_path / "manifest.yaml"
    args = [str(FIXTURE), "--out-dir", str(out), "--manifest", str(manifest)]
    assert html_to_text.main(args) == 0
    assert html_to_text.main(args) == 3
    assert html_to_text.main(args + ["--force"]) == 0


def test_cli_handles_directory_input(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.html").write_text("<title>a</title><p>A body</p>")
    (src_dir / "b.htm").write_text("<title>b</title><p>B body</p>")
    (src_dir / "ignore.txt").write_text("not html")

    out = tmp_path / "out"
    rc = html_to_text.main([str(src_dir), "--out-dir", str(out)])
    assert rc == 0
    plaintexts = list((out / "human").glob("*.txt"))
    assert len(plaintexts) == 2
