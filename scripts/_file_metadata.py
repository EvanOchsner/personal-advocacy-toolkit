"""Cross-platform file-metadata reader for download provenance.

Three platforms, three different mechanisms, one normalized output:

- macOS    -> Extended attributes via the `xattr` CLI (part of every
              macOS install; Python's `os.listxattr` is Linux-only and
              not available here).  kMDItemWhereFroms (binary plist of
              source URLs) and com.apple.quarantine (semicolon record
              with UTC timestamp) are auto-populated by Safari, Mail,
              and Finder.
- Linux    -> POSIX extended attributes via os.getxattr (stdlib, no
              shell-out). user.xdg.origin.url and user.xdg.referrer.url
              are defined by XDG and populated by Firefox; rare
              elsewhere.
- Windows  -> NTFS Alternate Data Streams: open `path:Zone.Identifier`
              and parse the [ZoneTransfer] INI block (HostUrl,
              ReferrerUrl, ZoneId). Auto-populated by IE/Edge/Chrome/
              Firefox/Outlook on NTFS volumes.

`read_raw` returns a flat name->str dict, identical in shape to the
existing provenance_snapshot xattrs payload (so the snapshot JSON
schema does not break). Windows ADS lands under a synthetic
`win.zone_identifier` key.

`normalize` decodes platform-specific formats and produces a common
shape with origin_urls / referrer_url / download_timestamp_iso / zone
fields plus a `decoded` block for platform-specific structured data.

`platform_capability` lets callers distinguish "no metadata" from
"platform doesn't support extended attributes" in user-facing output.
"""

from __future__ import annotations

import configparser
import io
import os
import plistlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Platform capability
# ---------------------------------------------------------------------------


def platform_capability() -> str:
    """Return the metadata mechanism this platform offers.

    - "macos-xattr"   — macOS, via the `xattr` CLI.
    - "posix-xattr"   — Linux/BSD, via stdlib `os.listxattr`.
    - "windows-ads"   — Windows, via NTFS Alternate Data Streams.
    - "unsupported"   — anything else (rare).
    """
    if sys.platform == "darwin":
        return "macos-xattr"
    if sys.platform == "win32":
        return "windows-ads"
    if hasattr(os, "listxattr"):
        return "posix-xattr"
    return "unsupported"


# ---------------------------------------------------------------------------
# Layer 1: raw read
# ---------------------------------------------------------------------------


def _run_xattr(args: list[str]) -> tuple[int, bytes]:
    """Run `xattr <args>` and return (returncode, stdout-bytes).

    Maps a missing `xattr` binary (FileNotFoundError) to exit code 127
    so callers can treat "binary missing" the same as "binary returned
    non-zero" and fall through to an empty result.
    """
    try:
        r = subprocess.run(
            ["xattr", *args], capture_output=True, check=False
        )
    except FileNotFoundError:
        return 127, b""
    return r.returncode, r.stdout


def _read_macos_xattrs(path: Path) -> dict[str, str]:
    """Read every xattr on `path` via the macOS `xattr` CLI.

    Python's `os.listxattr` / `os.getxattr` are Linux-only, so on macOS
    we shell out. Names come from `xattr <path>`; values come from
    `xattr -px <name> <path>` (hex-encoded so binary blobs like the
    kMDItemWhereFroms plist round-trip cleanly). Hex output is stored
    with the `hex:` prefix the rest of the pipeline uses.
    """
    rc, out = _run_xattr([str(path)])
    if rc != 0 or not out:
        return {}
    names = [n for n in out.decode("utf-8", errors="replace").splitlines() if n]
    result: dict[str, str] = {}
    for name in names:
        rc2, raw = _run_xattr(["-px", name, str(path)])
        if rc2 != 0:
            continue
        # `xattr -px` emits a hex dump with whitespace; strip it.
        hex_str = raw.decode("ascii", errors="replace").replace(" ", "").replace("\n", "")
        if not hex_str:
            continue
        try:
            decoded = bytes.fromhex(hex_str)
        except ValueError:
            continue
        try:
            result[name] = decoded.decode("utf-8")
        except UnicodeDecodeError:
            result[name] = "hex:" + hex_str
    return result


