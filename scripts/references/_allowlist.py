"""Load and enforce the trusted-source allow/denylist.

The allowlist policy lives in ``data/reference_sources.yaml``. This
module reads it once per process and exposes a small API:

    classify(host) -> "primary" | "secondary-trusted" | "secondary-confirm"
                      | "denied" | "unknown"

    classify_url(url) -> same as above (extracts host)

    load_directory() -> dict mapping (kind, jurisdiction) -> list of
                        curated sources for Path B "project-known"
                        source presentation.

`classify` returns ``"unknown"`` for hosts that are neither on the
allowlist nor the denylist. The fetcher's policy is to refuse "unknown"
without explicit user confirmation; "denied" is hard-refused; "primary"
and "secondary-trusted" fetch with the standard confirm prompt;
"secondary-confirm" requires the user to type the host explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_SOURCES_PATH = REPO_ROOT / "data" / "reference_sources.yaml"


@dataclass(frozen=True)
class HostClassification:
    verdict: str  # "primary" | "secondary-trusted" | "secondary-confirm" | "denied" | "unknown"
    matched_pattern: str | None = None
    reason: str | None = None  # populated for "denied"


def _load_yaml(path: Path) -> dict[str, Any]:
    import yaml  # PyYAML is a hard project dep

    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _host_of(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return host.lower()


def classify(host: str, *, source_path: Path | None = None) -> HostClassification:
    """Classify a hostname against the allow/denylist.

    Denylist takes precedence over allowlist.
    """
    if not host:
        return HostClassification("unknown")
    data = _load_yaml(source_path or REFERENCE_SOURCES_PATH)
    deny: list[dict[str, Any]] = data.get("denylist_domains") or []
    for entry in deny:
        pattern = entry.get("domain", "")
        if pattern and fnmatch(host, pattern):
            return HostClassification(
                verdict="denied",
                matched_pattern=pattern,
                reason=entry.get("reason") or "denylisted",
            )
    allow: list[dict[str, Any]] = data.get("allowlist_domains") or []
    for entry in allow:
        pattern = entry.get("domain", "")
        if pattern and fnmatch(host, pattern):
            return HostClassification(
                verdict=entry.get("trust") or "primary",
                matched_pattern=pattern,
            )
    return HostClassification("unknown")


def classify_url(url: str, *, source_path: Path | None = None) -> HostClassification:
    return classify(_host_of(url), source_path=source_path)


def load_directory(
    source_path: Path | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Return a dict keyed by (kind, jurisdiction) → entry.

    Entries preserve the original ``label``, ``sources``, and ``note``
    fields so callers can present them to the user verbatim.
    """
    data = _load_yaml(source_path or REFERENCE_SOURCES_PATH)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for kind, juris_map in (data.get("source_directory") or {}).items():
        if not isinstance(juris_map, dict):
            continue
        for jurisdiction, entry in juris_map.items():
            if not isinstance(entry, dict):
                continue
            out[(str(kind), str(jurisdiction))] = entry
    return out


def lookup_directory(
    kind: str,
    jurisdiction: str,
    *,
    source_path: Path | None = None,
) -> dict[str, Any] | None:
    """Lookup curated sources for ``(kind, jurisdiction)``.

    Falls back to ``(kind, "*")`` if the specific jurisdiction is not
    listed (e.g., ToS is jurisdiction-agnostic).
    """
    directory = load_directory(source_path=source_path)
    if (kind, jurisdiction) in directory:
        return directory[(kind, jurisdiction)]
    if (kind, "*") in directory:
        return directory[(kind, "*")]
    return None
