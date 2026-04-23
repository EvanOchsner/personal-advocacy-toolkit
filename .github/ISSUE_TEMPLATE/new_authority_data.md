---
name: Populate authority data (new jurisdiction or situation)
about: Contribute a populated entry to data/authorities.yaml or data/deadlines.yaml
title: "[data] <jurisdiction> <situation> authorities/deadlines"
labels: data, good-first-issue
assignees: ''
---

**This is the single most valuable community contribution the toolkit
takes.** Every populated entry converts a stub into usable reference
material for someone facing the same situation.

## What you are contributing

- [ ] New **authority entry** in
      [`data/authorities.yaml`](../../data/authorities.yaml)
- [ ] New **deadline entry** in
      [`data/deadlines.yaml`](../../data/deadlines.yaml)
- [ ] Both

## Jurisdiction and situation

- Jurisdiction (two-letter state code or `federal`):
- Situation slug (match
  [`data/situation_types.yaml`](../../data/situation_types.yaml)):

## Authority entry (if applicable)

For each authority you are adding, provide:

- **Name:** (full official name)
- **Short name:** (commonly used abbreviation)
- **Kind:** (regulator | ombud | bar | ag | federal | nonprofit)
- **URL:** (intake page, not the agency home page if a dedicated
  complaint-intake URL exists)
- **Notes:** (when to use, scope limits, timing expectations — 2-3
  sentences. Include any "verify with counsel" caveats.)

## Deadline entry (if applicable)

For each deadline you are adding, provide:

- **Label:** (e.g., "Statute of limitations, first-party contract")
- **Kind:** (SOL | notice | filing-window | other)
- **Clock starts from:** (loss_date | notice_of_loss | denial_date |
  last_act | custom)
- **Duration:** (days / months / years + number)
- **Authority ref:** (statute citation, regulation, or case name)
- **Notes:** (any conditions, tolling rules, or caveats — 2-3
  sentences. Always include "verify with counsel" language.)

## Source

Cite the statute, regulation, agency website, or secondary source you
used. If you are not a licensed attorney, please note that too — the
per-entry "verify with counsel" tag is important and shouldn't be
dropped.

- [ ] Statute / regulation text (URL):
- [ ] Agency page (URL):
- [ ] Secondary source (URL):
- [ ] I am a licensed attorney in this jurisdiction (optional)

## Verification

- [ ] I have read the existing Maryland (MD) + insurance_dispute
      entries as a template.
- [ ] My entry follows the same shape.
- [ ] I have run the tool against my new entry to confirm it loads:
      ```
      uv run python -m scripts.intake.authorities_lookup --situation <slug> --jurisdiction <STATE>
      uv run python -m scripts.intake.deadline_calc --situation <slug> --jurisdiction <STATE> --loss-date 2025-01-01
      ```

## Willingness to own follow-up

- [ ] I will update this entry if the source data changes within 12
      months.
- [ ] I will not — please mark this entry `last_verified: <date>` so
      a future contributor can audit it.
