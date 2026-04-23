# Authorities and regulators

The "who cares about this?" map. Most people default to "I should call
a lawyer" or "I should write my congressman." Neither is usually the
right first step. For most situations there is a specific office whose
statutory job is to receive your complaint, investigate, and either
act on it or tell you in writing why they won't. Knowing which office
is half the battle.

This page explains the landscape; `data/authorities.yaml` and
`scripts/intake/authorities_lookup.py` implement it.

## Two axes: situation × jurisdiction

Authorities are indexed by two dimensions:

- **Situation type** — insurance dispute, medical billing, consumer
  scam, harassment, landlord-tenant, debt collection, employment
  retaliation. The canonical list lives in
  `data/situation_types.yaml`.
- **Jurisdiction** — typically your state (two-letter code) plus the
  `federal` bucket, which is returned in addition to state results for
  every lookup.

Running the lookup:

```sh
uv run python -m scripts.intake.authorities_lookup \
  --situation insurance_dispute --jurisdiction MD
```

returns a ranked shortlist of authorities, each tagged with its kind
(regulator, ombuds, state AG, bar, federal agency, nonprofit), a URL,
and a short "what to use this for" note. Every record carries a
`status: populated | stub` flag so you can tell real entries from
placeholders.

## Kinds of authority

### Regulators

The office whose statutory job is to oversee the industry your
counterparty operates in:

- **State Departments of Insurance** (e.g., Maryland Insurance
  Administration) for first-party insurance claim handling.
- **State medical boards** for individual physician conduct.
- **State bar lawyer-regulation arms** for attorney misconduct.
- **State AG consumer-protection divisions** for deceptive
  business practices that cross industries.
- **Public utility / public service commissions** for regulated
  utility billing.

Regulators act on complaints that fit their statutory mandate. A
well-packaged complaint they can act on usually produces some
response; a poorly-packaged one usually produces a form letter back.

### Ombuds and consumer advocates

Not regulators in the statutory sense, but institutionalized
consumer-side advocates:

- **State health insurance assistance programs (SHIPs)** for Medicare.
- **State attorneys general consumer-protection hotlines.**
- **Nonprofits** like United Policyholders (insurance), the National
  Consumer Law Center (debt/consumer), CAIR (harassment), HUD-certified
  housing counselors (landlord/tenant).

These offices have no enforcement power but can explain the landscape
and often have a direct line into the regulator. They are the right
first call when you are still figuring out what your situation is.

### Federal agencies

Returned *in addition* to state authorities when applicable:

- **CFPB** — consumer financial products (debt collection, lender-placed
  insurance, credit reporting).
- **FTC ReportFraud / IC3** — deceptive practices, online scams, fraud.
- **HUD** — housing discrimination, federally-backed mortgage issues.
- **EEOC** — employment discrimination and retaliation.
- **CMS / No Surprises Act complaint portal** — federal surprise-billing
  protections.

Federal-only results are always returned, even when no state entry
exists for your jurisdiction yet. This is deliberate: federal fallback
is better than no guidance at all.

### Law enforcement

Included in the lookup only when the situation plausibly crosses into
criminal territory (impersonation, fraud above a dollar threshold,
physical harassment, stalking). For purely civil matters, law
enforcement is the wrong door — they will route you back to a
regulator or small-claims court. See the situation-specific playbook
for thresholds.

## Status flags

Every entry in `data/authorities.yaml` carries a `status`:

- `populated` — reviewed entry with a real URL and usable notes.
- `stub` — placeholder awaiting community contribution.

The lookup tool surfaces stubs with a `[STUB]` tag so you know not to
rely on them. Contributing a populated entry is a good first
open-source contribution: one YAML edit, one pull request.

## What to file first

Priority order, applicable to most situations:

1. **Regulator complaint** (if one has jurisdiction). Free, produces a
   paper trail, often generates an insurer / counterparty response
   within a defined window.
2. **State AG consumer-protection filing** as a belt-and-suspenders
   move when conduct crosses industries or involves deceptive
   practices.
3. **Federal filing** (CFPB / FTC / HUD / EEOC, whichever fits). Adds
   a second regulator lens; CFPB in particular routes complaints back
   to the counterparty for a mandated response.
4. **Counsel** if the dispute is above small-claims thresholds, if the
   regulator closes the complaint without relief, or if statute-of-
   limitations is approaching. See
   [`tutorials/03-understanding-the-situation.md`](../tutorials/03-understanding-the-situation.md)
   for the "when to hire a lawyer" discussion.

## Verify with counsel

**This is reference information, not legal advice.** The lookup
returns authorities that plausibly have jurisdiction. Whether any
given authority *actually* has jurisdiction over your specific
situation is a legal question. When in doubt, confirm with a lawyer
licensed in your state before filing.

## See also

- [`docs/tutorials/03-understanding-the-situation.md`](../tutorials/03-understanding-the-situation.md)
- [`docs/playbooks/`](../playbooks/) — per-situation playbooks
- [`data/authorities.yaml`](../../data/authorities.yaml)
- [`data/situation_types.yaml`](../../data/situation_types.yaml)
