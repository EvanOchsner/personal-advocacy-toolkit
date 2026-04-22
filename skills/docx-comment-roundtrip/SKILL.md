---
name: docx-comment-roundtrip
description: Strip Word comments from a .docx without altering document content, verify the round-trip, and restore comments to a working copy when needed. Triggers when the user says "strip comments from this .docx" or prepares a Word document for a counterparty.
---

# docx-comment-roundtrip

**PORT PENDING.** This skill is a stub. The authored source lives
in a private project (`lucy-repair-fight/.claude/skills/docx-comment-roundtrip/`)
that this Phase 4A session cannot read. The intent is described
below; a follow-up task should replace this stub with the full
ported SKILL.md.

## Intent

- A `.docx` is a zip of XML parts. Comments live in
  `word/comments.xml`, with anchor references in `word/document.xml`
  and relationship entries in `word/_rels/document.xml.rels`.
- Word documents shared with counterparties must not leak internal
  review comments. Simple "accept all / delete comments" in Word
  leaves residuals (comment IDs, people list in
  `word/commentsExtended.xml`, `commentsIds.xml`).
- The skill's job: strip all comment parts, their rels entries, and
  the anchor ranges in `document.xml`, while preserving the rest of
  the document byte-for-byte where feasible.
- Optional round-trip: keep the stripped comments in a sidecar so a
  future workflow can restore them to the author's working copy.

## Adjacent tooling already in tree

- `scripts/publish/docx_metadata_scrub.py` — scrubs `docProps/`
  (creator, company, revision) but does NOT touch comments.
  Comment-strip is a separate concern and belongs in this skill's
  eventual script.

## Minimal interim guidance

Until the full port lands, do NOT hand-edit the zip. Tell the user
the port is pending and recommend they use a Word "Delete All
Comments in Document" pass plus a manual check of
`word/commentsExtended.xml` via `unzip -l` until the scripted
version is available.

## Do not

- Do not conflate this with metadata scrub. The two solve different
  problems; ship both in the `going-public` sequence when both
  apply.
