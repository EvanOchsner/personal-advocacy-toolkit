---
name: situation-triage
description: Read an existing case-intake.yaml, sanity-check the situation_type and proposed authorities, and flag framing weaknesses before any drafting begins — triggers after case-intake or whenever the user asks "is this the right framing?"
---

# situation-triage

This skill runs *after* `case-intake.yaml` exists. It is the
gut-check pass: does the classification still make sense now that you
can see the whole picture, and does the user's framing hold up?

## When this skill fires

- User asks "is this the right situation type?" or "am I framing this
  right?"
- A `case-intake.yaml` exists but `situation_type` is `unknown` or the
  user expresses uncertainty about it.
- Before the first letter draft or packet build.

## Procedure

1. **Load the inputs.** Read `case-intake.yaml` in the cwd. Pull
   `situation_type`, `subtype` (if present), `jurisdiction.state`,
   `parties`, and the free-text `notes` / `situation` field.

2. **Pull the candidate authorities.** Run:

   ```
   python -m scripts.intake.authorities_lookup \
       --situation <situation_type> \
       --jurisdiction <state>
   ```

   This emits a list of regulators, ombuds, bar, AG, and federal
   backstops keyed on the slug. Do NOT drop the disclaimer banner
   when quoting the output to the user.

3. **Sanity-check the framing.** For each of these, state your view
   explicitly:
   - Is `situation_type` still the closest slug, or has the user's
     description drifted (e.g. an `insurance_dispute` that is really
     a `debt_collection` matter underneath)?
   - Does the proposed forum (first authority in the list) actually
     take the kind of complaint the user has? A state insurance
     regulator does not adjudicate contract damages; a small-claims
     court does not license insurers. Name the mismatch if you see
     one.
   - Is the strongest grievance the one the user is leading with?
     Weak-lead-first is a common framing mistake.

4. **Name at least one thing the user could be wrong about.** Triage
   is not validation. If you can't think of a counter-frame, say so
   explicitly rather than rubber-stamping.

## Synthetic example

For Mustang-in-Maryland the initial draft listed the $5,280.50
deduction as the lead grievance. Triage should flag: the
salvage-transfer-during-negotiations (2025-06-24) is the cleaner
procedural violation and makes a stronger lead. The deduction is a
damages fight; the salvage transfer is a rule fight. Lead with the
rule fight; the damages follow.

Similarly, triage should note: `insurance_dispute` is the right slug
at the level of forum (Maryland Insurance Administration), but
subtype `auto_total_loss_bad_faith` carries load the complaint has
to actually support. If the user doesn't have a UCSP-practice
pattern across claims, "bad faith" may oversell what the record
shows — consider `auto_total_loss_valuation_dispute` as the working
subtype until a pattern emerges.

## Do not

- Do not silently re-classify. If you think the slug is wrong, say so
  and let the user decide; then rerun `situation_classify.py` with
  updated answers.
- Do not fabricate authorities. If `authorities_lookup.py` says a
  jurisdiction isn't populated yet, say so — don't invent one.
