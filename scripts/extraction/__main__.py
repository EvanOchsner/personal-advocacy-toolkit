"""CLI entry point: ``uv run python -m scripts.extraction <file>``.

Replaces the per-format CLIs (``pdf_to_text``, ``html_to_text``,
``email_eml_to_json``). Auto-detects type by extension; writes the
three-layer outputs and (when ``--case-root`` is supplied) the
reproducibility script.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .vlm import available_providers
from .writer import write_three_layer


def _expand_inputs(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    suffixes = {".pdf", ".html", ".htm", ".xhtml", ".eml", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif"}
    for p in paths:
        if p.is_dir():
            out.extend(sorted(q for q in p.iterdir() if q.suffix.lower() in suffixes))
        else:
            out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Layered document → searchable plaintext extraction.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("inputs", nargs="*", type=Path)
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="Where raw/, structured/, readable/ subdirs are written.")
    ap.add_argument("--case-root", type=Path, default=None,
                    help="Case workspace root. When provided, overrides at "
                         "extraction/overrides/<id>.yaml are honored and the "
                         "reproducibility script is written.")
    ap.add_argument("--manifest", type=Path, default=None)
    ap.add_argument("--manifest-kind", type=str, default=None,
                    help="Override the manifest 'kind' field (default: extract_<type>).")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite an existing manifest entry with the same source_id.")
    ap.add_argument("--vlm-provider", default=None,
                    choices=("tesseract", "olmocr", "claude", "openai", "http"),
                    help="VLM provider for tier-2 PDF fallback. Default: tesseract.")
    ap.add_argument("--non-interactive", action="store_true",
                    help="Refuse to prompt for VLM consent (for scripted runs).")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="Log tier transitions to stderr.")
    ap.add_argument("--list-providers", action="store_true",
                    help="Print VLM provider availability and exit.")
    args = ap.parse_args(argv)

    if args.list_providers:
        for row in available_providers():
            avail = "yes" if row.get("available") else "no"
            net = "(network)" if row.get("requires_network") else "(local)"
            hint = f" — install: {row['hint']}" if not row.get("available") else ""
            print(f"  {row['name']:10s} {net:10s} available={avail}{hint}")
        return 0

    if not args.inputs:
        print("no inputs provided", file=sys.stderr)
        return 2

    if args.out_dir is None:
        print("--out-dir is required (or use --list-providers)", file=sys.stderr)
        return 2

    files = _expand_inputs(args.inputs)
    if not files:
        print("no extractable inputs found", file=sys.stderr)
        return 2

    rc = 0
    for src in files:
        if not src.is_file():
            print(f"skip: {src} (not a file)", file=sys.stderr)
            rc = 1
            continue
        try:
            record = write_three_layer(
                src,
                args.out_dir,
                case_root=args.case_root,
                vlm_provider=args.vlm_provider,
                interactive=not args.non_interactive,
                verbose=args.verbose,
                manifest_path=args.manifest,
                manifest_kind=args.manifest_kind,
                force=args.force,
            )
        except FileExistsError as exc:
            print(str(exc), file=sys.stderr)
            rc = 3
            continue
        except ValueError as exc:
            print(f"skip: {src}: {exc}", file=sys.stderr)
            rc = 1
            continue
        print(
            f"{src} -> {record['source_id']}: tier {record['tier']} "
            f"via {record['method']} ({record['text_chars']} chars)"
        )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
