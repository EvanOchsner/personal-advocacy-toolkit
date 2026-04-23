# Tutorial 05: Going public safely

> **Reference material, not legal advice.** Going public with a
> dispute exposes you to defamation counter-claims, unintentional
> doxing, and anti-SLAPP considerations. This tutorial covers the
> *mechanics* of sanitizing derivatives — not whether you should
> publish, how to frame it, or what a reader might do with it.
> Consult counsel before publishing anything identifying a named
> counterparty.

By the end of this tutorial, you'll know how to sanitize your case
tree into a derivative that is safe to publish, with mandatory post-
checks that catch the common failure modes (PDF text-layer leaks,
docx metadata, EXIF GPS, git history leaks).

Running example: the
[`Mustang-in-Maryland`](../../examples/mustang-in-maryland/) synthetic
case. It's already synthetic, so no actual scrubbing is needed — but
we'll run the tools in dry-run mode to demonstrate detection.

```sh
cd examples/mustang-in-maryland
```

## The two options

**Option 1 — template + narrative (safer).** Publish a generalized
template of what you did, with a narrative describing the situation
abstractly, and link to the toolkit for readers who want to follow
the same pattern. No real file tree leaves your private repo.

**Option 2 — sanitized derivative (riskier).** Publish a cleaned
version of parts of the actual file tree. Requires every tool in this
tutorial.

This tutorial covers Option 2 mechanics. For most situations, Option
1 is the right call.

## The non-negotiable rail

`pii_scrub.py` **refuses to run against any path with an `evidence/`
segment.** The evidence tree is append-only by contract (see
[`evidence-integrity.md`](../concepts/evidence-integrity.md));
scrubbing it destroys the forensic record.

You must copy derivatives into a **separate tree** (`drafts/`,
`publish/`, `public/`) and scrub there.

## 1. Build a substitutions file

For the Mustang case (already synthetic, so this is illustrative):

```yaml
# publish/substitutions.yaml
substitutions:
  "Delia Vance":                     "Jane Doe"
  "delia.vance@example.invalid":     "jane@example.invalid"
  "Chesapeake Indemnity Mutual":     "Example Indemnity Mutual"
  "414 Aigburth Vale":               "[address redacted]"
  "Towson, MD 21204":                "[city redacted], MD [zip redacted]"
  "+1-410-555-0142":                 "555-000-0000"
  "CIM-CLS-0000-0000":               "POL-REDACTED-00001"
  "CIM-2025-03-5517":                "CLAIM-REDACTED-00001"

policy_number_patterns:
  - "CIM-[A-Z]+-\\d{4}"
  - "CIM-\\d{4}-\\d{2}-\\d{4}"
  - "MAVA-\\d{4}-\\d{2}-\\d{4}"

extra_banned:
  - "414 Aigburth Vale"
  - "Harlan Whitlock"
  - "Joyce Pemberton"
```

Curation rules (from
[`pii-and-publication.md`](../concepts/pii-and-publication.md)):

- **Substitution keys are literal, case-sensitive.** List variants
  explicitly.
- **Longest-first matching.** If you list both "Jane" and "Jane Doe,"
  "Jane Doe" wins.
- **`extra_banned`** is the post-check list. Things that must never
  appear in any output, even partially.

## 2. Copy drafts into a publish tree

```sh
mkdir -p publish/
cp -R drafts/ publish/
```

You're about to scrub `publish/`. Do not scrub `drafts/` — keep your
unscrubbed working copy intact.

## 3. Dry-run the PII scrub

```sh
uv run python -m scripts.publish.pii_scrub \
  --root publish/ \
  --substitutions publish/substitutions.yaml \
  --report publish/.scrub-dryrun-report.json
```

Default mode is dry-run — files are not modified. The report (JSON)
lists every change the scrubber *would* make: path, line, detector,
replacement, and a SHA-256 of the original matched span. The
plaintext of what was replaced is **never** written to the report.

Review the report. Common surprises:

- Email addresses in signature blocks you forgot about.
- Phone numbers embedded in old quoted-reply threads.
- A VIN mentioned in passing in an attachment.
- Addresses in letterhead footers.

## 4. Apply the scrub

```sh
uv run python -m scripts.publish.pii_scrub \
  --root publish/ \
  --substitutions publish/substitutions.yaml \
  --report publish/.scrub-report.json \
  --apply
```

