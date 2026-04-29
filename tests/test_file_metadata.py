"""Tests for scripts._file_metadata cross-platform reader."""
from __future__ import annotations

import os
import plistlib
import sys
from pathlib import Path

import pytest

from scripts._file_metadata import (
    decode_quarantine,
    decode_wherefroms,
    decode_zone_identifier,
    normalize,
    platform_capability,
    read_and_normalize,
    read_raw,
)


# -----------------------------------------------------------------------------
# Platform capability
# -----------------------------------------------------------------------------


def test_platform_capability_returns_known_value() -> None:
    cap = platform_capability()
    assert cap in {"macos-xattr", "posix-xattr", "windows-ads", "unsupported"}


def test_platform_capability_matches_sys_platform() -> None:
    cap = platform_capability()
    if sys.platform == "darwin":
        assert cap == "macos-xattr"
    elif sys.platform == "win32":
        assert cap == "windows-ads"
    elif hasattr(os, "listxattr"):
        assert cap == "posix-xattr"
    else:
        assert cap == "unsupported"


# -----------------------------------------------------------------------------
# Decoders (platform-agnostic — pure-string input)
# -----------------------------------------------------------------------------


def test_decode_quarantine_parses_fields() -> None:
    out = decode_quarantine("0081;67380000;Safari;ABCD-1234")
    assert out is not None
    assert out["flag"] == "0081"
    assert out["app"] == "Safari"
    assert out["uuid"] == "ABCD-1234"
    assert out["timestamp_iso"] is not None


def test_decode_quarantine_rejects_garbage() -> None:
    assert decode_quarantine("not-a-record") is None


def test_decode_wherefroms_round_trips_hex_prefixed_bplist() -> None:
    urls = ["https://example.com/form", "https://example.com/index"]
    bplist = plistlib.dumps(urls, fmt=plistlib.FMT_BINARY)
    assert decode_wherefroms("hex:" + bplist.hex()) == urls


def test_decode_wherefroms_accepts_legacy_unprefixed_hex() -> None:
    # Back-compat with the legacy `xattr -px` form (no `hex:` prefix).
    urls = ["https://example.com/file.pdf"]
    bplist = plistlib.dumps(urls, fmt=plistlib.FMT_BINARY)
    assert decode_wherefroms(bplist.hex()) == urls


def test_decode_wherefroms_handles_garbage() -> None:
    assert decode_wherefroms("not-hex") == []
    assert decode_wherefroms("hex:deadbeef") == []


def test_decode_wherefroms_accepts_plain_url_string() -> None:
    # Manual `xattr -w` and some tools store a single URL as a plain
    # UTF-8 string rather than a binary plist.
    assert decode_wherefroms("https://example.com/file") == ["https://example.com/file"]
    assert decode_wherefroms("http://example.com/x") == ["http://example.com/x"]


def test_decode_zone_identifier_full_block() -> None:
    text = (
        "[ZoneTransfer]\n"
        "ZoneId=3\n"
        "HostUrl=https://example.com/file.pdf\n"
        "ReferrerUrl=https://example.com/page\n"
    )
    zi = decode_zone_identifier(text)
    assert zi == {
        "zone_id": "3",
        "zone_label": "Internet",
        "host_url": "https://example.com/file.pdf",
        "referrer_url": "https://example.com/page",
    }


def test_decode_zone_identifier_only_zone_id() -> None:
    zi = decode_zone_identifier("[ZoneTransfer]\nZoneId=4\n")
    assert zi == {"zone_id": "4", "zone_label": "RestrictedSites"}


def test_decode_zone_identifier_unknown_zone_id() -> None:
    zi = decode_zone_identifier("[ZoneTransfer]\nZoneId=99\n")
    assert zi == {"zone_id": "99", "zone_label": None}


def test_decode_zone_identifier_no_section() -> None:
    assert decode_zone_identifier("just some text\n") is None


def test_decode_zone_identifier_empty_block() -> None:
    # Section present but no fields.
    assert decode_zone_identifier("[ZoneTransfer]\n") is None


# -----------------------------------------------------------------------------
# normalize() — platform-agnostic, takes raw dict input
# -----------------------------------------------------------------------------


def test_normalize_empty_input() -> None:
    out = normalize({})
    assert out["origin_urls"] == []
    assert out["referrer_url"] is None
    assert out["download_timestamp_iso"] is None
    assert out["zone"] is None
    assert out["decoded"] == {
        "wherefroms": None,
        "quarantine": None,
        "xdg": None,
        "zone_identifier": None,
    }


