# Playbook: harassment / cyberbullying (stub)

> **Reference material, not legal advice. If you are in immediate
> danger, call 911 (US) or your local emergency number.**

**Status:** scaffolded. Mechanics around tamper-evident web capture
transfer directly from the evidence-integrity track; venue-specific
authority data is not yet populated.

## Situations this playbook covers

- Targeted online harassment across social platforms.
- Doxxing or threats of doxxing.
- Defamation / false-review campaigns targeting a small business or
  individual.
- School-based cyberbullying (minors).
- Workplace-based online harassment.
- Stalking that has migrated online (ongoing or historical).

## Core mechanic

**Capture everything, immediately, before the platform takes it down
or the harasser edits/deletes.** Platform takedowns — even good ones —
destroy your evidence. You need tamper-evident copies first.

## Tool surface

- `scripts/ingest/screenshot_capture.py` — produces PDF + DOM +
  manifest entry with retrieved URL, timestamp, and SHA-256.
  **Install playwright for evidence-grade capture** (prototype
  backend):
  ```
  uv pip install playwright && uv run playwright install chromium
  ```
- `scripts/evidence_hash.py` + `scripts/provenance_snapshot.py` —
  hash and snapshot the captures as soon as they land.
- `scripts/publish/exif_scrub.py` — if you later publish a derivative,
  scrub your own screenshots' metadata.
- `scripts/letters/draft.py --kind cease-desist` — when the harasser
  is identifiable and you want to create a paper trail before an
  escalation.
- `scripts/letters/draft.py --kind preservation` — to any platform
  you know holds relevant evidence, so they preserve it past their
  normal retention window.

## Reporting paths to populate

- [ ] Platform abuse teams — per-platform URLs and scope.
- [ ] Local law enforcement non-emergency line — for threats and
      stalking that cross into criminal territory.
- [ ] FBI IC3 — https://www.ic3.gov/ — for interstate harassment and
      stalking.
- [ ] School district Title IX office (for school-based incidents).
- [ ] Employer HR / Title VII office (for workplace-based incidents).
- [ ] State attorney general cyberharassment unit (where present).
- [ ] Relevant state cyberharassment / revenge-porn statute citation.
- [ ] Protective-order / restraining-order mechanics in your
      jurisdiction (varies state-to-state; timelines are typically
      fast).

## Civil vs criminal

Harassment often straddles both:

- **Criminal** — threats, stalking, sextortion, NCII (non-consensual
  intimate imagery), CFAA-style access violations. Law enforcement is
  the right door.
- **Civil** — defamation, intentional infliction of emotional
  distress, tortious interference (for business-targeted campaigns),
  injunction / protective order.
- **Platform policy** — TOS violations, typically handled through
  platform reporting before any legal step.

The order that usually works best: **capture → platform report →
(criminal report if applicable) → civil counsel if the above don't
produce relief**.

## When to hire counsel

- The harassment is affecting a business or your employment.
- Defamation damages are calculable and exceed small-claims threshold.
- You need an anti-SLAPP posture (you are being counter-sued for
  speaking up).
- Protective order is needed and you want it done right the first
  time.

Specialist nonprofits: Cyber Civil Rights Initiative (NCII / revenge
porn), ADL (identity-based harassment), EFF (broad digital-rights
issues).

## Populate-this list

- [ ] Per-platform abuse-report URL (Meta, X, Reddit, TikTok,
      YouTube, Discord, LinkedIn).
- [ ] Per-state cyberharassment statute citation.
- [ ] Per-state NCII / revenge-porn statute citation and remedies.
- [ ] Protective-order filing process by state.
- [ ] Anti-SLAPP statute availability by state.

## See also

- [`docs/concepts/evidence-integrity.md`](../concepts/evidence-integrity.md)
  — forensics grade matters here even more than in contract disputes.
- [`docs/concepts/pii-and-publication.md`](../concepts/pii-and-publication.md)
  — extra caution before publishing *anything* about a harasser: you
  can escalate, expose yourself to a defamation counter-suit, or
  doxx bystanders unintentionally.
