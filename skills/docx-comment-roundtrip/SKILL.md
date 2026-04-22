---
name: docx-comment-roundtrip
description: Strip Word comments from a .docx without altering document content, verify the round-trip, and restore comments to a working copy when needed. Triggers when the user says "strip comments from this .docx" or prepares a Word document for a counterparty.
---

# docx-comment-roundtrip

Round-trip comments on a Word document. Two directions:

- **Extract** — pull every `<w:comment>` out of a `.docx` into a
  human-readable YAML sidecar and emit a cleaned `.docx` with the
  comment parts (and their anchor elements in `document.xml`) removed.
  The cleaned `.docx` is what you send to the counterparty.
- **Inject** — take the cleaned `.docx` + the sidecar and rebuild the
  original `.docx`, with comment IDs, authors, timestamps, and body
  text preserved. The anchor positions in `document.xml` are restored
  at the same locations they were pulled from.

Why this exists: Word's "Delete All Comments in Document" command
leaves residuals behind — `word/commentsExtended.xml`,
`word/commentsIds.xml`, `word/commentsExtensible.xml`, and the
`[Content_Types].xml` override / relationship entries that reference
them. A reviewer opening the `.docx` with a zip tool can still see that
comments existed, who authored them, and sometimes their content via
`commentsExtended.xml`. For an advocacy context — a demand letter sent
to opposing counsel, a complaint draft shared with a regulator — those
residuals are a leak. Strip the whole comment apparatus, not just the
visible comments.

## Script surface

`scripts/publish/docx_comment_roundtrip.py`

```
# Extract: draft -> sidecar YAML + stripped .docx for the counterparty.
python -m scripts.publish.docx_comment_roundtrip \
    --extract \
    --in drafts/demand-letter.docx \
    --out out/demand-letter-clean.docx \
    --sidecar out/demand-letter-comments.yaml

# Inject: cleaned .docx + sidecar -> restored working copy.
python -m scripts.publish.docx_comment_roundtrip \
    --inject \
    --in out/demand-letter-clean.docx \
    --sidecar out/demand-letter-comments.yaml \
    --out drafts/demand-letter-restored.docx
```

Exit 0 on success, 2 on structural errors (no comments part found on
`--extract`, empty sidecar on `--inject`, etc.).

## When to invoke

- The user is preparing a `.docx` for a counterparty (opposing counsel,
  insurer, regulator, journalist) and internal review comments must
  not leak.
- The user wants to keep a reviewable / commented working copy but also
  produce a clean release copy.
- Part of a `going-public` sequence, before
  `scripts/publish/docx_metadata_scrub.py` removes author / company
  metadata.

Do **not** invoke for:

- PDF redaction — that is `scripts/publish/pdf_redact.py`.
- Image metadata scrub — `scripts/publish/exif_scrub.py`.
- Metadata (author, company, revision) scrub of a `.docx` —
  `scripts/publish/docx_metadata_scrub.py`. Comment round-trip and
  metadata scrub solve different problems; run both when both apply.
  Metadata scrub touches `docProps/`, comment round-trip touches
  `word/comments*.xml` and `document.xml` anchors. They don't overlap.

## Parts touched

```
word/comments.xml            REMOVED on extract, REBUILT on inject
word/commentsExtended.xml    REMOVED on extract (not rebuilt — Word
word/commentsIds.xml           regenerates these when the file is
word/commentsExtensible.xml    opened with comments again)
word/_rels/document.xml.rels RELATIONSHIP entry removed/restored
[Content_Types].xml          OVERRIDE entry removed/restored
word/document.xml            ANCHOR elements removed/restored:
                               <w:commentRangeStart>
                               <w:commentRangeEnd>
                               <w:commentReference>
```

Everything else in the zip — styles, numbering, headers, footers,
embedded media, document body text, tracked changes, footnotes — is
copied byte-for-byte in original member order.

## Sidecar format

YAML. One record per comment plus the list of anchors:

```yaml
schema_version: "1.0"
source_docx: demand-letter.docx
comments:
  - id: "0"
    author: "Reviewer Name"
    initials: "RN"
    date: "2026-04-22T10:15:00Z"
    body_xml: "<w:p xmlns:w=\"...\"><w:r><w:t>pushback here</w:t></w:r></w:p>"
anchors:
  - kind: commentRangeStart
    comment_id: "0"
    path: [0, 3, 1]
    order: 0
  # ... matching commentRangeEnd and commentReference
```

`body_xml` is the exact XML children of `<w:comment>`. Preserving it
means a round-trip restores formatting inside the comment body (bold,
italic, multi-paragraph comments, etc.) byte-for-byte.

`path` is a sequence of child indices from `word/document.xml` root to
the anchor's position. `order` records document order so injection is
deterministic.

## Round-trip testing

`tests/test_docx_comment_roundtrip.py` synthesizes a minimal `.docx`
with one or two comments and verifies:

1. Extract produces a stripped `.docx` with no `word/comments.xml`, no
   comment-related rels entry, no content-types override, and no
   anchor elements in `document.xml`.
2. Inject restores comments with the same IDs and bodies, and the
   anchor elements reappear in `document.xml`.
3. Body text runs in `document.xml` (outside the anchors) are
   unchanged across extract and inject.

## Do not

- Do not hand-edit the zip. Always go through the script. Manual
  editing frequently leaves `[Content_Types].xml` or the rels file
  referencing a part that no longer exists; Word opens those files
  with a repair dialog that leaks the fact of the edit.
- Do not run the extract on an encrypted or password-protected
  `.docx`. Decrypt first (Word, LibreOffice) to a plain `.docx`, then
  run the extract on that.
- Do not conflate this with the metadata-scrub script. The two
  solve different problems; ship both in a `going-public` sequence
  when both apply. A clean-for-counterparty document needs both:
  metadata scrub to remove `dc:creator` etc., and this skill to remove
  the comment apparatus.
- Do not rely on Word's "Delete All Comments in Document" alone.
  Inspect with `unzip -l file.docx | grep comment` afterward; if any
  `word/comments*.xml` entry still exists, the built-in command did
  not fully clean.

## Related

- `scripts/publish/docx_metadata_scrub.py` — authorial metadata scrub.
- `scripts/publish/exif_scrub.py` — image EXIF scrub.
- `scripts/publish/pdf_redact.py` — PDF redaction.
- `skills/going-public/` — orchestrates the full publication-safety
  sequence.
