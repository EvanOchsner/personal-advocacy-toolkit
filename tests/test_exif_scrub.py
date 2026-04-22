"""Tests for scripts.publish.exif_scrub.

Primary test: inject EXIF + GPS + a custom tag into a synthetic JPEG and
verify (a) the scrub removes it, (b) the post-check reports any file that
still has EXIF after a simulated partial scrub.
"""
from __future__ import annotations

from pathlib import Path

import pytest

Image = pytest.importorskip("PIL.Image")
from PIL import Image as PILImage  # noqa: E402


def _make_jpeg_with_exif(path: Path) -> None:
    """Write a tiny JPEG and embed a minimal EXIF block with a GPS tag."""
    im = PILImage.new("RGB", (8, 8), color=(200, 50, 50))
    # Pillow 10+: use Image.Exif to build an EXIF block.
    exif = im.getexif()
    # 0x0110 = Model, 0x010F = Make (both standard EXIF-IFD tags).
    exif[0x010F] = "SynthCamCo"
    exif[0x0110] = "Model-X1"
    # 0x8825 = GPS IFD pointer — assigning a non-empty IFD signals GPS data.
    gps_ifd = exif.get_ifd(0x8825)
    gps_ifd[1] = "N"   # GPSLatitudeRef
    im.save(path, format="JPEG", exif=exif)


def test_scrub_removes_exif_and_gps(tmp_path: Path) -> None:
    from scripts.publish import exif_scrub

    img = tmp_path / "photo.jpg"
    _make_jpeg_with_exif(img)

    # Baseline: the source file has EXIF.
    with PILImage.open(img) as im:
        assert im._getexif() is not None  # noqa: SLF001

    result = exif_scrub.scrub_image(img, apply=True)
    assert result.scrubbed is True
    assert result.survivors == [], f"survivors after scrub: {result.survivors}"

    # Post-check independently.
    with PILImage.open(img) as im:
        exif = im._getexif()  # noqa: SLF001
        assert not exif, f"exif not cleared: {dict(exif) if exif else exif}"


def test_post_check_reports_surviving_exif(tmp_path: Path) -> None:
    """Dry-run mode (apply=False) should still run the post-check and
    report that the file has EXIF present — otherwise a user who forgot
    --apply could ship the file thinking it was clean."""
    from scripts.publish import exif_scrub

    img = tmp_path / "photo.jpg"
    _make_jpeg_with_exif(img)

    result = exif_scrub.scrub_image(img, apply=False)
    assert result.scrubbed is False
    assert result.survivors, "dry-run must still report surviving EXIF"
    # At least one reason cites EXIF presence.
    assert any("exif" in s.lower() for s in result.survivors)


def test_batch_scrub_tree(tmp_path: Path) -> None:
    from scripts.publish import exif_scrub

    root = tmp_path / "images"
    root.mkdir()
    for i in range(3):
        _make_jpeg_with_exif(root / f"photo_{i}.jpg")

    rc = exif_scrub.main(["--root", str(root), "--apply"])
    assert rc == 0  # all clean


def test_cli_returns_1_if_survivors(tmp_path: Path) -> None:
    from scripts.publish import exif_scrub

    root = tmp_path / "images"
    root.mkdir()
    _make_jpeg_with_exif(root / "photo.jpg")

    # Dry-run: EXIF still there, should exit 1.
    rc = exif_scrub.main(["--root", str(root)])
    assert rc == 1
