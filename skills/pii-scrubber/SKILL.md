---
name: pii-scrubber
description: Review-and-confirm loop around scripts/publish/pii_scrub.py — runs dry-run first, walks the user through the report, then applies only after explicit confirmation. Triggers before any derivative file (draft letter, complaint, public post) leaves the private workspace.
---

# pii-scrubber

`pii_scrub.py` is the mechanical scrubber; this skill is the
human-in-the-loop wrapper that keeps you from redacting too much or
too little.

## When this skill fires

- Before publishing, posting, or sharing any `drafts/` or `publish/`
  derivative.
- Whenever the user says "scrub this" or "redact this" on a file
  that lives outside `evidence/`.

## Hard rule

The scrubber refuses to run against any path inside `evidence/`. The
evidence tree is read-only; scrubbing it destroys the forensic
record. This skill inherits that rule — if the user points at an
evidence file, decline and explain the three-layer model: copy it
into `drafts/` first, scrub the copy, and keep the raw untouched.

## Procedure

1. **Prepare the substitutions file.** `substitutions.yaml` lives
   in the workspace root (or is pointed at with `--substitutions`).
   Review it with the user — does every key still map to the
   intended placeholder? Add new entries if the document introduces
   names or numbers the scrubber couldn't guess generically.

2. **Dry run first — always.**

   ```
   uv run python -m scripts.publish.pii_scrub \
       --root drafts/ \
       --substitutions substitutions.yaml \
       --report scrub_report.json
   ```

   This writes `scrub_report.json` and touches no files.

3. **Walk the report with the user.** `scrub_report.json` is a list
   of `{path, line, detector, original_sha256, replacement}`
   records. The original text is hashed, not stored, so the report
   itself is safe to show. For each proposed change, ask:
   - Is the detector right? (An email matcher hitting a URL, a
     phone matcher hitting a form number, an "address" matcher
     hitting a mailing line that needs to stay — all common.)
   - Is the replacement right? Substitution keys win over category
     defaults; flag any unexpected default-placeholder hits.

4. **Amend and re-dry-run if needed.** If the user wants a specific
   replacement, add it to `substitutions.yaml` and run step 2
   again. Iterate until the report reads clean.

5. **Apply only with explicit user confirmation.**

   ```
   uv run python -m scripts.publish.pii_scrub \
       --root drafts/ \
       --substitutions substitutions.yaml \
       --report scrub_report.json \
       --apply
   ```

   Do not apply automatically. Do not chain `--apply` into the
   dry-run call. Two separate invocations is the guardrail.

6. **Verify.** After apply, grep the scrubbed files for any name or
   number you know should not be present. If anything leaks,
   investigate before publishing.

## Synthetic example

For a public write-up of Maryland-Mustang,
`substitutions.yaml` would include:

```yaml
# Real → synthetic. Case-sensitive.
Sally Ridesdale: "Sally Ridesdale"            # already synthetic; no-op anchor
CIM-CLS-0000-0000: "CIM-CLS-0000-0000"
# If the original had been a real case:
#   Real Name: "Synthetic Name"
#   REAL-POLICY-12345: "SYN-POLICY-0000"
```

Category detectors then catch anything not explicitly mapped —
stray email addresses get `redacted@example.invalid`, phones get
`555-000-0000`, etc.

## Do not

- Do not run `--apply` without a dry-run report the user has seen.
- Do not scrub `evidence/`. The script blocks it; this skill
  explains why rather than finding a workaround.
- Do not assume a clean report means the file is publishable. PII
  scrub catches common patterns; it does not catch paraphrase leaks
  or contextual identifiers. Pair with `going-public`.
