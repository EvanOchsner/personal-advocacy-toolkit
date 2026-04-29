---
name: authorities-reconcile
description: Run two independent authority lookups (local table + web research) for a (situation, jurisdiction) pair and present both findings side-by-side with agreement, disagreement, and staleness flags called out. Triggers when the user asks "who do I file with" and the answer matters enough to verify, or before any high-stakes packet is assembled.
---

# authorities-reconcile

Entry-point skill for "who has jurisdiction over this." Runs two independent processes and **always reports both results (or lack thereof)** — never silently prefers one over the other.

The local half is fast, offline, auditable, and curated; but it drifts. The web half is contemporaneous and catches drift; but it can be wrong, incomplete, or unreachable. Reporting both — with reconciliation visible — lets the user use their own judgement.

## When this skill fires

- User asks: "who do I file this with," "who regulates X," "is the agency in our table still right."
- Before [packet-builder](../packet-builder/SKILL.md) populates the `authority` block in `packet-manifest.yaml` for a high-stakes filing.
- After `case-intake.yaml` has a `situation_type` and `jurisdiction.state` but no confirmed forum.

## When to skip (use `authorities-finder` directly)

- The session has no network access.
- The user explicitly asks for the offline-only answer (`"just check our table"`).
- A scripted pipeline needs a deterministic result (no web variability).

## Procedure

1. **Get the inputs.** Pull `situation_type` and `jurisdiction.state` from `case-intake.yaml` if present; otherwise ask the user. Jurisdiction is a 2-letter US state. Situation is a slug from `data/situation_types.yaml`.

2. **Run the local pass.** Invoke [authorities-finder](../authorities-finder/SKILL.md) (or run the script directly):

   ```
   uv run python -m scripts.intake.authorities_lookup \
       --situation insurance_dispute \
       --jurisdiction MD \
       --format json
   ```

   Save the JSON output to a temp file (use `<workspace>/.tmp/authorities_local.json`, not `/tmp/`).

3. **Run the web pass.** Invoke [authorities-web-research](../authorities-web-research/SKILL.md) for the same `(situation, jurisdiction)`. It does *not* read local data; it returns the same JSON shape plus `sources` and `accessed_on`. Save the JSON to `<workspace>/.tmp/authorities_web.json`.

   If the web pass is unavailable (no network, no usable sources), continue with `--web` omitted in the next step. Do **not** fall back to "just use local."

4. **Reconcile.** Run:

   ```
   uv run python -m scripts.intake.authorities_reconcile \
       --local .tmp/authorities_local.json \
       --web   .tmp/authorities_web.json \
       --format json
   ```

   Or omit `--web` if the web pass returned nothing usable.

5. **Present both halves to the user, in this fixed order.** Never collapse them.

   - **Local findings** — every authority from the local pass, with `populated`/`stub` status visible. Do not strip stubs; if local has only stubs, say so plainly.
   - **Web findings** — every authority from the web pass, with cited URLs and the `accessed_on` date. If the web pass was unavailable, say "web pass returned no usable results" — do not silently omit this section.
   - **Reconciliation** — what matched, what's local-only, what's web-only, what conflicts (same agency, different URL/address), what staleness flags fired (local URL domain absent from web sources).
   - **Suggested next step** — a one-sentence recommendation tied to the reconciliation. Examples:
     - "Both halves agree on Maryland Insurance Administration as the primary regulator; URL in `data/authorities.yaml` matches the live site as of 2026-04-27."
     - "Local has no entry for this situation in MD; web found the MD Department of Labor as the apparent regulator — verify against dol.maryland.gov before relying on it."
     - "Local says MIA, web found a renamed-looking agency — staleness flag fired; ask the user to confirm before filing."
   - **Disclaimer + judgement reminder** — `"This is reference information, not legal advice."` plus "verify against the agency's own intake page and use your own judgement before filing."

6. **Write provenance.** The web skill already writes `notes/authorities-research/<date>_<situation>_<juris>_web.json`. Also write the reconciliation JSON to `notes/authorities-research/<date>_<situation>_<juris>_reconciled.json` so the dual-process result is preserved.

## Important: never silently prefer one half

- If web fails: report "web pass returned no usable results." Do not present local alone as if that were the full answer.
- If local has only stubs: report it. Do not dress up `TODO` rows as findings.
- If local and web disagree: surface the disagreement; do not silently pick one. Tell the user which fields differ (`url`, `mailing_address`, `kind`).
- If the staleness flag fires: include it in the user-facing summary by name. The whole point of the dual process is to catch drift.

## Synthetic example (Maryland-Mustang)

For `(insurance_dispute, MD)`:

- **Local:** MIA (populated), MD AG CPD (populated), CFPB (populated, federal scope).
- **Web:** MIA verified via insurance.maryland.gov; MD AG CPD via oag.state.md.us; NAIC state map cross-references MIA.
- **Reconciliation:** all three local entries match web; no conflicts; no staleness flags.
- **Suggested next step:** proceed to [packet-builder](../packet-builder/SKILL.md); the `authority` block can use the MIA entry from `data/authorities.yaml` directly.

## Do not

- Do not skip the web pass to save time on a high-stakes filing.
- Do not skip the local pass even if web "looks complete" — the local table encodes prior judgement and is the auditable baseline.
- Do not collapse the dual report into a single "the answer is X." The user asked for both signals; give them both.
- Do not strip the disclaimer.
- Do not write findings to `/tmp/` — use `<workspace>/.tmp/` and `notes/authorities-research/` per the project's scratch-space and provenance conventions.
