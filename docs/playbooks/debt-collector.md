# Playbook: debt collector (stub)

> **Reference material, not legal advice.** The FDCPA is federal and
> fairly specific; state-level debt-collection laws often *add* to
> federal protections but never subtract. Verify with counsel.

**Status:** scaffolded. Mechanics transfer from the evidence-integrity
and correspondence-ingest tracks; state-specific authority data is not
yet populated.

## Situations this playbook covers

- Third-party collectors (the collector is not the original creditor).
- First-party collections (original creditor's in-house collections).
- Collection on medical debt (cross-reference
  [`medical-billing.md`](medical-billing.md)).
- Zombie debt (time-barred debt that's been sold).
- Suit / summons received from a collector.
- Credit-bureau reporting during a dispute.

## Core mechanic

**Force the collector onto paper, on the clock.** The FDCPA gives
consumers specific written rights (validation, cease-communication)
that reset the clock on what the collector can legally do. Use them
in writing, preserve the exchange, and let the collector's response
either validate the debt or expose procedural violations.

## Tool surface

- `scripts/letters/draft.py --kind withdrawal` — cease-communication
  letter (FDCPA §805(c)).
- `scripts/letters/draft.py --kind preservation` — for records the
  collector may rotate out of retention.
- `scripts/letters/draft.py --kind demand` — validation-of-debt
  request (FDCPA §809).
- `scripts/ingest/email_eml_to_json.py` and
  `scripts/ingest/voicemail_meta.py` — capture every call and
  message; collector voicemails in particular are FDCPA gold when
  they fail the "meaningful disclosure" requirement.
- Evidence-integrity pipeline for the paper collector mail and any
  court docs served.

## Reporting paths to populate

- [ ] CFPB — https://www.consumerfinance.gov/complaint/ — the primary
      federal venue for FDCPA violations. CFPB complaints are routed
      to the collector with a mandated response window.
- [ ] State AG consumer-protection — state-specific unfair-debt-
      collection statute + URL.
- [ ] State financial-regulation agency — many states license
      debt collectors; the license can be pulled for patterns of
      violation.
- [ ] NACA (National Association of Consumer Advocates) referral
      network — plaintiff-side consumer attorneys, many work on
      contingency for FDCPA cases because the statute has fee-shifting.
- [ ] Local legal aid.

## Populate-this list

- [ ] State unfair-debt-collection statute (often stronger than FDCPA).
- [ ] State SOL for the underlying debt type (varies: 3-15 years).
- [ ] State SOL for a consumer FDCPA action (federal is 1 year).
- [ ] Whether the state recognizes "re-aging" of time-barred debt on
      any partial payment (many do; this is a common trap).
- [ ] Whether the state requires licensing of collectors.

## Key FDCPA tools (not legal advice — verify with counsel)

- **Validation request (§809(b)):** within 30 days of the initial
  communication, a written request for validation suspends collection
  activity until the collector provides verification.
- **Cease-communication letter (§805(c)):** written request that the
  collector stop communicating (with narrow carve-outs). Does not
  eliminate the debt; it changes what the collector is legally
  permitted to do.
- **Suit-filing on time-barred debt:** a per-se FDCPA violation in
  most circuits.

## Zombie debt pattern

Debt that is past the state SOL can still be purchased by collectors
and "resold." Watch for:

- A small payment offer ("settle for $50!") that would restart the
  clock via "re-aging."
- Suit filed in a far-away venue hoping for a default judgment.
- Credit-bureau re-insertion after the 7-year reporting window.

## When to hire counsel

- You are sued. Do not ignore a summons; default judgments are the
  collection industry's business model.
- Patterns of violation are documented and statutory damages +
  fee-shifting make contingency viable.
- The underlying debt may be mistaken or identity-theft-based.

NACA has a lawyer-finder tool; many FDCPA cases are handled on
contingency.

## See also

- [`docs/concepts/evidence-integrity.md`](../concepts/evidence-integrity.md)
- Run the lookup:
  `python -m scripts.intake.authorities_lookup --situation debt_collector --jurisdiction <state>`
