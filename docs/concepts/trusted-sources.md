# Trusted reference documents

PAT's anti-hallucination posture rests on a simple rule: **every
assertion is grounded in a file the user can audit.** That's
straightforward for the user's own evidence — emails, photos, EOBs,
voicemails — which lands under `evidence/` with sha256 hashes and an
append-only pre-commit hook. It's harder for **external authoritative
text**: statutes, regulations, official policies, terms of service,
agency guidance.

A complaint that cites *Md. Code Ins. § 27-303* is only as strong as
the user's confidence that the cite is accurate, the quoted text is
current, and the source was authoritative. Without a copy on disk, the
agent is paraphrasing from training data — which is exactly the
hallucination shape PAT exists to avoid.

The `trusted-sources` skill (and its `scripts/references/` CLI tools)
plug this gap by pulling canonical reference text into the case folder
with the same chain-of-custody discipline the toolkit applies to
evidence.

## Three independent acquisition paths

The skill walks three paths, mirroring the dual-process pattern from
[authorities-reconcile](../../.claude/skills/authorities-reconcile/SKILL.md):

- **Path A — User-supplied copy.** The user already has the doc.
  Ingest it, then *assess* it heuristically (truncation flags, missing
  effective dates, watermarks). The user makes the final call on
  whether to trust the copy — the agent reports flags but does not
  certify authority.
- **Path B — Project-known trusted source.** The curated source
  directory in [`data/reference_sources.yaml`](../../data/reference_sources.yaml)
  maps `(kind, jurisdiction)` to a list of authoritative publishers
  (e.g., `(statute, MD)` → Maryland General Assembly,
  `(regulation, federal)` → eCFR). The agent presents these to the
  user verbatim and offers to fetch or hand off for manual download.
- **Path C — Constrained web search.** Allowlist-only fetch
  (`*.gov`, `*.us`, NAIC, courts.gov, Cornell LII, etc.) with explicit
  denylist (Wikipedia, paywalled aggregators, marketing legal sites).
  Used as a cross-check or when Path B is sparse.

When two or more paths produce a copy, the skill **reports both
side-by-side**. Hash-equal copies consolidate; differences get a
markdown comparison report and the user decides which to rely on.
The dual-process discipline is the whole point: a single source can
be wrong; two independent paths agreeing is much harder to fake.

## Where reference docs live

```
<case>/
  evidence/                 ← your private record (append-only)
    emails/{raw,structured,readable}/
    policy/                 ← case-specific governing documents
    valuation/
    photos/
  references/               ← third-party authoritative text (this concept)
    raw/                    original artifacts (PDF, HTML, DOCX)
    structured/             sidecar JSON (URL, fetch date, sha256, ...)
    readable/               extracted plaintext
    .references-manifest.yaml
  .references-manifest.sha256   ← case-level rollup
```

`references/` is intentionally **not** under `evidence/`'s append-only
pre-commit hook. Public statutes, regulations, and ToS are
reproducible from their original publishers; routine corrections (the
agency posted v2 of a regulation, the platform updated its ToS) should
not require the `ADVOCACY_ALLOW_EVIDENCE_MUTATION=1` escape hatch. The
sha256 manifest still tracks every byte; the difference is posture,
not provenance.

The split is also semantic: `evidence/` is *what the counterparty did
to you*; `references/` is *what the law / contract / official policy
says*. Mixing them muddles both the chain-of-custody story and the
packet-builder reference appendix structure.

## Allow/deny policy

The fetcher (`scripts/references/fetch.py`) refuses any URL whose host
isn't on the allowlist. Trust levels:

| Level | Examples | Behavior |
|---|---|---|
| `primary` | `*.gov`, `*.us`, `naic.org`, agency sites | Default fetch with user confirm. |
| `secondary-trusted` | `law.cornell.edu`, `courtlistener.com` | Allowed; sidecar records the trust level. |
| `secondary-confirm` | `web.archive.org` | Refused unless `--allow-unknown` is passed after explicit user confirmation. |
| `denied` | `*.wikipedia.org`, `casetext.com`, `westlaw.com`, `findlaw.com`, `justia.com` | Hard-refused. |
| `unknown` | anything else | Refused unless `--allow-unknown` after explicit user confirmation. |

Denylist takes precedence over allowlist. The full domain list lives
in [`data/reference_sources.yaml`](../../data/reference_sources.yaml).

This is the same trust hierarchy used by
[authorities-web-research](../../.claude/skills/authorities-web-research/SKILL.md).
By design — the two skills are different consumers of the same
allow/deny policy.

## Sidecar metadata

Every ingested doc gets a `references/structured/<slug>.json` sidecar:

```json
{
  "schema_version": "0.1",
  "source_id": "ab0d0ce80e2d6a64",
  "source_sha256": "...",
  "kind": "statute",
  "citation": "Md. Code Ins. § 27-303",
  "title": "...",
  "jurisdiction": "MD",
  "source_url": "https://mgaleg.maryland.gov/...",
  "source_label": "Maryland General Assembly",
  "source_origin": "fetched",
  "fetched_at": "2026-04-30T22:50:00+00:00",
  "as_of": "2026-04-30",
  "sha256": "...",
  "content_type": "text/html",
  "extraction": {"method": "html-to-text", "text_chars": 13484, "warnings": []},
  "assessment": {"appears_complete": false, "flags": [...]},
  "fetch": {"host": "mgaleg.maryland.gov", "trust": "primary"},
  "disclaimer": "This is reference information, not legal advice."
}
```

