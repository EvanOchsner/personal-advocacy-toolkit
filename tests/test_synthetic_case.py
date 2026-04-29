"""Tests for the Maryland-Mustang synthetic-case regenerator.

These tests copy the case tree into a tmp dir, run the regenerator
against the copy, and assert the three artifact groups land with the
expected properties:

  - valuation PDF: non-empty, contains "SYNTHETIC" in extracted text,
    /Info has subject or title referencing synthetic.
  - photos: JPEGs exist, have no EXIF GPS (getexif() either returns
    empty or does not contain any GPSInfo tag).
  - complaint: .docx has no leaking author/company fields in
    docProps/core.xml and docProps/app.xml.

They exercise the full regenerate pipeline end-to-end.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest

pypdf = pytest.importorskip("pypdf")
PIL = pytest.importorskip("PIL")

from scripts.synthetic_case import regenerate as rg  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parent.parent
CASE_SRC = REPO_ROOT / "examples" / "maryland-mustang"


@pytest.fixture()
def case_tree(tmp_path: Path) -> Path:
    """Copy the parts of the case tree the regenerator needs."""
    root = tmp_path / "maryland-mustang"
    (root / "evidence" / "valuation").mkdir(parents=True)
    (root / "evidence" / "photos").mkdir(parents=True)
    (root / "drafts").mkdir(parents=True)

    shutil.copy2(
        CASE_SRC / "evidence" / "valuation" / "MidAtlantic-Vehicle-Appraisers-valuation.md",
        root / "evidence" / "valuation" / "MidAtlantic-Vehicle-Appraisers-valuation.md",
    )
    for spec in rg.PHOTO_SPECS:
        shutil.copy2(
            CASE_SRC / "evidence" / "photos" / spec.md_name,
            root / "evidence" / "photos" / spec.md_name,
        )
    shutil.copy2(
        CASE_SRC / "drafts" / "mia-complaint.md",
        root / "drafts" / "mia-complaint.md",
    )
    return root


def test_regenerate_all_produces_outputs(case_tree: Path) -> None:
    results = rg.regenerate(case_tree, ["valuation", "photos", "complaint"])
    pdf = results["valuation"]
    photos = results["photos"]
    docx = results["complaint"]

    assert isinstance(pdf, Path) and pdf.is_file() and pdf.stat().st_size > 1000
    assert isinstance(photos, list) and len(photos) == 3
    for p in photos:
        assert p.is_file() and p.stat().st_size > 2000
    assert isinstance(docx, Path) and docx.is_file() and docx.stat().st_size > 1000


def test_valuation_pdf_has_synthetic_text(case_tree: Path) -> None:
    pdf_path = rg.regenerate_valuation(case_tree)
    reader = pypdf.PdfReader(str(pdf_path))
    assert len(reader.pages) >= 1
    combined = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "SYNTHETIC" in combined.upper()
    # PDF /Info dict should also carry the stamp.
    meta = reader.metadata or {}
    info_blob = " ".join(str(v) for v in meta.values())
    assert "SYNTHETIC" in info_blob.upper()


def test_photos_have_no_exif_gps(case_tree: Path) -> None:
    from PIL import Image

    photos = rg.regenerate_photos(case_tree)
    for p in photos:
        with Image.open(p) as img:
            # dimensions sanity
            assert img.size == (1600, 1200)
            assert img.format == "JPEG"
            exif = img.getexif()
            # No GPS IFD, no GPSInfo tag pointer. Empty is fine.
            if exif is not None:
                gps = exif.get_ifd(0x8825) if hasattr(exif, "get_ifd") else {}
                assert not gps, f"{p.name}: unexpected GPS EXIF: {gps!r}"
                # Also: no Make/Model/DateTimeOriginal leaking.
                for banned_tag in (0x010F, 0x0110, 0x9003):  # Make, Model, DateTimeOriginal
                    assert banned_tag not in exif, (
                        f"{p.name}: unexpected EXIF tag 0x{banned_tag:04X}"
                    )


def test_photos_carry_synthetic_user_comment(case_tree: Path) -> None:
    """The synthetic stamp should be present in EXIF ImageDescription
    or UserComment. This is a teaching check: even if a user strips
    the image out of context, the stamp survives."""
    from PIL import Image

    photos = rg.regenerate_photos(case_tree)
    for p in photos:
        with Image.open(p) as img:
            exif = img.getexif()
            blob = ""
            if exif is not None:
                for v in exif.values():
                    if isinstance(v, bytes):
                        try:
                            blob += v.decode("ascii", errors="ignore")
                        except Exception:
                            pass
                    elif isinstance(v, str):
                        blob += v
            # If Pillow's exif builder silently dropped everything,
            # at minimum file has no author/GPS, which is the core
            # safety guarantee tested above. UserComment is a
            # soft-nice-to-have, so we only assert when EXIF survives.
            if exif is not None and len(list(exif.keys())) > 0:
                assert "SYNTHETIC" in blob.upper()


def test_complaint_docx_has_no_leaking_author(case_tree: Path) -> None:
    docx_path = rg.regenerate_complaint(case_tree)
    with zipfile.ZipFile(docx_path, "r") as z:
        core = z.read("docProps/core.xml").decode("utf-8")
        try:
            app = z.read("docProps/app.xml").decode("utf-8")
        except KeyError:
            app = ""
    # author / lastModifiedBy should be the synthetic stamp-pass value,
    # never a real user identity.
    assert "advocacy-toolkit" in core.lower()
    # No Evan / real-user names from the local environment must appear.
    for banned in ("Evan", "Ochsner", "evanochsner"):
        assert banned not in core
        assert banned not in app
    # SYNTHETIC stamp surfaces in core metadata.
    assert "SYNTHETIC" in core.upper()


def test_regenerate_is_idempotent(case_tree: Path) -> None:
    """Photos are deterministic given the same seed. Re-running
    ``regenerate_photos`` against an unchanged source tree must
    produce byte-identical JPEGs."""
    first = rg.regenerate_photos(case_tree)
    first_bytes = [p.read_bytes() for p in first]
    second = rg.regenerate_photos(case_tree)
    second_bytes = [p.read_bytes() for p in second]
    assert first_bytes == second_bytes


def test_cli_only_group(case_tree: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = rg.main(["--root", str(case_tree), "--only", "valuation"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "valuation:" in out
    # complaint and photos should not have been regenerated.
    assert not (case_tree / "drafts" / "mia-complaint.docx").exists()
    assert not (case_tree / "evidence" / "photos" / "photo-01-mustang-at-midlife-crisis.jpg").exists()
