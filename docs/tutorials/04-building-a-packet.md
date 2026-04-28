# Tutorial 04: Building a packet

> **Reference material, not legal advice.** The packet tooling
> assembles documents. What goes in those documents is your decision
> — ideally with counsel review.

By the end of this tutorial, you'll have a single merged PDF (the
"packet") plus per-exhibit standalone PDFs, built from a declarative
`packet-manifest.yaml`. No Python or shell knowledge required to
rebuild it — once the manifest is written, `build.py` handles the
rest.

Running example: the
[`Maryland-Mustang`](../../examples/maryland-mustang/) synthetic
case, which ships a complete `packet-manifest.yaml` driving a
7-exhibit complaint to the Maryland Insurance Administration.

```sh
cd examples/maryland-mustang
```

## What a packet is

A packet is the document set you file with a regulator, send to an
attorney, or hand to a journalist:

1. **Cover page** — to/from/re header naming the authority,
   complainant, and respondent.
2. **Complaint narrative** — your story, in lawyer mode. See
   [`docs/concepts/tone-modes.md`](../concepts/tone-modes.md).
3. **Exhibits** — labeled A, B, C, ..., each with a separator sheet
   describing what it proves.
4. **Reference appendix** (optional) — the counterparty's governing
   documents (policy, contract, TOS, handbook) compiled into a
   single reference with a "not the official filing" watermark.

The toolkit produces:

- A single merged PDF named `<packet-name>-<authority-code>-packet.pdf`.
- Per-exhibit standalone PDFs for regulators that want per-exhibit
  uploads.
- The reference appendices as standalone compiled-reference PDFs.

## The packet-manifest.yaml

The manifest declares everything the builder needs — authority,
complainant, respondent, complaint source, exhibit list, reference
appendices, output directory. No authority-, case-, or
jurisdiction-specific code lives in `build.py`; it all comes from
the manifest.

Schema:
[`templates/packet-manifests/schema.yaml`](../../templates/packet-manifests/schema.yaml)
(heavily commented prototype).

