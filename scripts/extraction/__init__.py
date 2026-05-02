"""Layered document → searchable plaintext extraction.

This package replaces the per-format ingesters that lived under
``scripts/ingest/`` with a single cascade that:

  1. tries cheap, stdlib-first extractors first (tier 0),
  2. checks the output for "garble" signals (CID glyphs, missing
     text, JS-stripped HTML, ...),
  3. falls back to progressively heavier tiers only on the pages or
     documents that need it,
  4. records the chosen path, settings, and any human overrides as a
     "recipe" — and emits a per-evidence Python script that can
     re-run the exact extraction and assert byte-identical output.

Provider recommendation order (see also ``README.md``, ``CLAUDE.md``,
and ``.claude/skills/document-extraction/SKILL.md``):

  1. ``tesseract`` — local OCR, no network, no GPU. **Default.**
  2. ``olmocr``    — local 7B VLM, no network, GPU recommended.
                     Pick this when tesseract isn't enough AND
                     privacy matters.
  3. ``claude`` / ``openai`` / ``http`` — cloud VLM providers.
                     Simple and powerful, but page images leave the
                     machine. Pick only when local options are
                     inadequate AND the user has consciously accepted
                     the privacy trade-off.

The cascade and providers degrade gracefully when optional
dependencies are missing: the base install behaves like the old
tier-0 path, no silent failures.
"""
from __future__ import annotations

from .result import ExtractionResult, PageResult

__all__ = ["ExtractionResult", "PageResult"]
