"""Tests for scripts.publish.docx_metadata_scrub.

Primary test: inject author/company/lastModifiedBy values into a synthetic
.docx and verify (a) they are stripped, (b) document.xml is byte-for-byte
unchanged, (c) the post-check catches a simulated failure where a scrubber
forgot to clear a field.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.publish import docx_metadata_scrub as dmd  # noqa: E402


CORE_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>John Doe</dc:creator>
  <cp:lastModifiedBy>John Doe</cp:lastModifiedBy>
  <cp:revision>42</cp:revision>
  <dc:title>Secret Draft</dc:title>
  <dcterms:created xsi:type="dcterms:W3CDTF">2025-01-01T00:00:00Z</dcterms:created>
</cp:coreProperties>
"""

APP_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Company>Acme Legal LLC</Company>
  <Manager>Jane Doe</Manager>
  <AppVersion>16.0000</AppVersion>
</Properties>
"""

DOCUMENT_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>Body text.</w:t></w:r></w:p></w:body>
</w:document>
"""


def _make_docx(path: Path, *, core: bytes = CORE_XML, app: bytes = APP_XML,
               document: bytes = DOCUMENT_XML) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", b"<Types/>")
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)
        z.writestr("word/document.xml", document)


def test_scrub_clears_sensitive_fields(tmp_path: Path) -> None:
    src = tmp_path / "draft.docx"
    dst = tmp_path / "clean.docx"
    _make_docx(src)

    dmd.scrub_docx(src, dst)

    with zipfile.ZipFile(dst, "r") as z:
        core = z.read("docProps/core.xml").decode("utf-8")
        app = z.read("docProps/app.xml").decode("utf-8")
        # document.xml preserved exactly.
        assert z.read("word/document.xml") == DOCUMENT_XML

    assert "John Doe" not in core
    assert "Acme Legal LLC" not in app
    assert "Jane Doe" not in app
    # revision cleared
    assert "<cp:revision>42" not in core


def test_post_check_catches_missed_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If a core-xml scrubber silently skipped clearing `dc:creator`, the
    post-check must catch it and delete the output."""
    src = tmp_path / "draft.docx"
    dst = tmp_path / "clean.docx"
    _make_docx(src)

    # Sabotage the core-xml scrub: return the input unchanged.
    monkeypatch.setattr(dmd, "_scrub_core_xml", lambda data, synthetic: data)

    with pytest.raises(dmd.DocxPostCheckError, match="creator"):
        dmd.scrub_docx(src, dst)
    assert not dst.exists()


def test_synthetic_values_replace(tmp_path: Path) -> None:
    src = tmp_path / "draft.docx"
    dst = tmp_path / "clean.docx"
    _make_docx(src)

    dmd.scrub_docx(src, dst, synthetic_values={"creator": "Advocacy Toolkit"})

    with zipfile.ZipFile(dst, "r") as z:
        core = z.read("docProps/core.xml").decode("utf-8")
    assert "Advocacy Toolkit" in core
    assert "John Doe" not in core


def test_zip_layout_preserved(tmp_path: Path) -> None:
    """Member ordering is preserved — users can diff before/after zips
    member-by-member without noise."""
    src = tmp_path / "draft.docx"
    dst = tmp_path / "clean.docx"
    _make_docx(src)

    with zipfile.ZipFile(src, "r") as z:
        src_names = z.namelist()
    dmd.scrub_docx(src, dst)
    with zipfile.ZipFile(dst, "r") as z:
        dst_names = z.namelist()
    assert dst_names == src_names