def test_normalize_macos_wherefroms_and_quarantine() -> None:
    urls = ["https://insurer.example.com/form.pdf", "https://insurer.example.com/portal"]
    bplist = plistlib.dumps(urls, fmt=plistlib.FMT_BINARY)
    raw = {
        "com.apple.metadata:kMDItemWhereFroms": "hex:" + bplist.hex(),
        "com.apple.quarantine": "0081;67380000;Safari;UUID-XYZ",
    }
    out = normalize(raw)
    assert out["origin_urls"] == urls
    assert out["referrer_url"] == "https://insurer.example.com/portal"
    assert out["download_timestamp_iso"] is not None
    assert out["decoded"]["wherefroms"] == urls
    assert out["decoded"]["quarantine"]["app"] == "Safari"


def test_normalize_linux_xdg_attrs() -> None:
    raw = {
        "user.xdg.origin.url": "https://example.com/file.pdf",
        "user.xdg.referrer.url": "https://example.com/page",
    }
    out = normalize(raw)
    assert out["origin_urls"] == ["https://example.com/file.pdf"]
    assert out["referrer_url"] == "https://example.com/page"
    assert out["download_timestamp_iso"] is None
    assert out["decoded"]["xdg"] == {
        "origin_url": "https://example.com/file.pdf",
        "referrer_url": "https://example.com/page",
    }


def test_normalize_windows_zone_identifier() -> None:
    raw = {
        "win.zone_identifier": (
            "[ZoneTransfer]\n"
            "ZoneId=3\n"
            "HostUrl=https://insurer.example.com/form.pdf\n"
            "ReferrerUrl=https://insurer.example.com/portal\n"
        )
    }
    out = normalize(raw)
    assert out["origin_urls"] == ["https://insurer.example.com/form.pdf"]
    assert out["referrer_url"] == "https://insurer.example.com/portal"
    assert out["zone"] == "Internet"
    assert out["decoded"]["zone_identifier"]["zone_id"] == "3"


def test_normalize_dedupes_origin_urls_across_sources() -> None:
    # Same URL declared under macOS and XDG attrs (as can happen if a
    # file was copied across platforms with xattrs preserved).
    url = "https://example.com/x"
    bplist = plistlib.dumps([url], fmt=plistlib.FMT_BINARY)
    raw = {
        "com.apple.metadata:kMDItemWhereFroms": "hex:" + bplist.hex(),
        "user.xdg.origin.url": url,
    }
    out = normalize(raw)
    assert out["origin_urls"] == [url]  # not duplicated


# -----------------------------------------------------------------------------
# read_raw() — platform-specific integration tests
# -----------------------------------------------------------------------------


@pytest.mark.skipif(
    sys.platform != "linux" or not hasattr(os, "setxattr"),
    reason="Linux-only integration test (uses os.setxattr)",
)
def test_read_raw_round_trips_linux_xattr(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("contents")
    try:
        os.setxattr(
            str(f),
            "user.xdg.origin.url",
            b"https://example.com/file.txt",
            follow_symlinks=False,
        )
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"filesystem does not support xattrs here: {e}")
    raw = read_raw(f)
    assert raw.get("user.xdg.origin.url") == "https://example.com/file.txt"


@pytest.mark.skipif(
    sys.platform != "darwin",
    reason="macOS-only integration test (uses the `xattr` CLI)",
)
def test_read_raw_round_trips_macos_xattr(tmp_path: Path) -> None:
    import subprocess as _subprocess

    f = tmp_path / "file.txt"
    f.write_text("contents")
    rc = _subprocess.run(
        ["xattr", "-w", "user.test.attr", "hello", str(f)],
        capture_output=True,
    ).returncode
    if rc != 0:
        pytest.skip("xattr CLI failed to set test attribute")
    raw = read_raw(f)
    assert raw.get("user.test.attr") == "hello"


def test_read_and_normalize_returns_platform_fields(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("contents")
    out = read_and_normalize(f)
    assert out["platform"] == sys.platform
    assert out["capability"] in {
        "macos-xattr", "posix-xattr", "windows-ads", "unsupported"
    }
    assert "origin_urls" in out
    assert "decoded" in out


def test_read_raw_on_clean_file_is_empty(tmp_path: Path) -> None:
    f = tmp_path / "untouched.txt"
    f.write_text("nothing here")
    raw = read_raw(f)
    # Either empty (no xattrs / no ADS) or, on some systems, contains
    # OS-injected attrs we don't care about. The contract is that no
    # *download-provenance* keys leak in for a freshly-written file.
    assert "com.apple.metadata:kMDItemWhereFroms" not in raw
    assert "user.xdg.origin.url" not in raw
    assert "win.zone_identifier" not in raw
