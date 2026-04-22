# Walkthrough — Mustang in Maryland

> **SYNTHETIC — NOT A REAL CASE.** Read `README.md` in this directory
> first. Every name, number, and date below is invented.

This walkthrough runs the advocacy toolkit end-to-end against the
synthetic Mustang case. It is both a tutorial and the integration-test
driver for `tests/`.

Phase 2 (this phase) only authors the case content. Many of the tools
called out below are authored in later phases; those calls are flagged
`TODO-Phase-N`. Phase 5 will validate this walkthrough end-to-end and
refactor any steps that trip.

---

## 0. Prerequisites

Assume you have cloned the `advocacy-toolkit` repo and run
`pip install -e .`. You are in the repo root.

```bash
cd examples/mustang-in-maryland
```

---

## 1. Read the case-context file

You should not need to; a Claude session in this directory will read
it automatically. But to understand the case before running tools:

```bash
cat CLAUDE.md
cat case-facts.yaml
```

You should see a two-paragraph situation summary in `CLAUDE.md` and a
structured fact sheet in `case-facts.yaml` (the first concrete example
of the `templates/case-intake.yaml` schema).

---

## 2. Hash and snapshot evidence

The toolkit's evidence-integrity track (Phase 1A) produces a hash
manifest of everything under `evidence/`, so that later derivatives can
be provenance-joined back to source.

```bash
# Phase 1A
python -m scripts.evidence_hash --root evidence --out .evidence-manifest.json
python -m scripts.provenance_snapshot --root evidence
```

Expected outcome: `.evidence-manifest.json` lists ~45 files (20 .eml +
20 .json + 20 .txt + 3 policy .md + 1 valuation .md + 3 photo
placeholders + 1 photos README). Each line carries a SHA-256.

> `TODO-Phase-1A`: until the final pre-commit config ships, hashing
> non-image placeholder files produces a warning but does not error.

---

## 3. Ingest correspondence

Phase 1B ports the three-layer email pipeline. The 20 emails are
already laid out in `evidence/emails/{raw,structured,readable}/`, so
ingestion here is a dry run that validates the layout rather than
creating it from an mbox.

```bash
# Phase 1B
python -m scripts.ingest.email_eml_to_json \
  --in evidence/emails/raw \
  --out evidence/emails/structured \
  --validate-only
python -m scripts.ingest.email_json_to_txt \
  --in evidence/emails/structured \
  --out evidence/emails/readable \
  --validate-only
python -m scripts.manifest.correspondence_manifest \
  --in evidence/emails/structured \
  --out correspondence-manifest.yaml
```

Expected outcome: `correspondence-manifest.yaml` lists 20 emails with
thread slugs (`fnol-initial`, `first-shop-decline`, `mava-inspection`,
`agent-policy-retrieval`, `formal-position`, `salvage-transfer`,
`midlife-crisis-fact-finding`) and narrative beats.

---

## 4. Classify the situation and find authorities

```bash
# Phase 3A
python -m scripts.intake.situation_classify --facts case-facts.yaml
python -m scripts.intake.authorities_lookup \
  --situation insurance_dispute --jurisdiction MD
python -m scripts.intake.deadline_calc \
  --situation insurance_dispute --jurisdiction MD \
  --loss-date 2025-03-15
```

Expected outcome:
- Situation classified as `insurance_dispute` / subtype
  `auto_total_loss_bad_faith`.
- Authorities lookup returns `Maryland Insurance Administration` as
  the lead authority, with `CFPB` and `Maryland Attorney General
  Consumer Protection Division` as secondary. (Exact list is
  specified by `data/authorities.yaml`.)
- Deadline calculator reports the applicable statute-of-limitations
  window with a "verify with counsel" disclaimer.

---

## 5. Build the complaint packet

```bash
# Phase 1C
python -m scripts.packet.build \
  --manifest complaint_packet/packet-manifest.yaml
```

Expected outcome: `complaint_packet/complaint.pdf`, per-exhibit
paginated PDFs under `complaint_packet/exhibits/{A..G}/`, and the
governing-documents appendix under `complaint_packet/appendix/`.

Current state (Phase 2 hand-assembled): the directory layout is in
place; `packet-manifest.yaml` is the declarative spec; the actual
PDF rendering is `TODO-Phase-1C`.

---

## 6. Generate a provenance report on an exhibit

```bash
# Phase 1A
python -m scripts.provenance \
  --file complaint_packet/exhibits/C/ \
  --manifest .evidence-manifest.json
```

Expected outcome: forensic report listing the 20 source emails that
compose Exhibit C, each with its SHA-256 and xattr snapshot.

---

## 7. Publication-safety dry run

Before any derivative leaves the private repo, the publication-safety
scrubbers run with `--dry-run` to confirm detection:

```bash
# Phase 3C
python -m scripts.publish.pii_scrub --dry-run --root drafts/
python -m scripts.publish.pii_scrub --dry-run --root complaint_packet/
```

Expected outcome for the synthetic case: the scrubber flags the
invented claimant name, email, phone, policy number, and claim number
as "would redact" if a substitutions file were supplied. Since this
case is already synthetic, no actual scrub is run.

---

## 8. Render the case dashboard

```bash
# Phase 4B
python -m scripts.status.case_dashboard \
  --facts case-facts.yaml \
  --manifest .evidence-manifest.json \
  --packet complaint_packet/packet-manifest.yaml
```

Expected outcome: a Markdown status dashboard listing filed date,
MIA acknowledgement, days-since-last-insurer-response, SOL countdown,
and packet-build status.

---

## 9. Verify

```bash
pytest
```

The synthetic case is the fixture corpus for the test suite. A green
pytest run confirms end-to-end integrity.

---

## Pending items (cross-phase follow-ups)

- `TODO-Phase-1A` — pre-commit hook treatment of Markdown placeholder
  files under `evidence/photos/` and `evidence/valuation/`.
- `TODO-Phase-1C` — `scripts/packet/build.py` rendering complaint and
  exhibits to PDF from the Phase 2-authored manifest.
- `TODO-Phase-3A` — `data/authorities.yaml` population for MD
  insurance disputes.
- `TODO-Phase-5` — regenerate `MidAtlantic-Vehicle-Appraisers-valuation.md`
  as a reportlab PDF, photo placeholders as Pillow-rendered PNGs, and
  `mia-complaint.md` as a python-docx `.docx`, all stamped SYNTHETIC.

If this walkthrough trips on a tool that should work by its phase, file
an issue against that phase's plan.
