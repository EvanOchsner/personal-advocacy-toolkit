# Playbook: medical billing (stub)

> **Reference material, not legal advice.** Medical billing law
> changes fast (No Surprises Act enforcement posture, state balance-
> billing rules). Verify every citation with counsel or a qualified
> consumer counselor before relying on it.

**Status:** scaffolded. Mechanics transfer from the insurance-dispute
playbook; authority and deadline data are not yet populated.

## Situations this playbook covers

- Surprise bills from out-of-network providers at in-network
  facilities (No Surprises Act territory).
- Balance billing after insurer payment.
- Coding disputes (CPT codes that drive charges upstream of payment).
- Collections referral for a disputed bill.
- Facility-fee surprises at hospital-owned outpatient clinics.

## Core mechanic

Build a three-way paper trail: the **EOB** (Explanation of Benefits
from the insurer), the **provider statement** (the bill), and the
**itemized CPT-coded bill** (you must request this; providers don't
send it by default). The dispute almost always resolves in the gap
between those three.

## Tool surface

- `scripts/ingest/medical_eob.py` — prototype EOB parser (Anthem / UHC
  formats + generic CSV fallback). Produces the same three-layer shape
  as the email pipeline.
- `scripts/ingest/email_eml_to_json.py` — correspondence with billing
  office, insurer, and patient-advocate office.
- Evidence-integrity, packet, and publication-safety pipelines apply
  unchanged.

## Populate-this list

- [ ] State medical board complaint process (provider-conduct issues,
      not billing per se).
- [ ] State insurance commissioner / DOI — HMO / managed-care billing
      disputes.
- [ ] State attorney general consumer-protection — deceptive billing.
- [ ] CMS No Surprises Act complaint portal URL + scope notes.
- [ ] NSA dispute-initiation window (federal).
- [ ] State balance-billing statute citation.
- [ ] State SOL for medical-debt collection.
- [ ] Credit-bureau reporting rules while in dispute (state-dependent).
- [ ] Whether your state has medical-debt consumer-protection statutes
      (MD, NY, NJ, CO, CA, WA have moved on this).

## When to hire counsel / a nonprofit advocate

- The bill is reported to credit bureaus while disputed.
- Collections calls continue after a written dispute (FDCPA — see
  [`debt-collector.md`](debt-collector.md)).
- The provider files suit.
- The amount is above your state's small-claims threshold.

Nonprofits worth calling first: Patient Advocate Foundation, Dollar For,
RIP Medical Debt.

## See also

- [`docs/concepts/authorities-and-regulators.md`](../concepts/authorities-and-regulators.md)
- Run the lookup:
  `uv run python -m scripts.intake.authorities_lookup --situation medical_billing --jurisdiction <state>`
