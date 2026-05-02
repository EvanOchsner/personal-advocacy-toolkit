---
name: document-extraction
description: Convert a PDF / HTML / email / image into searchable plaintext via a layered cascade with garble detection, per-page fallback, and a reproducibility script per source. Triggers when (1) a file lands in evidence/<type>/raw/ and structured/ is empty, (2) the user says "extract text from <file>", "this PDF won't OCR cleanly", "the HTML extraction is missing the table", or (3) `evidence-intake` delegates here for the extract step.
---

# document-extraction

Layered document → searchable plaintext extraction. Replaces the old
per-format ingesters (`scripts/ingest/{pdf_to_text,html_to_text,email_eml_to_json,email_json_to_txt}`)
with a cascade that escalates only when the cheap path produces
garbled text.

The cascade lives at `scripts/extraction/`; the CLI is
`uv run python -m scripts.extraction <file> --out-dir <evidence/<type>/> --case-root <case>`.

## When this skill fires

- A new PDF / HTML / `.eml` / image lands in `evidence/<type>/raw/`.
- User says: "extract text", "the OCR is broken", "this PDF doesn't
  search", "fix the HTML extraction", "this is a scanned policy".
- `evidence-intake` skill delegates to this skill for the extract step.

## Tier ladder

| Tier | PDF                    | HTML                       | Image     | Email |
|------|------------------------|----------------------------|-----------|-------|
| 0    | `pypdf` + `ocrmypdf`   | stdlib `html.parser`       | —         | stdlib `email` |
| 1    | Docling                | Trafilatura                | Tesseract | (single tier) |
| 2    | VLM provider (per page)| Playwright + Trafilatura   | —         | — |
| 3    | Tesseract backstop     | —                          | —         | — |

The cascade tries cheap → expensive, runs garble detection at each
tier, and only re-extracts the *garbled pages* (PDF) or the document
(HTML) at the next tier. Email is single-tier — stdlib is enough.

## Provider recommendation order — **load-bearing**

When tier 2 fires for a PDF (any page failed tier-0 and tier-1
garble checks), the cascade picks a VLM provider. Always recommend
in this order:

1. **`tesseract`** — local OCR, no GPU, no network. **Default.**
   Adequate for most documents. Pick this unless quality
   demonstrably blocks the case.
2. **`olmocr`** — local 7B VLM, GPU recommended. **When tesseract
   isn't enough AND privacy matters.** Stays on the user's machine.
   Best for bezier-glyph PDFs and complex layouts on sensitive
   evidence.
3. **`claude` / `openai` / `http`** — cloud VLM providers. **Last
   resort.** Simple and powerful, but page images leave the machine.
   Per-case opt-in required; the cascade prompts and records the
   answer in `<case>/extraction/vlm-consent.yaml`.

The recommendation order shows up identically in: `README.md`,
`CLAUDE.md`, install error messages, and the cascade's own user-
facing prompts. **Do not reorder these or invent a new ordering.**

## Privacy guardrail

Network providers (`requires_network=True`) are gated behind a
per-case consent check. The first time the cascade wants to run
`claude` / `openai` / `http`, it prompts:

```
[PRIVACY] Provider 'claude' sends raw page images to a third-party
service. Page images may contain SSNs, medical info, account
numbers, or other sensitive evidence. Once sent, recall is not
possible.
Recommended local alternatives: tesseract (default), olmocr.
Allow claude for this case? [y/N] >
```

The answer is recorded in `<case>/extraction/vlm-consent.yaml`. The
`going-public` skill reads this file before publication so a
regulator-bundle author can decide whether to re-extract with a
local provider for the public copy.

## Procedure

1. **Identify the file type** by extension. The cascade auto-detects.

2. **Run the cascade**:

   ```sh
   uv run python -m scripts.extraction \
       evidence/<type>/raw/<source>.<ext> \
       --out-dir evidence/<type>/ \
       --case-root . \
       --manifest evidence/<type>/manifest.yaml
   ```

   Output:
   - `evidence/<type>/raw/<source_id>.<ext>` (byte-identical copy)
   - `evidence/<type>/structured/<source_id>.json` (recipe metadata)
   - `evidence/<type>/readable/<source_id>.txt` (plaintext)
   - `<case>/extraction/scripts/extract_<source_id>.py` (reproducibility script)

3. **Inspect the result.** The structured JSON's `extraction.tier`
   field tells you which tier won. If you see `tier: 0`, the cheap
   path was good. If `tier: 2` or `tier: 3`, something was hard about
   this document — note which pages were garbled (`extraction.page_results`).

4. **If the result is wrong**, write or edit
   `<case>/extraction/overrides/<source_id>.yaml`:

   ```yaml
   source_id: 7a3f1e9c
   file: evidence/policy/raw/acr-61-3.pdf
   overrides:
     skip_pages: [1, 14]
     strip_text_patterns:
       - "CONFIDENTIAL — DO NOT DISTRIBUTE"
       - "Page \\d+ of \\d+"
     force_tier: 2
     vlm_provider: olmocr   # only if tesseract is the default and you want to escalate
     notes: "Watermark on every page; tier 0 picks it up as body text."
   ```

   Then re-run the same command. The recipe records overrides exactly
   so future replays apply them automatically.

5. **Re-hash the evidence tree** after ingest:

   ```sh
   uv run python -m scripts.evidence_hash --root evidence/
   ```

6. **Verify reproducibility** (optional but recommended for any
   document that escalated past tier 0):

   ```sh
   uv run python <case>/extraction/scripts/extract_<source_id>.py
   ```

   Should print `OK` and exit 0. Non-zero exit means the recipe no
   longer reproduces the on-disk readable text.

## Installing optional tiers

Base install (`uv sync`) runs tier 0 only — same behavior as the old
`scripts.ingest` modules. Heavier tiers need extras:

```sh
uv sync --extra extraction          # Docling, Trafilatura, Playwright, Tesseract, pdf2image
playwright install chromium         # one-time, after the first sync

uv sync --extra extraction-vlm      # olmOCR (local 7B VLM, GPU recommended)
uv sync --extra extraction-cloud-openai   # OpenAI vision
# Claude vision reuses the existing [llm] extra:
uv sync --extra llm
```

System binaries (graceful fallback if missing — the cascade prints a
hint):
- `tesseract` (`brew install tesseract`)
- `chromium` (via `playwright install chromium`)
- `poppler` for `pdf2image` (`brew install poppler`)
- `ocrmypdf` (`brew install ocrmypdf`) — used by tier-0 for image-only PDFs

Provider availability check:

```sh
uv run python -m scripts.extraction --list-providers
```

## Definition of done

- The `raw/` / `structured/` / `readable/` triple exists for the
  ingested file.
- `<case>/extraction/scripts/extract_<source_id>.py` exists.
- The manifest has the new entry.
- The SHA-256 evidence manifest is refreshed.
- If the document trips garble at any tier, the user has either
  accepted the cascade's chosen escalation or written an
  `overrides/<source_id>.yaml` that produces the right result.

## Do not

- Do not silently fall back to a cloud VLM when local options work.
  Always honor the recommendation order: tesseract → olmocr → cloud.
- Do not edit `<case>/extraction/scripts/extract_<source_id>.py` by
  hand. Regenerate it by re-running the cascade.
- Do not edit `structured/` / `readable/` outputs by hand. Use
  `overrides/<source_id>.yaml` instead so the change is reproducible.
- Do not skip consent recording when using a network provider. The
  `going-public` skill depends on `vlm-consent.yaml` to flag
  externally-processed pages before publication.
