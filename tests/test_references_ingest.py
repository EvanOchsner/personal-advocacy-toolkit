"""Tests for scripts.references.ingest end-to-end (file-mode)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from scripts.references import ingest

DISCLAIMER = "This is reference information, not legal advice."

SAMPLE_HTML = """\
<html><head><title>§ 27-303 — Unfair claim settlement practices</title></head>
<body>
  <h1>Md. Code Ins. § 27-303</h1>
  <p>(a) In general. — A person may not engage in any of the following practices:</p>
  <ol>
    <li>misrepresenting pertinent facts;</li>
    <li>failing to acknowledge claims with reasonable promptness;</li>
    <li>refusing to pay a claim without conducting a reasonable investigation
        based on all available information.</li>
  </ol>
  <p>(b) Effective date. — This section is effective as of October 1, 2017.</p>
</body>
</html>
"""


def _make_case(tmp_path: Path) -> Path:
    case = tmp_path / "case"
    (case / "references" / "raw").mkdir(parents=True)
    (case / "references" / "structured").mkdir(parents=True)
    (case / "references" / "readable").mkdir(parents=True)
    return case


def test_file_ingest_lands_three_layers(tmp_path: Path) -> None:
    case = _make_case(tmp_path)
    src = tmp_path / "src.html"
    src.write_text(SAMPLE_HTML)

    sidecar = ingest.ingest(
        case_root=case,
        raw_bytes=src.read_bytes(),
        content_type="text/html",
        kind="statute",
        citation="Md. Code Ins. § 27-303",
        title=None,
        jurisdiction="MD",
        source_origin="user-supplied",
        source_url=None,
        source_label="hand-saved",
        source_filename=str(src),
    )

    raw_path = case / sidecar["raw_path"]
    readable_path = case / sidecar["readable_path"]
    struct_path = case / "references" / "structured" / "md-code-ins-27-303.json"

    assert raw_path.is_file()
    assert readable_path.is_file()
    assert struct_path.is_file()
    assert sidecar["disclaimer"] == DISCLAIMER
    assert sidecar["citation"] == "Md. Code Ins. § 27-303"
    assert sidecar["jurisdiction"] == "MD"
    assert sidecar["extraction"]["method"] == "html-to-text"
    assert sidecar["extraction"]["text_chars"] > 100


def test_file_ingest_writes_manifest_and_sha256(tmp_path: Path) -> None:
    case = _make_case(tmp_path)
    src = tmp_path / "src.html"
    src.write_text(SAMPLE_HTML)

    ingest.ingest(
        case_root=case,
        raw_bytes=src.read_bytes(),
        content_type="text/html",
        kind="statute",
        citation="Md. Code Ins. § 27-303",
        title=None,
        jurisdiction="MD",
        source_origin="user-supplied",
        source_url=None,
        source_label=None,
        source_filename=str(src),
    )
    manifest_yaml = case / "references" / ".references-manifest.yaml"
    sha_manifest = case / ".references-manifest.sha256"
    assert manifest_yaml.is_file()
    assert sha_manifest.is_file()

    data = yaml.safe_load(manifest_yaml.read_text(encoding="utf-8"))
    assert len(data["entries"]) == 1
    assert data["entries"][0]["citation"] == "Md. Code Ins. § 27-303"

    rows = sha_manifest.read_text(encoding="utf-8").strip().splitlines()
    # Three files (raw, readable, structured); README isn't auto-written
    # because we created the dirs by hand here.
    assert len(rows) == 3


def test_clobber_protection(tmp_path: Path) -> None:
    case = _make_case(tmp_path)
    src = tmp_path / "src.html"
    src.write_text(SAMPLE_HTML)
    raw = src.read_bytes()
    ingest.ingest(
        case_root=case,
        raw_bytes=raw,
        content_type="text/html",
        kind="statute",
        citation="Md. Code Ins. § 27-303",
        title=None,
        jurisdiction="MD",
        source_origin="user-supplied",
        source_url=None,
        source_label=None,
        source_filename=str(src),
    )
    with pytest.raises(FileExistsError):
        ingest.ingest(
            case_root=case,
            raw_bytes=raw,  # same bytes -> same source_id
            content_type="text/html",
            kind="statute",
            citation="Md. Code Ins. § 27-303",
            title=None,
            jurisdiction="MD",
            source_origin="user-supplied",
            source_url=None,
            source_label=None,
            source_filename=str(src),
        )


def test_force_replaces_manifest_entry(tmp_path: Path) -> None:
    case = _make_case(tmp_path)
    src = tmp_path / "src.html"
    src.write_text(SAMPLE_HTML)
    raw = src.read_bytes()
    ingest.ingest(
        case_root=case,
        raw_bytes=raw,
        content_type="text/html",
        kind="statute",
        citation="Md. Code Ins. § 27-303",
        title="old title",
        jurisdiction="MD",
        source_origin="user-supplied",
        source_url=None,
        source_label=None,
        source_filename=str(src),
    )
    sidecar2 = ingest.ingest(
        case_root=case,
        raw_bytes=raw,
        content_type="text/html",
        kind="statute",
        citation="Md. Code Ins. § 27-303",
        title="new title",
        jurisdiction="MD",
        source_origin="user-supplied",
        source_url=None,
        source_label=None,
        source_filename=str(src),
        force=True,
    )
    assert sidecar2["title"] == "new title"


def test_slug_collision_appends_suffix(tmp_path: Path) -> None:
    case = _make_case(tmp_path)
    raw1 = b"<p>first version</p>"
    raw2 = b"<p>second version, different bytes</p>"
    s1 = ingest.ingest(
        case_root=case,
        raw_bytes=raw1,
        content_type="text/html",
        kind="statute",
        citation="Same Citation",
        title=None,
        jurisdiction="MD",
        source_origin="user-supplied",
        source_url=None,
        source_label=None,
        source_filename="src.html",
    )
    s2 = ingest.ingest(
        case_root=case,
        raw_bytes=raw2,
        content_type="text/html",
        kind="statute",
        citation="Same Citation",
        title=None,
        jurisdiction="MD",
        source_origin="user-supplied",
        source_url=None,
        source_label=None,
        source_filename="src.html",
    )
    assert s1["raw_path"] != s2["raw_path"]
    # second ingest's slug ends with -2
    assert s2["raw_path"].endswith("-2.html")


def test_unknown_kind_rejected(tmp_path: Path) -> None:
    case = _make_case(tmp_path)
    with pytest.raises(ValueError):
        ingest.ingest(
            case_root=case,
            raw_bytes=b"<p>x</p>",
            content_type="text/html",
            kind="invalid-kind",
            citation=None,
            title=None,
            jurisdiction=None,
            source_origin="user-supplied",
            source_url=None,
            source_label=None,
            source_filename="x.html",
        )


def test_cli_main_with_file(tmp_path: Path, capsys) -> None:
    case = _make_case(tmp_path)
    src = tmp_path / "src.html"
    src.write_text(SAMPLE_HTML)
    rc = ingest.main(
        [
            "--file", str(src),
            "--kind", "statute",
            "--citation", "Md. Code Ins. § 27-303",
            "--jurisdiction", "MD",
            "--case-root", str(case),
        ]
    )
    assert rc == 0
    captured = capsys.readouterr().out
    assert "ingested" in captured
    assert DISCLAIMER in captured


def test_cli_with_format_json(tmp_path: Path, capsys) -> None:
    case = _make_case(tmp_path)
    src = tmp_path / "src.html"
    src.write_text(SAMPLE_HTML)
    rc = ingest.main(
        [
            "--file", str(src),
            "--kind", "statute",
            "--citation", "Md. Code Ins. § 27-303",
            "--jurisdiction", "MD",
            "--case-root", str(case),
            "--format", "json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["disclaimer"] == DISCLAIMER
    assert payload["kind"] == "statute"
