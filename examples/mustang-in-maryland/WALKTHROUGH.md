# Walkthrough — Mustang in Maryland

> **SYNTHETIC — NOT A REAL CASE.** Read `README.md` in this directory
> first. Every name, company, claim number, policy form, address, and
> dollar amount below is invented. The Maryland Insurance
> Administration is a real regulator; the case number `MIA-SYN-0000-0000`
> is fake.

This walkthrough is both a tutorial and the integration-test driver
for this toolkit. It exercises every published CLI end-to-end against
the synthetic Mustang case, so you can see what each tool produces
before pointing it at your own situation.

Expected time (reading + running): 30-45 minutes.

All commands below assume:

- You are in the **repo root**, not in `examples/mustang-in-maryland/`,
  unless otherwise noted. (The scripts are Python modules invoked via
  `python -m scripts.X`; they must be run from the directory
  containing the `scripts/` package.)
- You ran `pip install -e .` from the repo root.

```sh
cd /path/to/personal-advocacy-toolkit
```

---

## 0. Orient

```sh
cat examples/mustang-in-maryland/README.md
cat examples/mustang-in-maryland/CLAUDE.md
cat examples/mustang-in-maryland/case-facts.yaml
```

You should see:

- A two-paragraph situation summary describing Delia Vance's 1969
  Mustang, the salvage-transfer grievance, and the MIA forum.
- A structured fact sheet (`case-facts.yaml`) used by the
  letter-drafting, dashboard, and deadline tools.

---

## 1. Hash the evidence tree

```sh
python -m scripts.evidence_hash \
  --root examples/mustang-in-maryland/evidence \
  --manifest examples/mustang-in-maryland/.evidence-manifest.sha256
```

Expected output: `wrote <N> entries to .../.evidence-manifest.sha256`
where N is roughly 45 (20 .eml + 20 .json + 20 .txt + 3 policy .md +
1 valuation .md + photo placeholders + 1 emails README + 1 photos
README). The manifest is a plain text file, one line per file,
`<sha256>  <relative-path>`.

Verify against the tree:

```sh
python -m scripts.evidence_hash \
  --root examples/mustang-in-maryland/evidence \
  --manifest examples/mustang-in-maryland/.evidence-manifest.sha256 \
  --verify
```

Expected: `ok: N files verified against .../.evidence-manifest.sha256`.

---

## 2. Capture the provenance snapshot

```sh
python -m scripts.provenance_snapshot \
  --root examples/mustang-in-maryland/evidence \
  --snapshot-dir examples/mustang-in-maryland/provenance/snapshots
```

Expected output: `wrote <N> entries to .../provenance/snapshots/<UTC>.json`.

On macOS the snapshot captures `com.apple.metadata:kMDItemWhereFroms`
and `com.apple.quarantine` xattrs (empty for the synthetic files but
populated for real downloaded evidence). On Linux the xattr block is
usually empty.

---

## 3. Ingest correspondence (demonstration)

The 20 synthetic emails are already laid out across
`evidence/emails/{raw,structured,readable}/`. For demonstration, re-run
the JSON→TXT step from the structured layer (safe — it's just
regeneration):

```sh
python -m scripts.ingest.email_json_to_txt \
  examples/mustang-in-maryland/evidence/emails/structured \
  --out-dir /tmp/mustang-txt-demo
```

Expected output: `<json> -> <txt>` for each of the 20 messages,
landing in `/tmp/mustang-txt-demo/`. Compare to the shipped
`evidence/emails/readable/` directory; contents should match.

You can also re-validate the EML→JSON direction:

```sh
python -m scripts.ingest.email_eml_to_json \
  examples/mustang-in-maryland/evidence/emails/raw \
  --out-dir /tmp/mustang-json-demo
```

Expected: 20 JSON files in `/tmp/mustang-json-demo/`, each with
`source_sha256` matching the corresponding .eml file hash.

<!-- TODO: verify after dogfood pass -->
(If the existing structured/ JSON was generated differently, minor
diffs are possible; the `source_sha256` and body_text fields should
match exactly.)

---

## 4. Classify the situation and look up authorities

```sh
cat > /tmp/mustang-answers.yaml <<'YAML'
claimant_name: "Delia Vance"
jurisdiction_state: "MD"
counterparty_kind: "insurer"
situation: "Classic-car agreed-value policy, insurer deducted from payout and moved vehicle to salvage during active negotiation."
loss_date: "2025-03-15"
YAML

python -m scripts.intake.situation_classify \
  --answers /tmp/mustang-answers.yaml \
  --out /tmp/mustang-intake.yaml
```