The disclaimer is verbatim, mandatory, and load-bearing. Every cite
extracted from a fetched doc and quoted in a draft must additionally
carry `[VERIFY WITH COUNSEL]`.

## Heuristic completeness assessment

For Path A (user-supplied) copies, the ingester runs heuristics
in [`scripts/references/assess.py`](../../scripts/references/assess.py):

| Code | Meaning |
|---|---|
| `truncation-suspected` | Text ends without sentence-final punctuation. |
| `short-for-kind` | Text is below a typical floor for this kind. |
| `has-truncation-marker` | Contains `[truncated]`, `(continued)`, `* * *`, etc. |
| `looks-like-excerpt` | First 500 chars contain "EXCERPT", "PARTIAL", "SAMPLE". |
| `has-watermark` | Contains "DRAFT" / "CONFIDENTIAL" tokens. |
| `no-effective-date` | No "as of" / "effective" / version marker found. |
| `no-section-numbers` | For `statute` / `regulation`, no `§`, "Section N", `(a)(b)` markers. |
| `encoding-issues` | Replacement characters / mojibake. |

These are flags, not pass/fail. The agent surfaces them with the
canonical phrasing — *"You make the call on whether this copy is good
enough; I can flag what I see but I can't certify authority"* — and
the user decides.

## Cross-source comparison

When the user pulled the same doc twice (e.g., once from Path A as a
PDF they had on their laptop, and once from Path B fresh from the
agency site), the `compare` tool surfaces what's different:

```sh
uv run python -m scripts.references.compare \
    --refs references/structured/md-code-ins-27-303.json \
          references/structured/md-code-ins-27-303-2.json \
    --out notes/references/2026-04-30_md-ins-27-303_compare.md
```

Three outcomes:

1. **`raw_sha256_equal: true`** — byte-identical. Consolidate to one
   record; the duplicate can be removed.
2. **`raw_sha256_equal: false, readable_text_equal: true`** —
   different containers (PDF vs HTML) but the substance is the same.
   Keep both; flag in the user-facing summary.
3. **`readable_text_equal: false`** — the rendered text differs. Show
   the diff. Likely causes: one is older, one is an excerpt, one is
   from a non-authoritative republisher.

## Worked example: Maryland-Mustang

The synthetic Maryland-Mustang case (under
[`examples/maryland-mustang/`](../../examples/maryland-mustang/))
ships with two real public-domain statutes:

- **Md. Code Ins. § 27-303** (unfair claim settlement practices) —
  fetched from the Maryland General Assembly publisher
  (`mgaleg.maryland.gov`, `*.gov` allowlist match, `primary` trust).
- **15 USC § 45** (FTC Act, unfair or deceptive practices) — fetched
  from Cornell LII (`law.cornell.edu`, `secondary-trusted` allowlist
  match).

Both are real statutes captured by the live ingester. The sidecars
record `source_origin: fetched`, `fetched_at` timestamps, and the
`assessment` block (which fires e.g. `truncation-suspected` because
the rendered HTML ends with site-footer navigation rather than statute
text — a real-world quirk worth knowing about).

To inspect:

```sh
uv run python -m scripts.references.list \
    --case-root examples/maryland-mustang
```

```
ID                 KIND               JURIS    CITATION                         TITLE
------------------------------------------------------------------------------------------
ab0d0ce80e2d6a64   statute            MD       Md. Code Ins. § 27-303           Laws - Statute Text
340be2b2e3c84930   statute            federal  15 USC § 45                      15 U.S. Code § 45 ...
```

## Where this fits in the workflow

The `trusted-sources` skill is **Phase 3b** in
[pat-workflow](../../.claude/skills/pat-workflow/SKILL.md) — between
Phase 3 (authorities lookup) and Phase 4 (deadline computation):

1. Phase 1 — set up the case workspace
2. Phase 2 — intake (situation classification)
3. Phase 3 — authorities lookup (who has jurisdiction)
4. **Phase 3b — trusted reference docs** *(this concept)*
5. Phase 4 — deadline computation
6. Phase 5 — evidence intake
7. Phase 6 — drafting
8. Phase 7 — packet assembly
9. Phase 8 — publication safety

Phase 3b is optional — not every case cites outside text. But for any
complaint that quotes or relies on a specific statutory provision,
regulation, or ToS clause, the cited text should be in `references/`
*before* the complaint is drafted. Drafting against the actual text
catches paraphrase drift early.

## Disclaimers (always)

Every emit, every quote, every downstream draft carries:

> *This is reference information, not legal advice.*

…and any cite extracted from a fetched doc carries `[VERIFY WITH
COUNSEL]`. These strings are stamped into sidecars by
[`scripts/references/ingest.py`](../../scripts/references/ingest.py)
automatically; do not strip them when reporting.
