# Playbook: consumer scam (stub)

> **Reference material, not legal advice. If the scam is actively in
> progress (mid-call, mid-transfer), contact your bank's fraud line
> before doing anything else.**

**Status:** scaffolded. Mechanics transfer from the evidence-integrity
and publication-safety tracks; per-venue authority data is not yet
populated.

## Situations this playbook covers

- Romance / "pig-butchering" crypto scams.
- Crypto-investment / "guaranteed return" scams.
- Impersonation scams (IRS, SSA, utility, tech support, family).
- Fake-invoice / BEC scams targeting individuals or small businesses.
- Marketplace / classified scams (fake-escrow, fake-shipping).

## Core mechanic

Preserve the scam footprint before the scammer takes it down.
Screenshots are not enough — scammers edit posts, delete accounts,
and rotate domains. Capture tamper-evident web archives, hash them,
and move on.

## Tool surface

- `scripts/ingest/screenshot_capture.py` — playwright / headless-
  Chrome web capture. Produces PDF + DOM + manifest entry with
  retrieved URL, timestamp, and SHA-256. Run this first, before any
  report.
- `scripts/ingest/email_eml_to_json.py` — for the scam emails
  themselves. The raw `.eml` preserves headers (Received:, SPF,
  DKIM, Authentication-Results) that prove sender infrastructure.
- `scripts/evidence_hash.py` and `scripts/provenance_snapshot.py` —
  capture everything as soon as you have it, before memory or
  platforms mutate.
- `scripts/letters/draft.py --kind withdrawal` — for scams that
  involved a recurring authorization (subscription-trap pattern).

## Where to report (populate per-venue)

- [ ] FTC ReportFraud — https://reportfraud.ftc.gov/ — deceptive
      practices, impersonation, business scams.
- [ ] FBI IC3 — https://www.ic3.gov/ — internet crime, cross-border
      fraud, crypto theft above threshold.
- [ ] State AG consumer-protection — state-specific URLs.
- [ ] CFPB — payment-side fraud involving regulated financial products.
- [ ] Your bank / card issuer dispute process — the *fastest*
      potential recovery path; file within the bank's dispute window
      (typically 60-120 days depending on payment rail).
- [ ] Platform abuse teams (Meta, X, Reddit, Discord, crypto
      exchanges) — takedown and potential info subpoena.
- [ ] Crypto-specific: Chainabuse, BitcoinAbuse, exchange abuse desks.

## Realistic expectations per venue

- **FTC / IC3:** reports aggregate into enforcement priorities. You
  will usually not get money back from filing. File anyway — the
  aggregate data matters and a future investigation may benefit.
- **Your bank / card issuer:** by far the best recovery odds if the
  payment was on a consumer card, ACH, or (increasingly) Zelle.
  File fast.
- **Crypto exchanges:** variable. Some cooperate with law enforcement
  quickly; others don't.
- **Civil suit:** rarely cost-effective unless the scammer is
  identified and US-based with recoverable assets.

## Populate-this list

- [ ] State AG consumer-protection — name, URL, filing channel.
- [ ] Applicable state deceptive-practices statute + damages
      multiplier (many states have 3x statutory damages).
- [ ] SOL for state consumer-fraud action.
- [ ] Bank / card-issuer dispute windows (typical: 60 days card, 60
      days ACH, varies Zelle).
- [ ] Whether your state has a specific elder-scam statute.

## When to hire counsel

Usually not the first step. Counsel is cost-justified when:

- Loss is above state small-claims threshold AND the scammer is
  identifiable and US-based.
- A platform is plausibly responsible (negligent design, Section 230
  carve-out, consumer-protection angle).
- A class pattern is visible across multiple victims.

## See also

- [`docs/concepts/evidence-integrity.md`](../concepts/evidence-integrity.md)
  — especially xattr/provenance snapshots for downloaded scam files.
- [`docs/concepts/pii-and-publication.md`](../concepts/pii-and-publication.md)
  — before posting anything to a "scam warning" blog or social media.
