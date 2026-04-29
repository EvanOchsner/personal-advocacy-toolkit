---
name: going-public
description: Publication-safety walkthrough — runs pii_scrub, docx_metadata_scrub, exif_scrub, and history_sanitizer post-checks before any derivative of the private workspace is posted, emailed, filed outside the regulator, or pushed to a public repo. Triggers before any "public" action.
---

# going-public

A packet going to a regulator is one thing. A write-up going on a
website, a thread, a public repo, or an OpEd is another. This skill
runs the four independent scrubbers and forces a post-check pass on
each before anything leaves the private workspace.

The four scrubbers are independent. PII scrub catches textual
identifiers; DOCX scrub catches Word metadata; EXIF scrub catches
image metadata; history sanitizer catches anything that leaked
into git history. You need all four.

## When this skill fires

- User says "publish this," "post this," "push this to the public
  repo," "share this on X/BlueSky/Substack."
- Before any file is attached to a non-adversary recipient (a
  journalist, a public advocate, an open mailing list).
- Before `git push` to a public remote if the scratch repo was
  ever used against real names.

## Procedure

Run each step, review its output, only proceed past a step when
the post-check passes.

### 1. PII scrub (text)

Delegate to the `pii-scrubber` skill. Dry-run → review → apply.
Confirm `scrub_report.json` is clean.

### 2. DOCX metadata scrub

For every `.docx` in the publication set:

```
uv run python -m scripts.publish.docx_metadata_scrub \
    --in drafts/complaint.docx \
    --out publish/complaint.docx
```

The script fails closed: if the post-check finds residual
`dc:creator`, `cp:lastModifiedBy`, `Company`, or similar, it
deletes the output file and raises. A silent success is what you
want.

### 3. EXIF scrub (images)

For every image in the publication set:

```
uv run python -m scripts.publish.exif_scrub --root publish/images/ --apply
```

Mandatory post-check: the script re-opens each output and verifies
no EXIF, GPS, or MakerNote survives. Non-zero exit means do not
publish.

### 4. Git history sanitizer (repo)

Only relevant if the workspace has ever been committed against
real identifiers and is about to become a public repo. This is
destructive — it rewrites history.

```
uv run python -m scripts.publish.history_sanitizer \
    --scratch-dir /abs/path/to/fresh-clone \
    --substitutions substitutions.yaml
```

Rails enforced by the script:
- `--scratch-dir` must be a fresh clone, not the caller's cwd.
- After rewrite, every blob in the rewritten repo is scanned for
  any banned term. A survivor exits non-zero — do NOT push.

Follow the bash rules: run this in its own Bash call, never
chained with other steps.

### 5. Second-pair-of-eyes read

Scripts catch mechanical leaks. They do not catch:

- Paraphrase leaks ("my elderly neighbor's insurer" when the
  reader knows your neighbor).
- Contextual identifiers (specific dates, dollar amounts, unique
  facts that triangulate the claimant).
- The thing you didn't think to add to `substitutions.yaml`.

Read the publication set end-to-end with the user before the
final push. A clean scrub report is necessary, not sufficient.

## Definition of done

All four scrubbers ran with passing post-checks, the second-pair-of-
eyes read happened end-to-end, and the user has explicitly approved
publication. If any post-check failed, the publication set stays in
the private workspace; the user must address the leak (extend
`substitutions.yaml`, redo the scrub, etc.) and rerun before
publishing.

This skill is the **last** workflow phase. When it completes, hand
back to `pat-workflow` only if more cases follow; otherwise the
session is done.

## Synthetic example

For a Maryland-Mustang public write-up the sequence is:

1. PII scrub of `drafts/` → write to `publish/`.
2. DOCX scrub of `publish/mia-complaint.docx`.
3. EXIF scrub of `publish/images/` (even though the current
   synthetic photos are `.md` placeholders, real ones would be
   JPEG/HEIC with location metadata).
4. History sanitizer over the clone. Confirm "Chesapeake
   Indemnity Mutual" and "Sally Ridesdale" survive (synthetic) while
   any real name that ever touched a commit message is gone.
5. Read the resulting bundle out loud. Publish.

## Do not

- Do not skip any of the four scrubbers because "this file type
  doesn't have that problem." A .docx has EXIF-adjacent risks
  (embedded images); an image post has DOCX-adjacent risks (the
  alt text you pasted in).
- Do not run the history sanitizer against the cwd. The script
  refuses; don't look for a way around it.
- Do not treat a clean scrub as a green light. Triangulation is a
  human-judgment problem.