Example (abbreviated from Mustang's):

```yaml
schema_version: "1.0"

packet:
  name: "maryland-mustang-mia"

  authority:
    name: "Maryland Insurance Administration"
    short_code: "MIA"
    mailing_address: |
      Maryland Insurance Administration
      Consumer Complaints & Investigation
      200 St. Paul Place, Suite 2700
      Baltimore, MD 21202
    intake_url: "https://insurance.maryland.gov/Consumer/Pages/FileAComplaint.aspx"

  complainant:
    name: "Sally Ridesdale"
    mailing_address: |
      Sally Ridesdale
      Towson, MD 21204
    email: "sally.ridesdale@example.invalid"

  respondent:
    name: "Chesapeake Indemnity Mutual"
    role: "Insurer (fictional)"
    reference_number: "CIM-CLS-0000-0000"

  complaint:
    source: "../drafts/mia-complaint.md"
    title: "Consumer Complaint Narrative — Sally Ridesdale v. Chesapeake Indemnity Mutual"

  output_dir: "."

  exhibits:
    - label: "A"
      title: "Full policy form set"
      description: "CIM's three governing forms in effect at loss."
      sources:
        - "../evidence/policy/CIM-VEH-2023.md"
        - "../evidence/policy/CIM-AV-ENDT-2023.md"
        - "../evidence/policy/CIM-SALV-2023.md"

    # ... B through F ...

  reference_appendices:
    - name: "cim-policy-reference"
      title: "Chesapeake Indemnity Mutual — Governing Documents"
      sources:
        - "../evidence/policy/CIM-VEH-2023.md"
        - "../evidence/policy/CIM-AV-ENDT-2023.md"
        - "../evidence/policy/CIM-SALV-2023.md"
      note: |
        Reproduced from the policy form set as retrieved from the
        producing agency on 2025-04-21.
```

Source paths are resolved relative to the manifest file. Supported
input formats per exhibit:

- `.pdf` — included as-is.
- `.docx` — compiled to PDF via soffice/libreoffice (if installed).
- `.txt` / `.md` — rendered to PDF via reportlab.
- `.png` / `.jpg` — wrapped in a PDF page.

Each exhibit can use either `source:` (one file) or `sources:` (list,
concatenated in order).

## Write the complaint narrative

Lawyer-mode writing. See [`tone-modes.md`](../concepts/tone-modes.md).

For the synthetic case, the narrative lives at
`drafts/mia-complaint.md`. Key structural elements:

1. **Salutation and re-line.**
2. **Statement of facts** — dated, sourced to exhibits.
3. **Core grievance** — the cleanest, best-documented issue, not
   necessarily the largest dollar amount. For Mustang it's the
   salvage-transfer-during-negotiation, not the valuation dispute.
4. **Supporting issues** — in descending order of strength.
5. **Relief requested** — specific, itemized.
6. **Exhibits referenced** — a labeled list matching the manifest.
7. **SYNTHETIC / disclosure footer** (for the synthetic case; for
   your own case, the signature block).

## Build the packet

```sh
uv run python -m scripts.packet.build complaint_packet/packet-manifest.yaml -v
```

Or via the shell wrapper (same thing; doesn't require you to be in
the repo root):

```sh
bash scripts/packet/build_pdf.sh complaint_packet/packet-manifest.yaml -v
```

Expected outputs under `complaint_packet/`:

- `maryland-mustang-mia-mia-packet.pdf` — the merged packet.
- `exhibit-A-full-policy-form-set.pdf`, `exhibit-B-...`, ... — per-
  exhibit standalones.
- `appendix-cim-policy-reference.pdf` — the compiled governing-
  documents reference (with COMPILED REFERENCE watermark on every
  page).

The cover page names the authority, complainant, and respondent.
Each exhibit gets a separator sheet with label, title, description,
and (if set) date.

## Validate the packet before filing

Re-hash evidence after any changes:

```sh
uv run python -m scripts.evidence_hash --root evidence --manifest .evidence-manifest.sha256 --verify
```

Spot-check the packet:

1. Open the merged PDF. Confirm the cover page is addressed correctly.
2. Confirm exhibit labels A, B, C, ... appear in order.
3. Confirm the reference-appendix cover explicitly disclaims that it
   is "a compiled reference, not the officially-filed document."
4. Confirm every page of the reference appendix carries the
   COMPILED REFERENCE watermark.

## Run a provenance report on an exhibit

Show where every file in Exhibit B came from:

```sh
uv run python -m scripts.provenance \
  --manifest .evidence-manifest.sha256 \
  --out provenance/report.json
```

<!-- TODO: verify after dogfood pass -->
The provenance tool emits a report over the whole manifest, not a
per-exhibit slice. Filter the resulting JSON to the exhibit's paths
if you want a per-exhibit view. This is the document you hand to an
attorney or regulator alongside the packet.

See [`chain-of-custody.md`](../concepts/chain-of-custody.md) for what
a reviewer looks for in the provenance report.

## Drafting letters around the packet

Demand letter, FOIA request, preservation letter, withdrawal-of-
consent, cease-and-desist — all template-driven from the same
`case-facts.yaml`:

```sh
uv run python -m scripts.letters.draft \
  --kind demand \
  --intake case-facts.yaml \
  --out drafts/demand-letter.docx
```

Kinds: `demand | foia | preservation | withdrawal | cease-desist`.

If the intake is missing a required field, the tool either prompts
(interactive), inserts a `[TODO: <field>]` placeholder (non-
interactive), or fails (with `--strict`).

## Where next

- [`05-going-public-safely.md`](05-going-public-safely.md) — if (and
  only if) you decide to publish a sanitized derivative.
- [`examples/maryland-mustang/WALKTHROUGH.md`](../../examples/maryland-mustang/WALKTHROUGH.md)
  — the full synthetic end-to-end run.