Expected: situation classified as `insurance_dispute` with matched
rules printed (`counterparty_kind=insurer`, plus keyword hits such
as `salvage`). Output file is a minimal `case-intake.yaml`.

```sh
python -m scripts.intake.authorities_lookup \
  --situation insurance_dispute --jurisdiction MD
```

Expected: Maryland Insurance Administration listed as the
state-scope authority, plus CFPB and FTC ReportFraud under federal
scope. Every entry carries a `status` (populated / stub) and the
global disclaimer banner.

```sh
python -m scripts.intake.deadline_calc \
  --situation insurance_dispute --jurisdiction MD \
  --loss-date 2025-03-15 \
  --notice-of-loss 2025-03-16 \
  --denial-date 2025-05-09 \
  --last-act 2025-06-24
```

Expected: one deadline entry per rule in `data/deadlines.yaml` for
`(MD, insurance_dispute)`, each tagged `-- VERIFY WITH COUNSEL`.

---

## 5. Build the complaint packet

```sh
python -m scripts.packet.build \
  examples/mustang-in-maryland/complaint_packet/packet-manifest.yaml \
  -v
```

Expected output under
`examples/mustang-in-maryland/complaint_packet/`:

- `mustang-in-maryland-mia-mia-packet.pdf` — merged packet.
- `exhibit-A-*.pdf` through `exhibit-F-*.pdf` — per-exhibit standalones.
- `appendix-cim-policy-reference.pdf` — compiled governing-documents
  reference with COMPILED REFERENCE watermark on every page.

The merged packet starts with a cover page addressed to the
Maryland Insurance Administration, followed by the complaint
narrative, followed by Exhibits A-F with separator sheets, followed
by the compiled-reference appendix.

Current state (Phase 2): the files listed above already exist in the
directory (hand-assembled during Phase 2). Running the builder
regenerates them. If the builder output matches the shipped files,
the packet round-trips cleanly.

<!-- TODO: verify after dogfood pass -->
(Confirm libreoffice/soffice is installed if any exhibit source is
`.docx`. The Mustang synthetic case currently uses `.md` and `.pdf`
sources, so reportlab + pypdf should suffice.)

---

## 6. Generate a unified provenance report

```sh
python -m scripts.provenance \
  --manifest examples/mustang-in-maryland/.evidence-manifest.sha256 \
  --snapshot-dir examples/mustang-in-maryland/provenance/snapshots \
  --out examples/mustang-in-maryland/provenance/report.json \
  --repo-root .
```

Expected output: `wrote provenance report (N files) to
.../provenance/report.json`.

The report joins:

- SHA-256 from the manifest.
- size / mtime / xattrs from the most recent snapshot.
- git `first` and `last_touched` commit for each file (if the
  workspace is a git repo).
- pipeline metadata sidecars (`<file>.meta.json`) where present.

This is the document handed to an attorney or regulator alongside
the packet. See
[`docs/concepts/chain-of-custody.md`](../../docs/concepts/chain-of-custody.md)
for what a reviewer looks for.

---

## 7. Draft a letter from case facts

```sh
python -m scripts.letters.draft \
  --kind demand \
  --intake examples/mustang-in-maryland/case-facts.yaml \
  --out /tmp/mustang-demand-letter.docx
```

Expected: a `.docx` demand letter at `/tmp/mustang-demand-letter.docx`
rendered from `templates/letter-templates/demand.docx.j2`, with the
sender (Delia Vance) and recipient (Chesapeake Indemnity Mutual)
pulled from `case-facts.yaml`. Disclaimer footer auto-appended.

Try the other kinds:

```sh
python -m scripts.letters.draft --kind foia         --intake examples/mustang-in-maryland/case-facts.yaml --out /tmp/mustang-foia.docx
python -m scripts.letters.draft --kind preservation --intake examples/mustang-in-maryland/case-facts.yaml --out /tmp/mustang-preservation.docx
python -m scripts.letters.draft --kind withdrawal   --intake examples/mustang-in-maryland/case-facts.yaml --out /tmp/mustang-withdrawal.docx
python -m scripts.letters.draft --kind cease-desist --intake examples/mustang-in-maryland/case-facts.yaml --out /tmp/mustang-cease-desist.docx
```

FOIA auto-targets the authority from `data/authorities.yaml` (MIA
for MD insurance_dispute). Preservation / demand / withdrawal /
cease-desist default to the counterparty (Chesapeake Indemnity
Mutual).

