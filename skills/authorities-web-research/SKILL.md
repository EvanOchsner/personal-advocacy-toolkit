---
name: authorities-web-research
description: Independently research the right regulators, ombuds, AG offices, and federal backstops for a (situation_type, jurisdiction) pair using only contemporaneous official public sources (.gov / .us / NAIC / courts.gov). Triggers as the web half of authorities-reconcile, or when the user explicitly asks "what does the live web say about who regulates X."
---

# authorities-web-research

The **web-only** half of a dual-process authority lookup. The local half lives in [authorities-finder](../authorities-finder/SKILL.md) and reads `data/authorities.yaml`. This skill does *not* read that table — it must form its answer purely from what it finds online so the two passes are genuinely independent.

The reconciler ([authorities-reconcile](../authorities-reconcile/SKILL.md)) compares both. If this skill reads local data, it can't disagree, and the reconciliation is meaningless.

## When this skill fires

- Invoked by `authorities-reconcile` as part of a dual lookup.
- User explicitly asks: "what does the live web say about who regulates this," "is the agency in our table still the right one," "has anything been renamed."
- Before relying on a `populated` row in `data/authorities.yaml` for a high-stakes filing — to catch drift.

## Forbidden inputs

- Do **not** read `data/authorities.yaml`, `case-intake.yaml`, or any project file beyond the `(situation, jurisdiction)` tuple passed in. If the user invokes this skill conversationally and you happen to know the local answer from earlier in the session, set that knowledge aside — answer from the web only.
- Do **not** ask the user "what does our table say" — that defeats independence.

## Trusted sources, in priority order

1. **The agency's own `.gov` / `.us` website.** Examples: `insurance.maryland.gov`, `oag.state.md.us`, `dca.ca.gov`, `dol.ny.gov`. The contact / file-a-complaint page on the agency's own site is the canonical citation.
2. **Curated official directories.** NAIC state insurance regulator map (insurance disputes); state bar association directories (attorney discipline); courts.gov / state judicial branch sites (court venue questions); USA.gov agency directory; HHS.gov Office for Civil Rights state map (medical privacy).
3. **Federal regulator landing pages** for backstops: CFPB (`consumerfinance.gov`), FTC (`ftc.gov` / `reportfraud.ftc.gov`), HHS-OCR, DOL, EEOC, HUD, IC3 (`ic3.gov`).

## Forbidden sources

- **No** Wikipedia as a primary cite. Wikipedia is allowed only as a navigational hint to find the agency's official name; the citation must be the agency's own page.
- **No** legal-marketing sites (Avvo, FindLaw consumer pages, Justia overviews, Nolo, LegalZoom).
- **No** AI-generated answer panels (Google AI Overviews, Bing Copilot summaries, Perplexity answers). Click through to the underlying source.
- **No** aggregator review sites, no SEO landing pages, no PDFs of unknown provenance.
- **No** caches or archives unless the live agency page is unreachable *and* you note the staleness explicitly.

If the only sources you can find are forbidden, return an empty `authorities` list with a warning — better to say "no usable sources" than to launder a bad citation.

## Search procedure

For each `(situation, jurisdiction)`:

1. **Resolve the primary regulator.** Run `WebSearch` queries like:
   - `"<situation phrase>" "<state full name>" regulator site:.gov`
   - `"<state>" "department of <X>" file complaint`
   - For insurance: also search the NAIC state map.
2. **Resolve the AG consumer-protection division.** `"<state> attorney general" "consumer protection" site:.gov`.
3. **Resolve federal backstops** for the situation type (one or two, not a kitchen-sink list).
4. **Open each candidate page with `WebFetch`** and verify:
   - Agency name (exact, current).
   - Intake URL or file-a-complaint URL (not just the homepage when an intake page exists).
   - Mailing address, phone if shown.
   - Jurisdiction scope — does the page itself say it covers this situation? An insurance regulator that disclaims jurisdiction over self-funded ERISA plans should be flagged.
   - Page-modified or last-reviewed date if shown.
5. **Reject** any candidate where:
   - The page doesn't load.
   - The URL doesn't resolve to the expected `.gov` / `.us` domain (or NAIC / courts.gov for directory cases).
   - The agency's scope obviously excludes the user's situation.

## Output shape

Mirror the JSON shape produced by `authorities_lookup.lookup()` so [authorities-reconcile](../authorities-reconcile/SKILL.md) can compare apples-to-apples. Add `sources` and `accessed_on`:

```json
{
  "disclaimer": "This is reference information, not legal advice.",
  "situation": "insurance_dispute",
  "jurisdiction": "MD",
  "warnings": ["…"],
  "authorities": [
    {
      "name": "Maryland Insurance Administration",
      "short_name": "MIA",
      "kind": "regulator",
      "scope": "MD",
      "url": "https://insurance.maryland.gov/Consumer/Pages/FileAComplaint.aspx",
      "notes": "Verified at insurance.maryland.gov on 2026-04-27."
    }
  ],
  "sources": [
    {"url": "https://insurance.maryland.gov/Consumer/Pages/FileAComplaint.aspx",
     "accessed_on": "2026-04-27"},
    {"url": "https://content.naic.org/state-insurance-departments",
     "accessed_on": "2026-04-27"}
  ],
  "accessed_on": "2026-04-27"
}
```

The `kind` enum matches the local script: `regulator | ombud | bar | ag | federal | nonprofit`.

## Provenance writeback

After the search, write the JSON to:

```
notes/authorities-research/<YYYY-MM-DD>_<situation>_<jurisdiction>_web.json
```

(Create the directory if it doesn't exist.) This makes the dual-process result auditable later, the same way `provenance/snapshots/` audits evidence.

## Disclaimer

Reuse the project's standard disclaimer string — `"This is reference information, not legal advice."` — verbatim, in the `disclaimer` field. Do not paraphrase.

## Do not

- Do not read the local table and parrot it back as a "web finding."
- Do not cite Google AI Overviews, ChatGPT, or any other LLM output as a source.
- Do not invent URLs you didn't actually fetch.
- Do not strip the `sources` array — without it, the reconciler can't compute staleness.
- Do not answer "should I file here" — that's triage. Defer to `situation-triage`.