def _read_posix_xattrs(path: Path) -> dict[str, str]:
    """Read every xattr on `path` (POSIX). Decode UTF-8; hex-prefix on failure."""
    try:
        names = os.listxattr(str(path), follow_symlinks=False)
    except (OSError, NotImplementedError):
        return {}
    out: dict[str, str] = {}
    for name in names:
        try:
            raw = os.getxattr(str(path), name, follow_symlinks=False)
        except OSError:
            continue
        try:
            out[name] = raw.decode("utf-8")
        except UnicodeDecodeError:
            out[name] = "hex:" + raw.hex()
    return out


def _read_windows_zone_identifier(path: Path) -> dict[str, str]:
    """Read NTFS Zone.Identifier ADS, if present.

    Returns `{"win.zone_identifier": <ini-block>}` when the stream
    exists, else `{}`. Errors (non-NTFS volume, permission) are
    swallowed — the caller treats absence the same as "no metadata".
    """
    stream = f"{path}:Zone.Identifier"
    try:
        with open(stream, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except (FileNotFoundError, OSError):
        return {}
    if not text.strip():
        return {}
    return {"win.zone_identifier": text}


def read_raw(path: Path) -> dict[str, str]:
    """Cross-platform raw metadata read.

    Returns a flat name->str dict. Empty if the platform offers no
    mechanism or the file has nothing.
    """
    cap = platform_capability()
    if cap == "macos-xattr":
        return _read_macos_xattrs(path)
    if cap == "posix-xattr":
        return _read_posix_xattrs(path)
    if cap == "windows-ads":
        return _read_windows_zone_identifier(path)
    return {}


# ---------------------------------------------------------------------------
# Layer 2: decoders
# ---------------------------------------------------------------------------


_QUARANTINE_RE = re.compile(
    r"^([0-9a-f]+);([0-9a-f]+);([^;]+);([^;]*)$", re.IGNORECASE
)

# ZoneId values per the documented Windows zones.
_ZONE_LABELS = {
    "0": "MyComputer",
    "1": "LocalIntranet",
    "2": "TrustedSites",
    "3": "Internet",
    "4": "RestrictedSites",
}


def decode_quarantine(value: str) -> dict[str, Any] | None:
    """Decode `com.apple.quarantine` semicolon-separated fields.

    Format: `<flag>;<hex-unix-ts>;<app>;<uuid>`.
    """
    m = _QUARANTINE_RE.match(value.strip())
    if not m:
        return None
    flag, hex_ts, app, uuid = m.groups()
    try:
        ts = int(hex_ts, 16)
        iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except ValueError:
        iso = None
    return {
        "flag": flag,
        "timestamp_hex": hex_ts,
        "timestamp_iso": iso,
        "app": app,
        "uuid": uuid,
    }


def decode_wherefroms(value: str) -> list[str]:
    """Decode kMDItemWhereFroms into a list of source URLs.

    Safari/Mail/Finder write the value as a binary plist (an array of
    URL strings). Our raw reader stores binary blobs as `hex:<hex>`.
    A few less-common cases also surface here:

    - `hex:<hex>` of a binary plist  -> the normal case.
    - Hex without the prefix          -> legacy `xattr -l` text rendering.
    - Plain URL string                -> set manually with `xattr -w`,
                                         or by tools that store a single
                                         URL as a UTF-8 string.

    Returns [] if none of the above decode cleanly.
    """
    text = value.strip()

    # Plain URL-string fallback: covers the manual-xattr and any tool
    # that wrote a single URL as a UTF-8 string rather than a plist.
    if text.startswith(("http://", "https://", "file://")):
        return [text]

    if text.startswith("hex:"):
        try:
            data = bytes.fromhex(text[4:])
        except ValueError:
            return []
    else:
        # Legacy `xattr -l` text rendering — bytes as space/newline-
        # separated hex pairs.  bytes.fromhex tolerates whitespace.
        try:
            data = bytes.fromhex(text.replace(" ", "").replace("\n", ""))
        except ValueError:
            return []
    try:
        plist = plistlib.loads(data)
    except (ValueError, plistlib.InvalidFileException):
        return []
    if isinstance(plist, list):
        return [str(x) for x in plist if x]
    return []


def decode_zone_identifier(text: str) -> dict[str, Any] | None:
    """Parse a Windows Zone.Identifier INI block.

    Returns a dict with `zone_id`, `zone_label`, `host_url`,
    `referrer_url` keys (any may be absent). Returns None if the block
    has no recognizable [ZoneTransfer] section.
    """
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        parser.read_file(io.StringIO(text))
    except configparser.Error:
        return None
    if not parser.has_section("ZoneTransfer"):
        return None
    section = parser["ZoneTransfer"]
    zone_id = section.get("ZoneId")
    out: dict[str, Any] = {}
    if zone_id is not None:
        out["zone_id"] = zone_id
        out["zone_label"] = _ZONE_LABELS.get(zone_id.strip())
    host = section.get("HostUrl")
    if host:
        out["host_url"] = host.strip()
    ref = section.get("ReferrerUrl")
    if ref:
        out["referrer_url"] = ref.strip()
    return out or None


# ---------------------------------------------------------------------------
# Layer 3: normalize
# ---------------------------------------------------------------------------


def normalize(raw: dict[str, str]) -> dict[str, Any]:
    """Apply platform-specific decoders to a raw read; return common shape.

    Caller owns whether `raw` came from a live read or a historical
    snapshot — both have the same name->str shape, and snapshot data
    captured on a different platform still decodes correctly here
    (e.g., a macOS snapshot read on a Linux server).
    """
    decoded: dict[str, Any] = {
        "wherefroms": None,
        "quarantine": None,
        "xdg": None,
        "zone_identifier": None,
    }

    origin_urls: list[str] = []
    referrer_url: str | None = None
    download_timestamp_iso: str | None = None
    zone: str | None = None

    # macOS: kMDItemWhereFroms + com.apple.quarantine
    wf_value = raw.get("com.apple.metadata:kMDItemWhereFroms")
    if wf_value:
        urls = decode_wherefroms(wf_value)
        if urls:
            decoded["wherefroms"] = urls
            origin_urls.extend(urls)
            # Convention: WhereFroms[0] is the source URL, WhereFroms[1]
            # is the referring page URL when the file was clicked from
            # one. Only set referrer if absent and we have a candidate.
            if len(urls) >= 2 and referrer_url is None:
                referrer_url = urls[1]

    q_value = raw.get("com.apple.quarantine")
    if q_value:
        q = decode_quarantine(q_value)
        if q:
            decoded["quarantine"] = q
            if q.get("timestamp_iso"):
                download_timestamp_iso = q["timestamp_iso"]

    # Linux: XDG attrs (also reachable on macOS if a Linux user copied
    # a file across with xattrs preserved — decode regardless).
    xdg_origin = raw.get("user.xdg.origin.url")
    xdg_referrer = raw.get("user.xdg.referrer.url")
    if xdg_origin or xdg_referrer:
        decoded["xdg"] = {
            "origin_url": xdg_origin,
            "referrer_url": xdg_referrer,
        }
        if xdg_origin and xdg_origin not in origin_urls:
            origin_urls.append(xdg_origin)
        if xdg_referrer and not referrer_url:
            referrer_url = xdg_referrer

    # Windows: Zone.Identifier ADS
    zi_text = raw.get("win.zone_identifier")
    if zi_text:
        zi = decode_zone_identifier(zi_text)
        if zi:
            decoded["zone_identifier"] = zi
            if zi.get("host_url") and zi["host_url"] not in origin_urls:
                origin_urls.append(zi["host_url"])
            if zi.get("referrer_url") and not referrer_url:
                referrer_url = zi["referrer_url"]
            if zi.get("zone_label"):
                zone = zi["zone_label"]

    return {
        "raw": dict(raw),
        "attribute_names": sorted(raw.keys()),
        "origin_urls": origin_urls,
        "referrer_url": referrer_url,
        "download_timestamp_iso": download_timestamp_iso,
        "zone": zone,
        "decoded": decoded,
    }


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------


def read_and_normalize(path: Path) -> dict[str, Any]:
    """Read raw metadata for `path` and return the normalized common shape.

    Adds `platform` and `capability` fields so callers can distinguish
    "absent because unsupported" from "absent because empty".
    """
    raw = read_raw(path)
    out = normalize(raw)
    out["platform"] = sys.platform
    out["capability"] = platform_capability()
    out["present"] = bool(raw)
    return out
