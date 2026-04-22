"""Packet-manifest loader and validators.

The manifest schema is documented in
`templates/packet-manifests/schema.yaml`. This module does the minimum
required to load a manifest, resolve relative paths against the
manifest's own directory, and surface clear errors early so downstream
tools don't fail with cryptic tracebacks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_SCHEMA_VERSIONS = {"1.0"}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class ManifestError(ValueError):
    """Raised for any manifest-shape problem the user should fix."""


@dataclass
class Exhibit:
    label: str
    title: str
    description: str
    source: Path | None = None
    sources: list[Path] = field(default_factory=list)
    date: str | None = None
    no_separator: bool = False

    @property
    def all_sources(self) -> list[Path]:
        if self.source is not None:
            return [self.source]
        return list(self.sources)


@dataclass
class ReferenceAppendix:
    name: str
    title: str
    sources: list[Path]
    note: str | None = None


@dataclass
class Authority:
    name: str
    short_code: str
    mailing_address: str | None = None
    intake_url: str | None = None


@dataclass
class Party:
    name: str
    role: str | None = None
    reference_number: str | None = None
    mailing_address: str | None = None
    email: str | None = None
    phone: str | None = None


@dataclass
class Complaint:
    title: str
    source: Path | None = None
    docx_source: Path | None = None


@dataclass
class PacketManifest:
    manifest_path: Path
    schema_version: str
    name: str
    authority: Authority
    complainant: Party
    respondent: Party
    complaint: Complaint
    output_dir: Path
    exhibits: list[Exhibit]
    reference_appendices: list[ReferenceAppendix]

    @property
    def base_dir(self) -> Path:
        return self.manifest_path.parent


def load_manifest(path: str | Path) -> PacketManifest:
    """Load a manifest from disk and return a validated PacketManifest.

    Paths inside the manifest are resolved relative to the manifest's
    own directory so a manifest moves cleanly with its evidence tree.
    """
    path = Path(path).resolve()
    if not path.is_file():
        raise ManifestError(f"Manifest not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ManifestError("Manifest root must be a mapping.")

    schema_version = str(raw.get("schema_version", "")).strip()
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ManifestError(
            f"Unsupported schema_version {schema_version!r}. "
            f"Supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )

    packet = raw.get("packet")
    if not isinstance(packet, dict):
        raise ManifestError("Missing or malformed `packet:` section.")

    name = str(packet.get("name", "")).strip()
    if not NAME_RE.match(name):
        raise ManifestError(
            f"packet.name {name!r} must match {NAME_RE.pattern!r} "
            "(lowercase letters, digits, and hyphens)."
        )

    authority = _parse_authority(packet.get("authority"))
    complainant = _parse_party(packet.get("complainant"), role_label="complainant")
    respondent = _parse_party(packet.get("respondent"), role_label="respondent")
    complaint = _parse_complaint(packet.get("complaint"), base=path.parent)

    output_dir_raw = packet.get("output_dir")
    if not output_dir_raw:
        raise ManifestError("packet.output_dir is required.")
    output_dir = (path.parent / str(output_dir_raw)).resolve()

    exhibits = _parse_exhibits(packet.get("exhibits") or [], base=path.parent)
    ref_apps = _parse_reference_appendices(
        packet.get("reference_appendices") or [], base=path.parent
    )

    return PacketManifest(
        manifest_path=path,
        schema_version=schema_version,
        name=name,
        authority=authority,
        complainant=complainant,
        respondent=respondent,
        complaint=complaint,
        output_dir=output_dir,
        exhibits=exhibits,
        reference_appendices=ref_apps,
    )


def _parse_authority(raw: Any) -> Authority:
    if not isinstance(raw, dict):
        raise ManifestError("packet.authority must be a mapping.")
    name = str(raw.get("name", "")).strip()
    short_code = str(raw.get("short_code", "")).strip()
    if not name or not short_code:
        raise ManifestError("packet.authority requires both `name` and `short_code`.")
    return Authority(
        name=name,
        short_code=short_code,
        mailing_address=_opt_str(raw.get("mailing_address")),
        intake_url=_opt_str(raw.get("intake_url")),
    )


def _parse_party(raw: Any, *, role_label: str) -> Party:
    if raw is None:
        return Party(name="")
    if not isinstance(raw, dict):
        raise ManifestError(f"packet.{role_label} must be a mapping.")
    name = str(raw.get("name", "")).strip()
    if not name:
        raise ManifestError(f"packet.{role_label}.name is required.")
    return Party(
        name=name,
        role=_opt_str(raw.get("role")),
        reference_number=_opt_str(raw.get("reference_number")),
        mailing_address=_opt_str(raw.get("mailing_address")),
        email=_opt_str(raw.get("email")),
        phone=_opt_str(raw.get("phone")),
    )


def _parse_complaint(raw: Any, *, base: Path) -> Complaint:
    if not isinstance(raw, dict):
        raise ManifestError("packet.complaint must be a mapping.")
    src = raw.get("source")
    docx = raw.get("docx_source")
    if not src and not docx:
        raise ManifestError(
            "packet.complaint requires either `source` or `docx_source`."
        )
    return Complaint(
        title=str(raw.get("title") or "Complaint Narrative"),
        source=(base / str(src)).resolve() if src else None,
        docx_source=(base / str(docx)).resolve() if docx else None,
    )


def _parse_exhibits(raw: list[Any], *, base: Path) -> list[Exhibit]:
    exhibits: list[Exhibit] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ManifestError(f"Exhibit #{i + 1} must be a mapping.")
        label = str(item.get("label") or _default_label(i)).strip()
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        if not title:
            raise ManifestError(f"Exhibit #{i + 1} requires a `title`.")
        src_raw = item.get("source")
        srcs_raw = item.get("sources")
        if src_raw and srcs_raw:
            raise ManifestError(
                f"Exhibit {label}: set either `source` or `sources`, not both."
            )
        if not src_raw and not srcs_raw:
            raise ManifestError(
                f"Exhibit {label}: one of `source` or `sources` is required."
            )
        source = (base / str(src_raw)).resolve() if src_raw else None
        sources: list[Path] = []
        if srcs_raw:
            if not isinstance(srcs_raw, list):
                raise ManifestError(
                    f"Exhibit {label}: `sources` must be a list."
                )
            sources = [(base / str(s)).resolve() for s in srcs_raw]
        exhibits.append(
            Exhibit(
                label=label,
                title=title,
                description=description,
                source=source,
                sources=sources,
                date=_opt_str(item.get("date")),
                no_separator=bool(item.get("no_separator", False)),
            )
        )
    return exhibits


def _parse_reference_appendices(
    raw: list[Any], *, base: Path
) -> list[ReferenceAppendix]:
    out: list[ReferenceAppendix] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ManifestError(f"reference_appendices[{i}] must be a mapping.")
        name = str(item.get("name") or "").strip()
        title = str(item.get("title") or "").strip()
        srcs = item.get("sources") or []
        if not name or not title or not srcs:
            raise ManifestError(
                f"reference_appendices[{i}] requires name, title, and sources."
            )
        if not NAME_RE.match(name):
            raise ManifestError(
                f"reference_appendices[{i}].name {name!r} must match {NAME_RE.pattern!r}."
            )
        out.append(
            ReferenceAppendix(
                name=name,
                title=title,
                sources=[(base / str(s)).resolve() for s in srcs],
                note=_opt_str(item.get("note")),
            )
        )
    return out


def _opt_str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _default_label(index: int) -> str:
    """A, B, C, ..., Z, AA, AB, ..."""
    out = ""
    n = index
    while True:
        out = chr(ord("A") + (n % 26)) + out
        n = n // 26 - 1
        if n < 0:
            return out
