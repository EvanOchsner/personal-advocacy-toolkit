# Mustang in Maryland — synthetic worked example

> **SYNTHETIC — NOT A REAL CASE.** Every person, company, address,
> claim number, and form number in this directory is invented. If any
> of these resembles a real entity, that is coincidence and should be
> reported so the name can be changed.

This directory holds the fully synthetic end-to-end worked example
that the toolkit's tests and tutorials run against. The goal is to
show the full workflow — from first notice of loss through complaint
packet assembly — on a case where nothing real is at stake, so that
newcomers can see every tool in context before applying it to their
own situation.

For the narrated end-to-end run, see **`WALKTHROUGH.md`**.

## What's in this directory

```
examples/mustang-in-maryland/
  README.md                          ← you are here
  WALKTHROUGH.md                     ← narrated end-to-end run
  CLAUDE.md                          ← case-context file for Claude sessions
  case-facts.yaml                    ← structured facts (case-intake.yaml schema v0.1)
  evidence/
    emails/
      raw/          001..020_*.eml   ← 20 synthetic emails, RFC-5322-ish
      structured/   001..020_*.json  ← structured sidecars
      readable/     001..020_*.txt   ← human-readable format
    valuation/      MidAtlantic-Vehicle-Appraisers-valuation.md
    photos/         photo-01..03_*.md (placeholders; regenerate in Phase 5)
    policy/         CIM-VEH-2023.md, CIM-AV-ENDT-2023.md, CIM-SALV-2023.md
  drafts/
    mia-complaint.md                 ← MIA complaint (Markdown; regenerate as .docx in Phase 5)
    midlife-crisis-opinion-letter.md
    parts-market-comparables.md
  complaint_packet/
    README.md
    packet-manifest.yaml             ← declarative spec for scripts/packet/build.py
    complaint.md                     ← pointer to drafts/mia-complaint.md
    MANIFEST.md                      ← human-readable index
    exhibits/
      A/  B/  C/  D/  E/  F/  G/     ← per-exhibit cover pages
    appendix/
      cover.md                       ← governing-documents appendix
```

## Narrative summary (2 paragraphs)

Delia Vance's 1969 Ford Mustang Mach 1 is rear-ended at a Columbia MD
stoplight on 2025-03-15. The vehicle is insured by Chesapeake Indemnity
Mutual under a classic-vehicle agreed-value policy, agreed value
$58,000. The first shop declines the job (vintage parts sourcing is
outside its scope), so the car moves to Midlife Crisis Restorations of Wilmington
in Wilmington DE. The insurer's appraisal vendor produces an ACV below
the agreed value and a repair estimate using "customary regional rates"
that assume general-population body-shop work.

The insurer offers agreed value minus a $5,280.50 deduction for
"non-customary charges." While the claimant's written objection is on
file, the insurer transfers the vehicle to its salvage vendor
(2025-06-24) without a signed release. The claimant files a complaint
with the Maryland Insurance Administration (real regulator; synthetic
case number `MIA-SYN-0000-0000`), leading the complaint with the
unauthorized salvage transfer as the core grievance.

## Who this example is for

- **Newcomers** who want to see the evidence-integrity + packet-assembly
  workflow top to bottom before applying it to their own situation.
- **Evaluators** (LIT Lab / LSC TIG grantees / legal-aid tech) who want
  a fixture corpus they can run the tools against.
- **Contributors** who need a stable, fully synthetic case to write
  tests and tutorials against.

## What's real and what's not

- **Real**: the jurisdiction (Maryland), the regulator (Maryland
  Insurance Administration), and the general structure of a
  classic-vehicle agreed-value dispute.
- **Not real**: every person, every company, every claim number, every
  policy form number, every VIN, every address, every dollar amount.
  The complaint narrative is fictional.

See `case-facts.yaml` for the canonical fact sheet and `CLAUDE.md` for
the case-context file a fresh Claude session can read to catch up.