---

## 8. Render the case dashboard

```sh
python -m scripts.status.case_dashboard \
  --intake examples/mustang-in-maryland/case-facts.yaml \
  --manifest examples/mustang-in-maryland/complaint_packet/packet-manifest.yaml \
  --packet-dir examples/mustang-in-maryland/complaint_packet/
```

<!-- TODO: verify after dogfood pass -->
The dashboard's `--manifest` is an evidence-manifest YAML with an
`entries:` list (kind per entry), not the SHA-256 manifest from
Step 1. For the Mustang case we don't ship a standalone
`evidence-manifest.yaml` yet — the command above points `--manifest`
at the packet manifest as a placeholder, which loads cleanly but
produces zero evidence-count rows. A proper evidence-manifest.yaml
(or running `correspondence_manifest.py` first) would populate the
Evidence section.

Expected output: a Markdown dashboard to stdout containing:

- Header (caption: "Mustang in Maryland", situation:
  insurance_dispute, jurisdiction: MD, loss date: 2025-03-15,
  SYNTHETIC flag).
- Evidence source-type table (from manifest entries).
- Deadlines table with `[VERIFY WITH COUNSEL]` tags.
- Packet validation status.
- Done / Pending checklist.

Write to a file instead of stdout with `--out`.

---

## 9. Publication-safety dry run

The Mustang case is already synthetic, so no actual scrubbing is
needed — but we demonstrate the detection pass:

```sh
cat > /tmp/mustang-subs.yaml <<'YAML'
substitutions:
  "Delia Vance":                     "Jane Doe"
  "Chesapeake Indemnity Mutual":     "Example Indemnity Mutual"
policy_number_patterns:
  - "CIM-[A-Z]+-\\d{4}"
extra_banned:
  - "414 Aigburth Vale"
YAML

python -m scripts.publish.pii_scrub \
  --root examples/mustang-in-maryland/drafts \
  --substitutions /tmp/mustang-subs.yaml \
  --report /tmp/mustang-scrub-dryrun.json
```

Expected output: `dry-run: <N> changes across <M> files; report ->
/tmp/mustang-scrub-dryrun.json`. The report lists every match the
scrubber *would* make (path, line, detector, replacement, SHA-256
of the original) without modifying any file.

The scrubber would refuse to run against `evidence/` — try it to see
the safety rail:

```sh
python -m scripts.publish.pii_scrub \
  --root examples/mustang-in-maryland/evidence \
  --substitutions /tmp/mustang-subs.yaml
# Expected: "refused: refusing to scrub under an 'evidence/' path" and exit 2
```

---

## 10. Verify via tests

```sh
pytest
```

Expected: all 130 tests pass. The synthetic case is the fixture
corpus for the test suite; a green run confirms end-to-end integrity.

---

## What each step produces (summary)

| Step | Tool                            | Output                                                      |
|------|---------------------------------|-------------------------------------------------------------|
|  1   | `evidence_hash`                 | `.evidence-manifest.sha256`                                 |
|  2   | `provenance_snapshot`           | `provenance/snapshots/<UTC>.json`                           |
|  3   | `ingest.email_*`                | three-layer email corpus                                    |
|  4   | `intake.*`                      | classification + authorities + deadlines                    |
|  5   | `packet.build`                  | merged packet PDF + exhibit PDFs + appendix PDF             |
|  6   | `provenance`                    | unified provenance report (JSON)                            |
|  7   | `letters.draft`                 | .docx letters per kind                                      |
|  8   | `status.case_dashboard`         | Markdown dashboard                                          |
|  9   | `publish.pii_scrub --dry-run`   | sidecar JSON report (no file changes)                       |
| 10   | `pytest`                        | green test suite                                            |

---

## Known rough edges

- Several commands in this walkthrough are flagged
  `<!-- TODO: verify after dogfood pass -->`. The parent orchestrator
  will fix these as part of the Phase 5 verification pass.
- The dashboard's expected `--manifest` input is an evidence-
  manifest.yaml (list of entries) distinct from the SHA-256 manifest
  produced by `evidence_hash`. A dedicated evidence-manifest for the
  Mustang case is not yet generated; Step 8 uses the packet manifest
  as a loadable-but-empty placeholder.
- `build.py` for `.docx` exhibit sources requires `soffice` or
  `libreoffice` on PATH. The Mustang case currently uses `.md` and
  `.pdf` sources only, so this doesn't trip.

File an issue for any command that trips on your environment.
