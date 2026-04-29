---
name: authorities-finder
description: Look up the right regulators, ombuds, bar associations, AG offices, and federal backstops for a (situation_type, jurisdiction) pair — triggers when the user asks "who do I complain to" or "who has jurisdiction over this."
---

# authorities-finder

A conversational wrapper around `scripts/intake/authorities_lookup.py`.
The script is the source of truth; this skill makes it usable without
the user memorizing flags.

This is the **local-only** half of a dual-process lookup. It reads
`data/authorities.yaml` and nothing else. For the full picture —
local lookup + independent web research + reconciliation — invoke
[authorities-reconcile](../authorities-reconcile/SKILL.md) instead.
Use this skill directly when the session is offline, the user
explicitly wants the offline-only answer, or a scripted pipeline
needs a deterministic result.

## When this skill fires

- User asks "who regulates X" or "who do I file this with."
- Any time `case-intake.yaml` has a `situation_type` but no
  identified forum yet.
- Before `packet-builder` fires — the packet authority comes from
  here.

## Procedure

1. **Get the inputs.** Pull `situation_type` and `jurisdiction.state`
   from `case-intake.yaml` if it exists; otherwise ask the user for
   both. Jurisdiction is a 2-letter US state. Situation is a slug
   defined in `data/situation_types.yaml`.

2. **Run the lookup.** Prefer JSON for programmatic consumption, or
   the default human format for display:

   ```
   uv run python -m scripts.intake.authorities_lookup \
       --situation insurance_dispute \
       --jurisdiction MD
   ```

   For a machine-readable handoff to `packet-builder`:

   ```
   uv run python -m scripts.intake.authorities_lookup \
       --situation insurance_dispute \
       --jurisdiction MD \
       --format json
   ```

3. **Present the bucket structure to the user.** The output is
   grouped:
   - **regulator** — the primary administrative body.
   - **ombuds** — non-binding escalation path.
   - **bar / attorney discipline** — only relevant if the
     counterparty is a licensed attorney.
   - **AG** — state attorney general, for consumer-protection
     angles or pattern-of-practice complaints.
   - **federal** — CFPB, HHS-OCR, DOL, etc. — backstops that sit
     over state regulators.

   Each record has a `status` field (`populated` or `todo`). Do NOT
   treat `todo` entries as usable — say so.

4. **Flag unknowns.** If the jurisdiction isn't populated, the
   script falls through to federal-only. Tell the user plainly:
   "state-specific authorities for XX are not yet in the table."
   Do not fabricate a URL or mailing address.

5. **Keep the disclaimer.** The script's output includes a banner —
   "This is reference information, not legal advice." When you
   quote the output, keep the banner visible. Do not strip it.

## Synthetic example

For Maryland-Mustang the lookup returns:

- **regulator:** Maryland Insurance Administration — the primary
  forum. This becomes the `authority` block in the packet manifest.
- **ombuds:** NAIC state map entry for MD.
- **AG:** Maryland Office of the Attorney General, Consumer
  Protection Division — relevant if a pattern of unfair practice
  across insureds surfaces.
- **federal:** no federal regulator has direct jurisdiction over a
  state-licensed insurer's claim handling; none listed.

The skill then hands off to `packet-builder`, which wires the MIA
address and intake URL into `packet-manifest.yaml`.

## Definition of done

The user has seen the bucket structure for their `(situation_type,
jurisdiction)` pair, knows which entry is the **primary forum**
(usually the regulator bucket), and has the disclaimer attached. If
this is being driven by `pat-workflow`, hand control back so the
orchestrator can move to deadline computation (Phase 4).

If the lookup returned only `todo` stubs or only federal backstops
because the state isn't populated, **say so explicitly** and offer
to run `authorities-reconcile` (web reconciliation) before treating
the result as the answer.

## Do not

- Do not invent authorities the script doesn't list.
- Do not present a `todo` stub as an actual contact.
- Do not answer "should I file here" — that's triage, not lookup.
  Defer to `situation-triage`.
