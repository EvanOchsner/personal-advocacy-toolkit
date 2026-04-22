#!/usr/bin/env python3
"""PII detector + replacer for publishing derivatives.

Usage:
    python -m scripts.publish.pii_scrub \\
        --root drafts/ \\
        --substitutions substitutions.yaml \\
        [--report scrub_report.json] \\
        [--apply]

Default is --dry-run: scans files, writes a sidecar report, touches nothing.
--apply must be passed explicitly to mutate files on disk.

Hard safety rail: the scrubber refuses to run against any path that resolves
inside an `evidence/` directory. The evidence tree is read-only by contract
(see docs/concepts/evidence-integrity.md); scrubbing it would destroy the
forensic record. Publication derivatives must be written to a separate tree
(e.g. `drafts/` or `publish/`) and scrubbed there.

Detectors:
    - Substitution keys from `substitutions.yaml` (literal, case-sensitive).
    - Email addresses (RFC-5322-light).
    - US phone numbers (several common formats).
    - VINs (ISO 3779 17-char; excludes I/O/Q).
    - Policy numbers (user-supplied regex list).
    - Case numbers (user-supplied regex list, stored under the same
      `policy_number_patterns` key OR as raw substitution keys). Generic case
      numbers are hard to detect blindly without false positives, so we keep
      this driven by the user's regex list.
    - Best-effort US mailing addresses ("<number> <Word...> <St|Ave|Rd|...>").

Replacement policy:
    - If the matched span is a literal substitution key, it's replaced with
      the mapped value.
    - Otherwise the category-specific placeholder is used:
        email         -> redacted@example.invalid
        phone         -> 555-000-0000
        vin           -> VIN-REDACTED-0000
        policy_number -> POLICY-REDACTED
        address       -> [ADDRESS REDACTED]

Sidecar report:
    JSON list. Each entry:
        {
          "path": "...",
          "line": 42,
          "detector": "email",
          "original_sha256": "<hex>",   # never the original plaintext
          "replacement": "redacted@example.invalid"
        }
    The original text is hashed (not stored) so the report itself is safe
    to attach to a review ticket.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from scripts.publish._substitutions import Substitutions, load_substitutions


# --- Detectors -------------------------------------------------------------

EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# US phone numbers. Matches:
#   (555) 123-4567
#   555-123-4567
#   555.123.4567
#   5551234567
#   +1 555 123 4567
PHONE_RE = re.compile(
    r"""(?x)
    (?<!\d)                         # left boundary: not a digit
    (?:\+?1[\s.-]?)?                # optional country code
    (?:\(\d{3}\)\s?|\d{3}[\s.-])    # area code (with or without parens)
    \d{3}[\s.-]?\d{4}
    (?!\d)                          # right boundary: not a digit
    """
)

# VIN: ISO 3779, 17 alphanumeric characters, no I/O/Q.
VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")

# US mailing address, very narrow on purpose. The post-check (banned-term
# scan) is the safety net for things we miss here.
ADDRESS_RE = re.compile(
    r"""(?x)
    \b
    \d{1,6}\s+
    (?:[A-Z][A-Za-z0-9.'-]*\s+){1,5}
    (?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|
       Court|Ct|Terrace|Ter|Place|Pl|Way|Parkway|Pkwy|Highway|Hwy|Circle|Cir)
    \b\.?
    """
)


# --- Replacement constants -------------------------------------------------

PLACEHOLDER = {
    "email": "redacted@example.invalid",
    "phone": "555-000-0000",
    "vin": "VIN-REDACTED-0000",
    "policy_number": "POLICY-REDACTED",
    "address": "[ADDRESS REDACTED]",
}

# Binary-ish extensions we refuse to scrub in-place. Use a dedicated tool
# (pdf_redact, docx_metadata_scrub, exif_scrub) instead.
BINARY_EXTS = {
    ".pdf", ".docx", ".xlsx", ".pptx", ".zip", ".tar", ".gz",
    ".jpg", ".jpeg", ".png", ".gif", ".heic", ".heif", ".tiff",
    ".mp3", ".mp4", ".mov", ".wav",
}


# --- Data ------------------------------------------------------------------

@dataclass
class Change:
    path: str
    line: int
    detector: str
    original_sha256: str
    replacement: str


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# --- Core ------------------------------------------------------------------

def _contains_evidence_segment(path: Path) -> bool:
    """True if any path component equals 'evidence' (after resolution)."""
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    return any(part == "evidence" for part in resolved.parts)


def _iter_target_files(root: Path) -> Iterable[Path]:
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() in BINARY_EXTS:
            continue
        yield p


def _compile_policy_patterns(subs: Substitutions) -> list[re.Pattern[str]]:
    out: list[re.Pattern[str]] = []
    for pat in subs.policy_number_patterns:
        try:
            out.append(re.compile(pat))
        except re.error as e:
            raise ValueError(f"invalid policy_number_patterns entry {pat!r}: {e}") from e
    return out


def scrub_text(
    text: str,
    subs: Substitutions,
    policy_patterns: list[re.Pattern[str]],
    *,
    path_for_report: str = "<memory>",
) -> tuple[str, list[Change]]:
    """Return (new_text, changes) for a single text blob.

    Order of operations matters:
      1) Literal substitutions (longest key first) — these are what the user
         curated, so they take priority and win over category detectors.
      2) Policy-number patterns (user regex).
      3) Category detectors (email, phone, VIN, address).

    Each pass rewrites `text`; later passes see the already-replaced string
    so they don't re-fire on placeholders (placeholders are chosen to not
    match the detectors — e.g. `redacted@example.invalid` still matches
    EMAIL_RE, but it's also in the substitutions map as itself, so we
    short-circuit below).
    """
    changes: list[Change] = []

    # Track line numbers by keeping a running offset → line-number map.
    line_starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            line_starts.append(i + 1)

    def line_of(pos: int) -> int:
        # bisect-like
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    def record(detector: str, original: str, replacement: str, pos: int) -> None:
        changes.append(
            Change(
                path=path_for_report,
                line=line_of(pos),
                detector=detector,
                original_sha256=_sha(original),
                replacement=replacement,
            )
        )

    # --- 1) Literal substitutions (longest first) ---
    # Single forward scan: at each position, try the longest key first. This
    # avoids the "John" vs "John Doe" shadow AND prevents re-replacing our
    # own output (if the replacement text happens to contain a shorter key,
    # we skip it because the cursor has already advanced past it).
    keys_longest_first = [k for k in sorted(subs.mapping.keys(), key=len, reverse=True) if k]
    if keys_longest_first:
        out_parts: list[str] = []
        i = 0
        n = len(text)
        while i < n:
            matched = None
            for key in keys_longest_first:
                if text.startswith(key, i):
                    matched = key
                    break
            if matched is not None:
                repl = subs.mapping[matched]
                record("substitution", matched, repl, i)
                out_parts.append(repl)
                i += len(matched)
            else:
                out_parts.append(text[i])
                i += 1
        text = "".join(out_parts)
        # Recompute line_starts since text length may have changed.
        line_starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                line_starts.append(i + 1)

    def sub_regex(pat: re.Pattern[str], detector: str, placeholder: str) -> None:
        nonlocal text, line_starts

        def _replace(m: re.Match[str]) -> str:
            original = m.group(0)
            # If the matched literal is already a substitution key (e.g. the
            # user's placeholder domain), the literal pass already handled
            # it; skip.
            if original in subs.mapping:
                return original
            record(detector, original, placeholder, m.start())
            return placeholder

        text = pat.sub(_replace, text)
        line_starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                line_starts.append(i + 1)

    # --- 2) Policy-number user regexes ---
    for pat in policy_patterns:
        sub_regex(pat, "policy_number", PLACEHOLDER["policy_number"])

    # --- 3) Category detectors ---
    sub_regex(EMAIL_RE, "email", PLACEHOLDER["email"])
    sub_regex(PHONE_RE, "phone", PLACEHOLDER["phone"])
    sub_regex(VIN_RE, "vin", PLACEHOLDER["vin"])
    sub_regex(ADDRESS_RE, "address", PLACEHOLDER["address"])

    return text, changes


def post_check_banned(text: str, banned_terms: list[str]) -> list[str]:
    """Return list of banned terms still present in text."""
    hits = []
    for term in banned_terms:
        if term and term in text:
            hits.append(term)
    return hits


def scrub_tree(
    root: Path,
    subs: Substitutions,
    *,
    apply: bool,
) -> tuple[list[Change], list[str]]:
    """Scrub a directory. Returns (changes, survivors).

    `survivors` is a list of `"<path>: <banned-term>"` strings — any banned
    term that our detectors missed but is known to be sensitive. If this is
    non-empty after --apply, the caller MUST treat it as a hard failure.
    """
    if _contains_evidence_segment(root):
        raise RuntimeError(
            f"refusing to scrub under an 'evidence/' path: {root}. "
            "The evidence tree is read-only by contract. Copy the files "
            "to a derivative tree (e.g. drafts/) and scrub there."
        )

    policy_patterns = _compile_policy_patterns(subs)
    banned = subs.banned_terms

    all_changes: list[Change] = []
    survivors: list[str] = []

    for p in _iter_target_files(root):
        try:
            original = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Skip non-UTF8 blobs; they shouldn't be in a text-drafts tree.
            continue

        new_text, changes = scrub_text(
            original, subs, policy_patterns, path_for_report=str(p)
        )
        all_changes.extend(changes)

        post_hits = post_check_banned(new_text, banned)
        for term in post_hits:
            # The hashed term is still discoverable via substitutions.yaml,
            # but we never write the plaintext into this report file.
            survivors.append(f"{p}: banned-term-survived sha256={_sha(term)}")

        if apply and new_text != original:
            p.write_text(new_text, encoding="utf-8")

    return all_changes, survivors


def _write_report(report_path: Path, changes: list[Change], survivors: list[str]) -> None:
    payload = {
        "changes": [c.__dict__ for c in changes],
        "survivors": survivors,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True, help="Tree to scrub.")
    ap.add_argument(
        "--substitutions",
        type=Path,
        required=True,
        help="Path to substitutions.yaml.",
    )
    ap.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Where to write the sidecar JSON report (default: <root>/.pii_scrub_report.json).",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Actually mutate files. Default is a dry-run.",
    )
    args = ap.parse_args(argv)

    subs = load_substitutions(args.substitutions)

    try:
        changes, survivors = scrub_tree(args.root, subs, apply=args.apply)
    except RuntimeError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2

    report_path = args.report or (args.root / ".pii_scrub_report.json")
    _write_report(report_path, changes, survivors)

    mode = "applied" if args.apply else "dry-run"
    print(
        f"{mode}: {len(changes)} changes across {len({c.path for c in changes})} files; "
        f"report -> {report_path}"
    )
    if survivors:
        print(
            f"POST-CHECK FAIL: {len(survivors)} banned-term survivors "
            "(see report 'survivors' field).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
