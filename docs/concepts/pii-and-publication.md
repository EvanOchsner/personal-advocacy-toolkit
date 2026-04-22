# PII and publication

At some point you may want to publish a sanitized version of your case
— a blog post, a Twitter thread with a screenshot, a journalist's tip,
an open-source example for someone else facing the same situation.
This document is about how not to leak yourself in the process.

The failure mode this section exists to prevent: a "redacted" PDF
whose text layer still contains the redacted content, visible to
anyone who selects and copies the text.

## The layers you have to think about

Every publishable derivative has at least four layers where PII can
leak. A scrubber that only addresses one is worse than no scrubber at
all, because it builds false confidence.

### 1. Visible text

The obvious layer — the words a reader sees. Names, emails, phone
numbers, VINs, policy/claim/account numbers, addresses.

Handled by: `scripts/publish/pii_scrub.py`, driven by a
`substitutions.yaml` you curate.

### 2. Hidden text under visual redactions

When you draw a black box over text in Preview / Acrobat, the text
usually remains in the PDF's text layer. A reader copies-and-pastes
past the box and sees the original. This has been the source of many
publicized leaks.

Handled by: `scripts/publish/pdf_redact.py`, which:

1. Removes text objects whose placement falls inside the redaction
   bounding box.
2. Draws a filled rectangle on top.
3. Writes replacement text if you supply it.
4. **Mandatory post-check:** re-extracts all text from the output PDF
   and verifies none of your `banned_terms` appears. If any term
   survives, the output is DELETED and the tool raises.

The post-check is the primary test target. A scrubber you cannot audit
is worse than no scrubber at all.

### 3. File metadata

- **.docx** files carry `docProps/core.xml` (author, last-modified-by,
  revision count) and `docProps/app.xml` (company, template path,
  application). Handled by `scripts/publish/docx_metadata_scrub.py`.
- **PDFs** carry XMP metadata and a `/Info` dictionary (author,
  title, creation tool). Handled as part of `pdf_redact.py`.
- **Images** carry EXIF (GPS coordinates, camera serial, timestamps,
  maker-notes). Handled by `scripts/publish/exif_scrub.py`.

Every one of these scrubbers has a mandatory post-check that re-opens
the output and fails if any known-sensitive field is still populated.

### 4. Git history

If you have ever committed a file containing your real name, email,
or address to the repo — even if you later deleted the file — that
content is still in the git history and `git log -p | grep` will find
it. Push the repo publicly and a reader who runs `git clone` and
`git log -p` sees everything.

Handled by: `scripts/publish/history_sanitizer.py`, a wrapper around
`git filter-repo`. Safety rails:

- Refuses to run unless `--scratch-dir` points to a fresh clone, not
  your working copy. History-rewriting is destructive; you rewrite a
  throwaway copy.
- Mandatory post-check: walks every blob in the rewritten repo
  (`git rev-list --all` → `git ls-tree -r` → `git cat-file blob`) and
  greps for every banned term. Non-zero exit means do not push.

`git filter-repo` itself is a separate binary: install via
`brew install git-filter-repo` (macOS) or your distro's package
manager (Linux).

## The substitutions file

All scrubbers share one `substitutions.yaml`:

```yaml
substitutions:
  "Jane Doe":            "Jane Synthetic"
  "jdoe@example.com":    "synthetic@example.invalid"
  "555-123-4567":        "555-000-0000"
  "POL-ABC-12345":       "POL-REDACTED-00001"

policy_number_patterns:
  - "CIM-[A-Z]+-\\d{4}"
  - "POL-[A-Z0-9]{6,}"

extra_banned:
  - "742 Evergreen Terrace"
```

Rules:

- **Substitution keys are literal case-sensitive substrings.** If you
  want "jane doe" (lowercase) scrubbed too, list it separately. A
  loose regex that over-matches is worse than a strict literal that
  under-matches, because the category detectors (below) provide the
  safety net.
- **Longest-first matching at scrub time.** If you list both "Jane"
  and "Jane Doe," "Jane Doe" wins when both match at the same
  position.
- **`policy_number_patterns`** is for regex-driven detection of
  format-stable identifiers the substitution list can't enumerate
  (claim numbers with variable suffixes, etc.).
- **`extra_banned`** is the post-check list. Terms here never need
  substitution but must never appear in any output. Typically a home
  address you never want published in any form.

## Category detectors (safety net)

On top of the substitutions list, `pii_scrub.py` runs category
detectors that catch things you forgot to enumerate:

- Email addresses (RFC-5322-light regex).
- US phone numbers in common formats.
- VINs (ISO 3779 17-char, excludes I/O/Q).
- US mailing addresses (narrow heuristic; backed by post-check).

Each detected match is replaced with a category placeholder:
`redacted@example.invalid`, `555-000-0000`, `VIN-REDACTED-0000`,
`[ADDRESS REDACTED]`, etc.

## The hard safety rail

`pii_scrub.py` **refuses to run against any path containing an
`evidence/` directory segment.** The evidence tree is append-only by
contract (see
[`evidence-integrity.md`](evidence-integrity.md)); scrubbing it
destroys the forensic record.

Publication derivatives must be written to a separate tree (`drafts/`,
`publish/`, etc.) and scrubbed there. Never scrub `evidence/`.

## Recommended workflow

```
1. Write your narrative in `drafts/` using real data.
2. Build a `substitutions.yaml` curated for your case.
3. Copy `drafts/` to `publish/` (or similar).
4. Run `pii_scrub.py --root publish/ --substitutions subs.yaml`
   (dry-run by default). Review the report.
5. Run again with `--apply`. Review the actual file changes.
6. If the packet includes a PDF with visible PII: rebuild the PDF
   from the scrubbed drafts, OR run `pdf_redact.py` with explicit
   bounding boxes and a banned-terms list.
7. For images: run `exif_scrub.py --root publish/ --apply`.
8. For .docx: run `docx_metadata_scrub.py` on each file.
9. Before pushing a new repo: clone to a scratch dir and run
   `history_sanitizer.py` against that clone.
10. Manually grep the final output for each term in `extra_banned`.
    The tools do this, but one human read-through before pushing is
    cheap insurance.
```

## Sidecar reports

Every scrubber writes a sidecar JSON report listing what it changed:
path, line, detector, replacement, and a SHA-256 of the original
matched span. The plaintext of what was replaced is **never** written
to the report — the hash is. You can safely attach the report to a
review ticket without leaking the thing you just scrubbed.

## What this does not do

- It does not prove your derivative is safe to publish. The post-checks
  verify specific things. They do not replace human review.
- It does not handle screenshots of third-party UIs (e.g., an
  insurer's portal) where PII is rendered as pixels, not text. Those
  need a manual redaction tool and a human eye.
- It does not defeat an adversary with a copy of your original
  `drafts/` tree. If you committed the unscrubbed version earlier,
  `history_sanitizer.py` is the tool; see that section.

## CI gates

Two CI jobs enforce the publication-safety story continuously:

- **`publication-safety-postchecks`** (`.github/workflows/ci.yml`) runs
  the three scrubbers against `examples/` (and `templates/` for
  `.docx`) in post-check mode: `exif_scrub` (exit 1 on any surviving
  EXIF/GPS/XMP tag), `docx_metadata_scrub` per `.docx` (exit 1 if any
  sensitive `core.xml` or `app.xml` field survived), and `pii_scrub`
  with `ci/example-subs.yaml` (exit 1 if any banned-term survivor).
  All three run on every push and PR to `main`.
- **`publication-prep-grep`** runs `rg -F -f ci/banned-terms.txt` over
  the whole repo. Any match fails CI. `ci/banned-terms.txt` ships
  empty; the infra is in place for when a real-case identifier ever
  nearly leaks.

To add a banned term: append one line per term to `ci/banned-terms.txt`
(fixed-string match, case-sensitive, `#` for comments). Commit. CI will
fail on any file in the repo — tracked or untracked — that contains the
term, except `ci/banned-terms.txt` and `scripts/ci/local_postchecks.sh`
themselves, which are excluded so a term never matches its own
declaration.

To diagnose a failing post-check: run `bash scripts/ci/local_postchecks.sh`
locally. It mirrors the CI steps and prints the same reports
(`/tmp/postcheck/*` or `$REPO/.tmp/postcheck/*`) so the offending file
and field are visible without re-reading CI logs.

## See also

- [`evidence-integrity.md`](evidence-integrity.md) — the append-only
  contract `pii_scrub.py` enforces.
- [`skills/pii-scrubber/SKILL.md`](../../skills/pii-scrubber/SKILL.md) —
  invokable from a Claude Code session for review-and-confirm loops.
- [`skills/going-public/SKILL.md`](../../skills/going-public/SKILL.md) —
  the full pre-publication checklist wrapped around these tools.
- [`docs/tutorials/05-going-public-safely.md`](../tutorials/05-going-public-safely.md)
  — the tutorial that walks the synthetic case through this pipeline.
