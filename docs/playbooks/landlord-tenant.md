# Playbook: landlord-tenant (stub)

> **Reference material, not legal advice.** Landlord-tenant law is
> **city- and state-specific**; citations below are illustrative, not
> authoritative. Verify with your local legal-aid office or tenant
> union.

**Status:** scaffolded. Mechanics transfer from the insurance-dispute
playbook (policy forms → lease; DOI → state AG / city housing office);
authority and deadline data are not yet populated.

## Situations this playbook covers

- Habitability violations (heat, water, mold, pests, lead) the
  landlord refuses to address.
- Retaliation after a tenant complaint (notice-to-quit, rent hike,
  lease non-renewal following a code-enforcement call).
- Security-deposit disputes at move-out.
- Illegal eviction / self-help eviction (lockout, utility shutoff).
- Rent-escrow / rent-withhold situations where state law allows.
- Fair-housing / discrimination issues.

## Core mechanic

Build a **dated, documented paper trail** before any concrete action:

1. Written notices to landlord (certified mail return-receipt, or
   email with read-receipt) describing the issue and requesting
   remedy.
2. Photo/video evidence with timestamps and xattr capture.
3. Correspondence manifest covering the full exchange.
4. Code-enforcement complaints (where applicable) *in addition to*
   the private notice to landlord — the city inspection report is a
   neutral third-party exhibit.

The packet order in a landlord dispute typically leads with the
lease, then the written notices, then the code-enforcement
inspection, then photos, then the landlord's response (or lack).

## Tool surface

- Evidence pipeline (`evidence_hash.py`, `provenance_snapshot.py`)
  for photos. xattrs matter: Safari and Mail write source URLs, and
  most phone-camera files carry EXIF timestamps that prove when the
  issue was documented.
- Email ingest pipeline for the correspondence.
- Screenshot capture for landlord listings, marketplace posts, or
  public reviews referenced in the dispute.
- `scripts/letters/draft.py --kind preservation` when you need the
  landlord's maintenance records to survive into discovery.
- `scripts/letters/draft.py --kind demand` for rent-escrow / repair
  demand letters.

## Reporting paths to populate

- [ ] City / county code-enforcement office — inspection request URL.
- [ ] State attorney general landlord-tenant / tenant-rights unit
      (where present; varies widely).
- [ ] HUD — fair-housing complaints (protected classes).
- [ ] State housing court / rent-escrow court filing process.
- [ ] Local legal-aid intake.
- [ ] Local tenant union (many cities).

## Populate-this list

- [ ] State security-deposit statute: return window, itemization
      requirement, damages multiplier.
- [ ] State habitability / implied-warranty standard.
- [ ] State retaliation presumption window (e.g., retaliatory action
      within X days of tenant's complaint is presumed retaliatory).
- [ ] State self-help-eviction remedy + damages.
- [ ] State rent-escrow / rent-withholding mechanics (not available
      in all states).
- [ ] Local rent-stabilization / rent-control rules (city-specific).

## When to hire counsel / legal aid

- Eviction notice served.
- Landlord files suit.
- Fair-housing (protected-class) discrimination is plausibly involved.
- Retaliation pattern is established and damages are calculable.

Legal aid is usually free for income-qualified tenants and is the
right first call — tenant matters are a common legal-aid specialty.

## See also

- [`docs/concepts/evidence-integrity.md`](../concepts/evidence-integrity.md)
  — photo/video xattr capture is especially important for habitability.
- Run the lookup:
  `python -m scripts.intake.authorities_lookup --situation landlord_tenant --jurisdiction <state>`
