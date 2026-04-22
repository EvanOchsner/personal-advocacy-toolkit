# Playbook: employment retaliation (stub)

> **Reference material, not legal advice.** Employment-law deadlines
> are **unforgiving** — federal Title VII filing windows can be as
> short as 180 days. Verify with counsel now, not later.

**Status:** scaffolded. Mechanics transfer from the insurance-dispute
playbook (policy forms → employee handbook; DOI → EEOC / state FEPA);
authority and deadline data are not yet populated.

## Situations this playbook covers

- Retaliation for protected-activity complaints (Title VII, FLSA,
  OSHA whistleblower, NLRB concerted activity, SOX, Dodd-Frank,
  state whistleblower statutes).
- Wrongful termination following a protected complaint.
- Hostile-environment harassment that continues after reporting.
- Wage-and-hour retaliation (FLSA / state labor commission).
- Failure to accommodate (ADA / FMLA / PWFA) followed by retaliation.

## Core mechanic

The whole case is about **connecting the timeline**. Document (a) the
protected activity, (b) the employer's awareness of it, and (c) the
adverse action — in that order, with dates. A clean three-point
timeline wins most retaliation cases; a muddled one loses them.

## Tool surface

- `scripts/ingest/email_eml_to_json.py` — every work email that
  touches the protected activity, the reporting chain, or the
  adverse action.
- `scripts/ingest/sms_export.py` — work-related texts, especially
  manager communications outside official channels.
- `scripts/ingest/voicemail_meta.py` — voicemails from HR or
  management.
- Evidence-integrity + provenance pipeline — critical because the
  employer controls the primary sources (email servers, HR systems).
  Your locally-preserved copies with hashes and git timestamps are
  often the most reliable record.
- `scripts/letters/draft.py --kind preservation` — to HR and
  general counsel, **immediately**, to freeze email/IM/HR records
  before normal retention deletes them.

## Reporting paths — federal

- [ ] EEOC — https://www.eeoc.gov/ — Title VII, ADA, ADEA, GINA,
      PWFA retaliation. **Filing window: typically 180 days from
      the adverse action; extends to 300 days in states with a
      work-sharing FEPA.** Verify the window for your state.
- [ ] OSHA Whistleblower — https://www.whistleblowers.gov/ — 22+
      federal statutes, many with 30-180 day windows.
- [ ] NLRB — https://www.nlrb.gov/ — concerted activity retaliation,
      union-related activity. 6-month window.
- [ ] DOL Wage and Hour — FLSA retaliation.
- [ ] SEC Whistleblower / CFTC Whistleblower — Dodd-Frank / SOX
      retaliation. Bounty programs.

## Reporting paths — state (populate per jurisdiction)

- [ ] State FEPA (Fair Employment Practices Agency) — state-level
      EEOC counterpart. Often dual-filing is automatic.
- [ ] State labor commissioner — wage-and-hour retaliation.
- [ ] State whistleblower statute (where present) — often broader
      protections than federal.

## The deadline problem

Most situations in this toolkit have forgiving deadlines. Employment
does not. The tool will:

```
python -m scripts.intake.deadline_calc \
  --situation employment_retaliation --jurisdiction <state> \
  --loss-date <adverse-action-date>
```

Flag the EEOC/FEPA window. **Confirm it with counsel the same day you
identify the adverse action.** Most employment attorneys offer free
intake consultations specifically for this reason.

## Populate-this list

- [ ] State FEPA name, URL, filing process.
- [ ] Whether state has a work-sharing agreement with EEOC
      (extending the window to 300 days).
- [ ] State whistleblower statute citation + deadline.
- [ ] State retaliation statute of limitations.
- [ ] State employment-at-will exceptions (public policy, implied
      contract, covenant of good faith) — varies significantly.
- [ ] State WARN Act equivalents.

## When to hire counsel

**Immediately** for any retaliation case. Plaintiff-side employment
attorneys overwhelmingly work on contingency for viable cases
because federal statutes have fee-shifting. The intake call is free.
The deadline to file charges is the constraint; don't miss it trying
to DIY the charge.

Referrals: NELA (National Employment Lawyers Association) has a
find-a-lawyer tool; state-level bar referral services.

## See also

- [`docs/concepts/evidence-integrity.md`](../concepts/evidence-integrity.md)
  — especially critical when the employer controls primary sources.
- [`docs/concepts/authorities-and-regulators.md`](../concepts/authorities-and-regulators.md)
- Run the lookup:
  `python -m scripts.intake.authorities_lookup --situation employment_retaliation --jurisdiction <state>`
