# references/

Trusted reference documents for the synthetic Maryland-Mustang
example. Two real public-domain statutes were ingested via the
`trusted-sources` pipeline — one from the Maryland General Assembly
publisher, one from Cornell LII — to give the example a complete
end-to-end picture.

## Contents

- `raw/md-code-ins-27-303.html` — Md. Code Ins. § 27-303 (unfair
  claim settlement practices), fetched live from
  `mgaleg.maryland.gov`.
- `raw/15-usc-45.html` — 15 USC § 45 (FTC Act, unfair or deceptive
  practices), fetched live from `law.cornell.edu`.

Both have matching `structured/<slug>.json` sidecars (provenance
metadata) and `readable/<slug>.txt` plaintext extractions.

## How these were generated

The two statutes were pulled via the `trusted-sources` skill's Path B
flow (project-known trusted source from
[`data/reference_sources.yaml`](../../../data/reference_sources.yaml)):

```sh
uv run python -m scripts.references.ingest \
    --url "https://mgaleg.maryland.gov/mgawebsite/Laws/StatuteText?article=gin&section=27-303" \
    --kind statute \
    --citation "Md. Code Ins. § 27-303" \
    --jurisdiction MD \
    --source-label "Maryland General Assembly (mgaleg.maryland.gov)" \
    --as-of "2026-04-30" \
    --case-root .

uv run python -m scripts.references.ingest \
    --url "https://www.law.cornell.edu/uscode/text/15/45" \
    --kind statute \
    --citation "15 USC § 45" \
    --jurisdiction federal \
    --source-label "Cornell Legal Information Institute (law.cornell.edu)" \
    --as-of "2026-04-30" \
    --case-root .
```

Both files are public-domain statutes; checking them in is fine
(no copyright concern, no real case material). Re-running the
commands fetches a fresh copy from the original publisher.

## Inspecting

```sh
uv run python -m scripts.references.list --case-root .
```

Or to assess one of the readable extractions in isolation:

```sh
uv run python -m scripts.references.assess \
    --file readable/md-code-ins-27-303.txt \
    --kind statute
```

## Disclaimers

Every doc here carries the verbatim disclaimer:

    This is reference information, not legal advice.

For a real case, also tag any extracted cite quoted in a draft with
`[VERIFY WITH COUNSEL]`.

## See also

- [`docs/concepts/trusted-sources.md`](../../../docs/concepts/trusted-sources.md)
  — design rationale.
- [`.claude/skills/trusted-sources/SKILL.md`](../../../.claude/skills/trusted-sources/SKILL.md)
  — agent-side workflow.