Now files are modified. Re-read the report. If any banned term from
`extra_banned` still appears in any output after `--apply`, the tool
exits non-zero with a "POST-CHECK FAIL" warning. Treat this as a
hard failure — do not publish until it's resolved.

## 5. PDF redaction (visual + text layer)

If your publish tree includes PDFs with visible PII that you want to
redact:

```sh
uv run python -m scripts.publish.pdf_redact \
  --in publish/some-letter.pdf \
  --out publish/some-letter-redacted.pdf \
  --spec publish/redactions.json \
  --substitutions publish/substitutions.yaml
```

The redaction spec is JSON listing bounding boxes per page. The tool:

1. Removes text objects whose placement is inside each bbox.
2. Draws a filled rectangle on top.
3. Strips XMP + /Info metadata.
4. **Post-check:** re-extracts all text from the output and verifies
   no banned term survives. If any does, the output is **DELETED**
   and the tool raises.

The post-check is the point. A scrubber you can't audit is worse
than no scrubber.

## 6. docx metadata scrub

For any .docx in the publish tree:

```sh
uv run python -m scripts.publish.docx_metadata_scrub \
  --in publish/draft.docx \
  --out publish/draft-clean.docx
```

Strips `docProps/core.xml` (dc:creator, cp:lastModifiedBy, etc.) and
`docProps/app.xml` (Company, Manager, etc.). Does not touch
`word/document.xml` — content stays intact. Post-check re-opens the
output and asserts each known-sensitive field is empty.

## 7. EXIF scrub for images

```sh
uv run python -m scripts.publish.exif_scrub --root publish/ --apply
```

Re-saves each image through Pillow without EXIF. Drops GPS, camera
serial, maker-notes, and TIFF-style tags. Post-check re-opens each
file and reports any that still carry EXIF.

Without `--apply` the tool runs in dry-run mode (report only, no file
changes).

## 8. (Only if needed) git history sanitizer

If you committed real PII to the repo earlier and need to rewrite
history before pushing publicly:

```sh
# 1. Clone to a scratch directory — never operate on your working copy
git clone /path/to/case /tmp/case-scratch

# 2. Run the sanitizer against the scratch clone
uv run python -m scripts.publish.history_sanitizer \
  --scratch-dir /tmp/case-scratch \
  --substitutions publish/substitutions.yaml
```

Safety rails built in:

- Refuses to run unless `--scratch-dir` is a git repo that is NOT
  your cwd.
- Mandatory post-check walks every blob in the rewritten history
  (`git rev-list --all` → `git ls-tree -r` → `git cat-file blob`)
  and greps for every banned term. Non-zero exit means **do not
  push** this scratch repo.

`git filter-repo` (the underlying binary) isn't a Python package;
install separately: `brew install git-filter-repo`.

## 9. Human read-through

Every tool above has a post-check. **Do the human read-through
anyway.** Skim every file in `publish/` once before posting. Pay
special attention to:

- Quoted-reply blocks in old emails.
- Letterhead footers.
- Attachment filenames (not just contents).
- Hyperlink URLs that may contain identifiers.
- Image captions / alt text.

## 10. Rebuild the packet from the scrubbed tree (if applicable)

If you're publishing a sanitized complaint packet:

```sh
# Point a separate packet-manifest at the scrubbed sources
uv run python -m scripts.packet.build publish/packet-manifest.yaml -v
```

The builder regenerates the PDF from the scrubbed sources. It will
pick up your `[ADDRESS REDACTED]` placeholders and your synthetic
names throughout.

## What this does not do

- It does not prove the derivative is safe to publish. Post-checks
  verify specific things; human judgment is still required.
- It does not redact pixels in screenshots (e.g., a redacted area in
  a UI screenshot). Use a pixel-level image editor for those and
  verify the output has no layers preserving the original.
- It does not prevent an adversary who has a copy of your original
  `drafts/` tree from publishing the unscrubbed version. If that
  tree has been shared with anyone, assume it's public.

## See also

- [`docs/concepts/pii-and-publication.md`](../concepts/pii-and-publication.md)
  — full conceptual story on the four layers of leakage.
- [`skills/going-public/SKILL.md`](../../skills/going-public/SKILL.md)
  — interactive pre-publication checklist.
- [`skills/pii-scrubber/SKILL.md`](../../skills/pii-scrubber/SKILL.md)
  — review-and-confirm loop for the scrub output.
