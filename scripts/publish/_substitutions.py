"""Shared loader for substitutions.yaml.

Schema (shared across pii_scrub.py and history_sanitizer.py so users only
maintain one list):

    # substitutions.yaml
    substitutions:
      # Exact-string → replacement. Longest-first matching at scrub time.
      "John Doe": "John Synthetic"
      "jdoe@example.com": "synthetic@example.invalid"
      "555-123-4567": "555-000-0000"

    policy_number_patterns:
      # Optional list of regexes to treat as policy numbers.
      - "CIM-VEH-\\d{4}"
      - "POL-[A-Z0-9]{6,}"

    # Additional free-form banned terms the post-check must not find anywhere
    # in the output. Typically the LHS of `substitutions` is auto-added; use
    # `extra_banned` only for terms that never need substitution but also
    # must never appear (e.g. a home address you never want published in
    # any form, even a partial one).
    extra_banned:
      - "742 Evergreen Terrace"

The banned-term list (for post-checks) is built as:
    sorted(set(substitutions.keys()) | set(extra_banned), key=len, reverse=True)

Matching policy:
- Substitution keys are matched as plain substrings (not regex), case-sensitive.
  If you want case-insensitive, list the variants explicitly. This is a
  deliberate safety choice: a loose regex that over-matches is worse than a
  strict literal that under-matches, because the detector-pass adds coverage
  for generic categories (emails, phones, VINs) on top of the literal list.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Substitutions:
    mapping: dict[str, str] = field(default_factory=dict)
    policy_number_patterns: list[str] = field(default_factory=list)
    extra_banned: list[str] = field(default_factory=list)

    @property
    def banned_terms(self) -> list[str]:
        """Terms a post-check must NOT find in the output. Longest first."""
        terms = set(self.mapping.keys()) | set(self.extra_banned)
        # Empty strings would match everything; guard explicitly.
        return sorted((t for t in terms if t), key=len, reverse=True)

    def replacement_for(self, term: str | None = None) -> str | None:
        return self.mapping.get(term) if term else None


def load_substitutions(path: Path) -> Substitutions:
    import yaml  # local import so the module is importable without PyYAML

    with open(path, encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh) or {}

    subs = data.get("substitutions") or {}
    if not isinstance(subs, dict):
        raise ValueError(f"{path}: `substitutions` must be a mapping")
    # Normalize to str/str.
    mapping = {str(k): str(v) for k, v in subs.items()}

    pats = data.get("policy_number_patterns") or []
    if not isinstance(pats, list):
        raise ValueError(f"{path}: `policy_number_patterns` must be a list")
    patterns = [str(p) for p in pats]

    extra = data.get("extra_banned") or []
    if not isinstance(extra, list):
        raise ValueError(f"{path}: `extra_banned` must be a list")
    extra_banned = [str(e) for e in extra]

    return Substitutions(
        mapping=mapping,
        policy_number_patterns=patterns,
        extra_banned=extra_banned,
    )
