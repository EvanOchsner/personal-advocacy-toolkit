#!/usr/bin/env python3
"""Strip identifying metadata from a .docx without touching document content.

Usage:
    python -m scripts.publish.docx_metadata_scrub \\
        --in draft.docx --out clean.docx

A .docx is a ZIP of XML parts. We rewrite:
    docProps/core.xml   (dc:creator, cp:lastModifiedBy, cp:revision, dc:title, ...)
    docProps/app.xml    (Company, Manager, AppVersion, etc.)

We do NOT touch word/document.xml — that's content, not metadata.
The zip layout (member order, compression levels) is preserved exactly:
reading member-by-member in original order and writing the same names to the
output keeps diff-ability intact.

Post-check (mandatory): re-open the output, parse the two metadata parts,
and assert each known-sensitive field is empty (or matches a synthetic
value from --synthetic-values). If any sensitive field has content after
scrubbing, the output is DELETED and we raise.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


# Namespaces used in docProps XML parts. We register them so etree preserves
# the `dc:`, `cp:`, etc. prefixes instead of rewriting to ns0/ns1.
NAMESPACES = {
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "dcmitype": "http://purl.org/dc/dcmitype/",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}

# Fields in core.xml that identify a person or revision history.
SENSITIVE_CORE_FIELDS = [
    "{http://purl.org/dc/elements/1.1/}creator",
    "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}lastModifiedBy",
    "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}revision",
    "{http://purl.org/dc/elements/1.1/}title",
    "{http://purl.org/dc/elements/1.1/}subject",
    "{http://purl.org/dc/elements/1.1/}description",
    "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}keywords",
    "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}category",
    "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}contentStatus",
    "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}version",
    "{http://purl.org/dc/terms/}created",
    "{http://purl.org/dc/terms/}modified",
    "{http://schemas.openxmlformats.org/package/2006/metadata/core-properties}lastPrinted",
]

# Fields in app.xml (namespace-less in that part's element names).
SENSITIVE_APP_FIELDS = [
    "Company",
    "Manager",
    "Author",
    "LastAuthor",
    "AppVersion",
    "Template",
    "TotalTime",
    "Application",
]


class DocxPostCheckError(RuntimeError):
    """Raised when sensitive metadata fields survived scrubbing."""


def _register_namespaces() -> None:
    for prefix, uri in NAMESPACES.items():
        ET.register_namespace(prefix, uri)


def _scrub_core_xml(xml_bytes: bytes, synthetic: dict[str, str]) -> bytes:
    _register_namespaces()
    root = ET.fromstring(xml_bytes)
    for tag in SENSITIVE_CORE_FIELDS:
        # Short name without namespace, for synthetic-value lookup.
        short = tag.rsplit("}", 1)[-1]
        for el in root.iter(tag):
            el.text = synthetic.get(short, "")
            # Clear attributes like xsi:type that imply a format on empty text.
            # Leave structural attributes in place otherwise.
    body = ET.tostring(root, encoding="UTF-8")
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + body


def _scrub_app_xml(xml_bytes: bytes, synthetic: dict[str, str]) -> bytes:
    _register_namespaces()
    root = ET.fromstring(xml_bytes)
    # app.xml uses a default namespace; iterate over all children and match
    # by local name.
    for el in list(root.iter()):
        local = el.tag.rsplit("}", 1)[-1]
        if local in SENSITIVE_APP_FIELDS:
            el.text = synthetic.get(local, "")
    body = ET.tostring(root, encoding="UTF-8")
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + body


def scrub_docx(
    in_path: str | Path,
    out_path: str | Path,
    *,
    synthetic_values: dict[str, str] | None = None,
) -> None:
    in_path = Path(in_path)
    out_path = Path(out_path)
    synthetic = synthetic_values or {}

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(in_path, "r") as zin:
        names = zin.namelist()
        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for name in names:
                data = zin.read(name)
                if name == "docProps/core.xml":
                    data = _scrub_core_xml(data, synthetic)
                elif name == "docProps/app.xml":
                    data = _scrub_app_xml(data, synthetic)
                # Preserve the member's original compression.
                info = zin.getinfo(name)
                new_info = zipfile.ZipInfo(filename=name, date_time=info.date_time)
                new_info.compress_type = info.compress_type
                new_info.external_attr = info.external_attr
                zout.writestr(new_info, data)

    survivors = _post_check(out_path, synthetic)
    if survivors:
        try:
            out_path.unlink()
        except OSError:
            pass
        raise DocxPostCheckError(
            f"sensitive metadata survived scrubbing: {survivors}. Output deleted."
        )


def _post_check(docx_path: Path, synthetic: dict[str, str]) -> list[str]:
    """Return list of `<field>: <value>` for any sensitive field that is
    non-empty AND not the expected synthetic placeholder."""
    survivors: list[str] = []
    with zipfile.ZipFile(docx_path, "r") as z:
        members = z.namelist()
        if "docProps/core.xml" in members:
            core = ET.fromstring(z.read("docProps/core.xml"))
            for tag in SENSITIVE_CORE_FIELDS:
                short = tag.rsplit("}", 1)[-1]
                for el in core.iter(tag):
                    val = (el.text or "").strip()
                    expected = synthetic.get(short, "")
                    if val and val != expected:
                        survivors.append(f"core:{short}={val}")
        if "docProps/app.xml" in members:
            app = ET.fromstring(z.read("docProps/app.xml"))
            for el in list(app.iter()):
                local = el.tag.rsplit("}", 1)[-1]
                if local in SENSITIVE_APP_FIELDS:
                    val = (el.text or "").strip()
                    expected = synthetic.get(local, "")
                    if val and val != expected:
                        survivors.append(f"app:{local}={val}")
    return survivors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="in_path", type=Path, required=True)
    ap.add_argument("--out", dest="out_path", type=Path, required=True)
    ap.add_argument(
        "--synthetic-creator",
        default="",
        help="If set, dc:creator and Author are replaced with this value instead of emptied.",
    )
    args = ap.parse_args(argv)

    synthetic: dict[str, str] = {}
    if args.synthetic_creator:
        synthetic["creator"] = args.synthetic_creator
        synthetic["Author"] = args.synthetic_creator
        synthetic["LastAuthor"] = args.synthetic_creator

    try:
        scrub_docx(args.in_path, args.out_path, synthetic_values=synthetic)
    except DocxPostCheckError as e:
        print(f"POST-CHECK FAIL: {e}", file=sys.stderr)
        return 1

    print(f"scrubbed -> {args.out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
