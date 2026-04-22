# CLAUDE.md — Mustang in Maryland (SYNTHETIC — NOT A REAL CASE)

> Every person, company, claim number, policy form, and address referenced
> in this file is invented. See `case-facts.yaml` for the canonical fact
> sheet. This file is an instantiation of `templates/CLAUDE.md.template`
> against those facts, and exists so a fresh Claude session operating in
> this directory has the context it needs without re-reading the whole
> packet.

## Context

Delia Vance's 1969 Ford Mustang Mach 1 was rear-ended at a stoplight in
Columbia, MD on 2025-03-15. The vehicle is insured under a
classic-vehicle agreed-value policy from Chesapeake Indemnity Mutual
(fictional), policy `CIM-CLS-0000-0000`, agreed value $58,000. The
first shop (Dundalk Bodywork and Crabcakes) declined the job citing
parts-sourcing constraints for a 1969 frame; the vehicle was moved to
Midlife Crisis Restorations of Wilmington, a specialist shop in Wilmington, DE.

After inspection by MidAtlantic Vehicle Appraisers (the insurer's
retained vendor), the insurer offered agreed value minus a $5,280.50
deduction for "non-customary charges" (storage rate, specialist labor
rate, NOS-parts sourcing fee). While negotiations were active the
insurer transferred the vehicle to salvage (2025-06-24), which the
claimant treats as the core grievance.

Forum: Maryland Insurance Administration complaint, synthetic case
number `MIA-SYN-0000-0000`, filed 2025-09-12, acknowledged 2025-10-01.

## Key facts and numbers

- **Counterparty:** Chesapeake Indemnity Mutual (fictional)
- **Matter / claim #:** CIM-2025-03-5517 (insurer claim, synthetic)
- **Regulator case #:** MIA-SYN-0000-0000 (synthetic)
- **Loss / incident date:** 2025-03-15
- **Amount in dispute:** $5,280.50 (the deduction) against a $58,000
  agreed value; plus the separate grievance over the salvage transfer
  that occurred while negotiations were ongoing.
- **Policy form set:** CIM-VEH-2023, CIM-AV-ENDT-2023, CIM-SALV-2023

## Legal framework in play

Argued against the counterparty's own stated position, not against
statute directly. The packet invokes:

- The **agreed-value endorsement** (CIM-AV-ENDT-2023): under an
  agreed-value policy the insurer's valuation vendor cannot override
  the schedule of value set at policy inception absent fraud or
  material misrepresentation, neither of which is alleged here.
- The **specialist-shop provision** in CIM-VEH-2023 §VII: classic
  policies contemplate restoration-quality repair, including
  period-correct parts and labor rates that are not comparable to
  contemporary-vehicle "customary" rates.
- The **salvage / total-loss provisions** in CIM-SALV-2023: salvage
  transfer requires claimant consent or a completed total-loss
  settlement; the 2025-06-24 transfer satisfied neither.
- **MD Ins. Code** unfair-claims-settlement practices are cited by
  reference via the MIA complaint; specific counts are stated in
  lawyer mode in the complaint itself.

## Exhibit inventory

See `complaint_packet/manifest.md` for the authoritative list. Working
summary:

- **A** — Declarations page (CIM-CLS-0000-0000, 2024-07 to 2025-07).
- **B** — Full policy form set retrieved from Meritor Insurance Group
  on 2025-04-21 (CIM-VEH-2023, CIM-AV-ENDT-2023, CIM-SALV-2023).
- **C** — Correspondence compilation (ingested emails,
  2025-03-16 through 2025-09-12).
- **D** — MidAtlantic Vehicle Appraisers valuation report
  (2025-04-17).
- **E** — Photographs of the vehicle at Midlife Crisis Restorations of Wilmington
  (synthetic placeholders in this example).
- **F** — Midlife Crisis Restorations of Wilmington opinion letter and parts-market
  comparables (2025-08-15).
- **G** — Salvage-transfer record (2025-06-24) — core grievance.

## Tone

Default: lawyer mode for written artifacts (complaint, position letters,
demand letters); casual mode for verbal drafts and internal reasoning.
See `docs/concepts/tone-modes.md`.

Specifically for this case:

- Lawyer mode treats the agreed-value endorsement as a contract term
  the insurer has already agreed to, not as something to argue for.
- Casual mode, in internal reasoning, is free to say "they're trying
  to re-underwrite the policy after the loss," which lawyer-mode would
  rephrase as "the insurer's conduct is inconsistent with the
  agreed-value endorsement at policy inception."

## Working preferences

- Core arguments are built fresh against the insurer's *current* stated
  position (most recent letter or email), not against the earliest
  denial. If a new position letter lands, the prior one becomes context,
  not the target.
- Flag when an argument is weaker than it reads — for example, the
  "specialist labor rate premium" line item is the weakest leg of the
  dispute on its own, and should not be the lead grievance.
- Salvage transfer while negotiations ongoing (2025-06-24) is the
  strongest grievance and should lead the complaint.
- No document leaves this directory without a `SYNTHETIC — NOT A REAL
  CASE` footer. This is a teaching example; that tag is part of the
  pedagogy.
