"""Heuristic completeness check for user-supplied reference docs.

The agent uses these heuristics to flag possible problems with a copy
of a statute, regulation, official policy, or ToS that the user
provided themselves. The user makes the final call on whether to trust
the doc — this module only surfaces what's visible.

The output shape is:

    {
      "appears_complete": bool,   # overall heuristic verdict
      "flags": [
        {"code": str, "level": "info"|"warn", "detail": str},
        ...
      ],
      "stats": {
        "char_count": int,
        "line_count": int,
        ...
      }
    }

Codes:

    truncation-suspected    Text ends mid-word, mid-sentence, or with "..."
    short-for-kind          Length is below a typical floor for this kind
    no-effective-date       No "as of" / "effective" / version marker found
    has-truncation-marker   Contains literal "[truncated]", "...", "(continued)", etc.
    looks-like-excerpt      Headers like "EXCERPT", "PARTIAL", "SAMPLE"
    no-section-numbers      No section / paragraph markers found (for statutes/regs)
    has-watermark           Contains common watermark text ("DRAFT", "CONFIDENTIAL")
    encoding-issues         Replacement characters or mojibake patterns

None of the flags are pass/fail by themselves; the agent presents them
to the user with the verbatim guidance from the SKILL.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Minimum plaintext length we'd expect for various kinds. Below this is
# suspicious; well above is fine. These are pre-filter heuristics, not
# hard rules — a single short statute could legitimately be 500 chars.
KIND_MIN_CHARS = {
    "statute": 400,
    "regulation": 400,
    "official-policy": 800,
    "tos": 1500,
    "guidance": 400,
    "case-law": 800,
    "other": 0,
}

_TRUNCATION_MARKERS = [
    "[truncated]",
    "[...]",
    "(continued on next page)",
    "* * *",
    "...",
]
_EXCERPT_HEADERS = re.compile(
    r"\b(excerpt|partial|sample|preview)\b",
    re.IGNORECASE,
)
_WATERMARK_TOKENS = re.compile(
    r"\b(DRAFT|CONFIDENTIAL|DO NOT DISTRIBUTE|FOR INTERNAL USE)\b"
)
_EFFECTIVE_DATE_RE = re.compile(
    r"\b(effective\s+(date|as\s+of|on)|as\s+of\s+\d{4}|"
    r"last\s+(updated|revised|amended)|version\s+\d|©\s*\d{4})\b",
    re.IGNORECASE,
)
_SECTION_MARKER_RE = re.compile(
    r"(§\s*\d|"  # § 27-303
    r"\bsection\s+\d|"
    r"\b\d+(\.\d+)+\b|"  # 31.15.07
    r"^\s*\([a-z0-9]+\)\s+\w|"  # (a) The...
    r"^\s*\d+\.\s+\w)",  # 1. The...
    re.IGNORECASE | re.MULTILINE,
)
_REPLACEMENT_CHARS_RE = re.compile(r"�|\\ufffd")


@dataclass
class AssessmentFlag:
    code: str
    level: str  # "info" | "warn"
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "level": self.level, "detail": self.detail}


@dataclass
class Assessment:
    appears_complete: bool
    flags: list[AssessmentFlag] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "appears_complete": self.appears_complete,
            "flags": [f.as_dict() for f in self.flags],
            "stats": self.stats,
        }


def assess(text: str, *, kind: str = "other") -> Assessment:
    """Run heuristics over plaintext and return an Assessment."""
    flags: list[AssessmentFlag] = []
    stats: dict[str, Any] = {
        "char_count": len(text),
        "line_count": text.count("\n") + 1 if text else 0,
    }
    stripped = text.strip()
    if not stripped:
        flags.append(
            AssessmentFlag(
                code="empty",
                level="warn",
                detail="extracted text is empty; the source format may not be supported.",
            )
        )
        return Assessment(appears_complete=False, flags=flags, stats=stats)

    floor = KIND_MIN_CHARS.get(kind, 0)
    if floor and len(stripped) < floor:
        flags.append(
            AssessmentFlag(
                code="short-for-kind",
                level="warn",
                detail=(
                    f"plaintext is {len(stripped)} chars, below the typical "
                    f"floor of {floor} for kind={kind!r}. May be an excerpt."
                ),
            )
        )

    last = stripped[-200:]
    if last and not last.rstrip().endswith((".", "!", "?", '"', "'", ")", "]")):
        flags.append(
            AssessmentFlag(
                code="truncation-suspected",
                level="warn",
                detail="document ends without sentence-final punctuation; possibly truncated.",
            )
        )

    for marker in _TRUNCATION_MARKERS:
        if marker in text:
            flags.append(
                AssessmentFlag(
                    code="has-truncation-marker",
                    level="warn",
                    detail=f"contains literal {marker!r}; check the surrounding text for omissions.",
                )
            )
            break

    if _EXCERPT_HEADERS.search(stripped[:500]):
        flags.append(
            AssessmentFlag(
                code="looks-like-excerpt",
                level="warn",
                detail=(
                    "the first 500 chars contain a word like 'excerpt', "
                    "'partial', 'sample', or 'preview'."
                ),
            )
        )

    if _WATERMARK_TOKENS.search(text):
        flags.append(
            AssessmentFlag(
                code="has-watermark",
                level="info",
                detail="contains text like 'DRAFT' or 'CONFIDENTIAL' — may indicate a non-final version.",
            )
        )

    if _REPLACEMENT_CHARS_RE.search(text):
        flags.append(
            AssessmentFlag(
                code="encoding-issues",
                level="warn",
                detail="contains Unicode replacement characters; the file may have a charset mismatch.",
            )
        )

    if not _EFFECTIVE_DATE_RE.search(text):
        flags.append(
            AssessmentFlag(
                code="no-effective-date",
                level="info",
                detail=(
                    "no obvious 'effective date', 'as of', 'last updated', or "
                    "version marker found. Confirm with the user which "
                    "version they have."
                ),
            )
        )

    if kind in {"statute", "regulation"} and not _SECTION_MARKER_RE.search(text):
        flags.append(
            AssessmentFlag(
                code="no-section-numbers",
                level="warn",
                detail=(
                    f"kind={kind!r} but no section / paragraph markers found "
                    "(§, 'Section N', N.M.M, (a), (b)...). May be a "
                    "summary or excerpt rather than the codified text."
                ),
            )
        )

    appears_complete = not any(f.level == "warn" for f in flags)
    return Assessment(appears_complete=appears_complete, flags=flags, stats=stats)


# ---------------------------------------------------------------------------
# CLI for standalone use (uv run python -m scripts.references.assess)
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser(
        description="Heuristic completeness check for a reference doc plaintext.",
    )
    ap.add_argument("--file", required=True, type=Path, help="Plaintext file to assess.")
    ap.add_argument(
        "--kind",
        default="other",
        choices=list(KIND_MIN_CHARS.keys()),
        help="Document kind (affects heuristic thresholds).",
    )
    ap.add_argument(
        "--format",
        default="text",
        choices=["text", "json"],
        help="Output format.",
    )
    args = ap.parse_args(argv)

    text = args.file.read_text(encoding="utf-8", errors="replace")
    result = assess(text, kind=args.kind)

    if args.format == "json":
        print(json.dumps(result.as_dict(), indent=2))
        return 0

    print(f"file:  {args.file}")
    print(f"kind:  {args.kind}")
    print(f"chars: {result.stats['char_count']}")
    print(f"verdict: {'looks complete' if result.appears_complete else 'has warnings'}")
    if not result.flags:
        print("(no flags)")
    else:
        print("flags:")
        for f in result.flags:
            print(f"  [{f.level}] {f.code}: {f.detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
