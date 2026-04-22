"""Smoke tests for the Phase-1 correspondence-ingest toolchain.

Fixtures are authored inline with obviously-fake addresses
(`alice@example.com` / `bob@insco.example`). No real case data.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from scripts.ingest import email_eml_to_json, email_json_to_txt, mbox_split
from scripts.manifest import correspondence_manifest as cm


# --------------------------------------------------------------------------- #
# Inline fake .eml / .mbox fixtures
# --------------------------------------------------------------------------- #


EML_SIMPLE = textwrap.dedent(
    """\
    From: Alice Example <alice@example.com>
    To: Bob Insco <bob@insco.example>
    Cc: Clerk <clerk@insco.example>
    Subject: Invoice #42 for policy review
    Date: Wed, 15 May 2024 09:45:00 +0000
    Message-ID: <msg-001@example.com>
    X-Claim-Number: ACR61-3
    MIME-Version: 1.0
    Content-Type: text/plain; charset=utf-8

    Hello Bob,

    Attaching invoice #42. Please confirm receipt.

    Thanks,
    Alice
    """
).encode("utf-8")


EML_MULTIPART = (
    b"From: Bob Insco <bob@insco.example>\r\n"
    b"To: Alice Example <alice@example.com>\r\n"
    b"Subject: Re: Claim status\r\n"
    b"Date: Thu, 16 May 2024 10:00:00 +0000\r\n"
    b"Message-ID: <msg-002@insco.example>\r\n"
    b"MIME-Version: 1.0\r\n"
    b'Content-Type: multipart/alternative; boundary="BOUND"\r\n'
    b"\r\n"
    b"--BOUND\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"\r\n"
    b"Coverage denied per policy section 4.\r\n"
    b"--BOUND\r\n"
    b"Content-Type: text/html; charset=utf-8\r\n"
    b"\r\n"
    b"<p>Coverage denied per policy section 4.</p>\r\n"
    b"--BOUND--\r\n"
)


EML_UNRELATED = textwrap.dedent(
    """\
    From: Newsletter <news@newsletter.example>
    To: Alice Example <alice@example.com>
    Subject: Weekly digest
    Date: Fri, 17 May 2024 08:00:00 +0000
    Message-ID: <msg-003@newsletter.example>
    MIME-Version: 1.0
    Content-Type: text/plain; charset=utf-8

    This week's top stories...
    """
).encode("utf-8")


@pytest.fixture
def eml_dir(tmp_path: Path) -> Path:
    d = tmp_path / "raw"
    d.mkdir()
    (d / "simple.eml").write_bytes(EML_SIMPLE)
    (d / "multipart.eml").write_bytes(EML_MULTIPART)
    (d / "unrelated.eml").write_bytes(EML_UNRELATED)
    return d


@pytest.fixture
def mbox_file(tmp_path: Path) -> Path:
    mbox = tmp_path / "inbox.mbox"
    # mbox format: "From " separator line per message.
    parts: list[bytes] = []
    for body in (EML_SIMPLE, EML_MULTIPART, EML_UNRELATED):
        parts.append(b"From sender@example.com Wed May 15 00:00:00 2024\n")
        # Normalize CRLF→LF so mbox's blank-line/"From "-detection works.
        normalized = body.replace(b"\r\n", b"\n")
        parts.append(normalized)
        if not normalized.endswith(b"\n"):
            parts.append(b"\n")
        parts.append(b"\n")  # blank line before next "From " separator
    mbox.write_bytes(b"".join(parts))
    return mbox


# --------------------------------------------------------------------------- #
# email_eml_to_json
# --------------------------------------------------------------------------- #


def test_parse_eml_plaintext(eml_dir: Path) -> None:
    rec = email_eml_to_json.parse_eml(eml_dir / "simple.eml")
    assert rec["subject"] == "Invoice #42 for policy review"
    assert rec["from"] == [{"name": "Alice Example", "email": "alice@example.com"}]
    assert {"name": "Bob Insco", "email": "bob@insco.example"} in rec["to"]
    assert rec["date_iso"].startswith("2024-05-15T09:45:00")
    assert "Attaching invoice #42" in rec["body_text"]
    assert rec["headers"]["X-Claim-Number"] == "ACR61-3"
    assert rec["attachments"] == []
    assert len(rec["source_sha256"]) == 64


def test_parse_eml_multipart(eml_dir: Path) -> None:
    rec = email_eml_to_json.parse_eml(eml_dir / "multipart.eml")
    assert rec["body_text"] and "Coverage denied" in rec["body_text"]
    assert rec["body_html"] and "<p>" in rec["body_html"]


def test_eml_to_json_cli_writes_files(eml_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "json"
    rc = email_eml_to_json.main(
        [str(eml_dir), "--out-dir", str(out), "--overwrite"]
    )
    assert rc == 0
    files = sorted(p.name for p in out.glob("*.json"))
    assert files == ["multipart.json", "simple.json", "unrelated.json"]
    rec = json.loads((out / "simple.json").read_text())
    assert rec["message_id"] == "<msg-001@example.com>"


# --------------------------------------------------------------------------- #
# email_json_to_txt
# --------------------------------------------------------------------------- #


def test_json_to_txt_roundtrip(eml_dir: Path, tmp_path: Path) -> None:
    jdir = tmp_path / "json"
    email_eml_to_json.main([str(eml_dir), "--out-dir", str(jdir), "--overwrite"])
    tdir = tmp_path / "txt"
    rc = email_json_to_txt.main([str(jdir), "--out-dir", str(tdir), "--overwrite"])
    assert rc == 0
    text = (tdir / "simple.txt").read_text()
    assert "Subject: Invoice #42 for policy review" in text
    assert "alice@example.com" in text
    assert "Attaching invoice #42" in text


# --------------------------------------------------------------------------- #
# mbox_split
# --------------------------------------------------------------------------- #


def test_mbox_split_unfiltered(mbox_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "split"
    written = mbox_split.split_mbox(mbox_file, out, prefix="all")
    assert len(written) == 3
    # All outputs are readable as .eml by the parser.
    for p in written:
        rec = email_eml_to_json.parse_eml(p)
        assert rec["subject"]


def test_mbox_split_with_filter_config(mbox_file: Path, tmp_path: Path) -> None:
    cfg_path = tmp_path / "cfg.yaml"
    cfg_path.write_text(
        "parties:\n"
        "  - '@insco.example'\n"
        "subject_regex:\n"
        "  - '(?i)claim'\n"
    )
    # Skip gracefully when PyYAML is absent in the environment.
    pytest.importorskip("yaml")
    cfg = cm.load_config(cfg_path)
    predicate = lambda msg: cm.message_matches(msg, cfg)  # noqa: E731
    out = tmp_path / "split"
    written = mbox_split.split_mbox(mbox_file, out, prefix="claim", predicate=predicate)
    # Only the "Re: Claim status" message should survive.
    assert len(written) == 1
    rec = email_eml_to_json.parse_eml(written[0])
    assert "Claim status" in (rec["subject"] or "")


# --------------------------------------------------------------------------- #
# correspondence_manifest
# --------------------------------------------------------------------------- #


def test_manifest_matches_expected(eml_dir: Path, tmp_path: Path) -> None:
    cfg = {
        "parties": ["@insco.example"],
        "subject_regex": [r"(?i)claim|invoice"],
    }
    manifest = cm.build_manifest([eml_dir], cfg)
    subjects = {e["subject"] for e in manifest["entries"]}
    assert subjects == {
        "Invoice #42 for policy review",
        "Re: Claim status",
    }
    assert manifest["count"] == 2


def test_manifest_date_range(eml_dir: Path) -> None:
    cfg = {"date_range": {"start": "2024-05-16", "end": "2024-05-16"}}
    manifest = cm.build_manifest([eml_dir], cfg)
    assert manifest["count"] == 1
    assert manifest["entries"][0]["message_id"] == "<msg-002@insco.example>"


def test_manifest_identifiers_and_header_contains(eml_dir: Path) -> None:
    # Header substring hit.
    cfg_header = {"header_contains": {"X-Claim-Number": ["ACR61-3"]}}
    m1 = cm.build_manifest([eml_dir], cfg_header)
    assert m1["count"] == 1
    # Free-form identifier hit (searches subject + body + headers).
    cfg_id = {"identifiers": ["ACR61-3"]}
    m2 = cm.build_manifest([eml_dir], cfg_id)
    assert m2["count"] == 1


def test_manifest_empty_config_matches_all(eml_dir: Path) -> None:
    manifest = cm.build_manifest([eml_dir], {})
    assert manifest["count"] == 3


def test_manifest_cli_writes_json(eml_dir: Path, tmp_path: Path) -> None:
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps({"parties": ["alice@example.com"]}))
    out = tmp_path / "manifest.json"
    rc = cm.main(
        ["--config", str(cfg_path), "--out", str(out), str(eml_dir)]
    )
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["count"] == 3  # alice appears on all three
    assert "generated_at" in data
