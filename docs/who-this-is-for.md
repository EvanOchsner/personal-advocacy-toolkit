# Who this is for

## Primary audience

**Non-technical people organizing a fact-heavy dispute** so that a
regulator, advocate, journalist, or attorney can act on it
effectively.

You may have:

- Exchanged months of emails with an insurer, landlord, hospital
  billing office, debt collector, or employer and need to turn that
  sprawl into a coherent exhibit set.
- Downloaded PDFs and screenshots into a Downloads folder and are not
  sure which are still authentic and which have been edited.
- Been told by a regulator's intake form that you can upload a single
  PDF per "item" and you are not sure what should go into which item.
- Been told by an attorney, "send me what you have" and realized you
  don't have it in a form anyone can easily review.

You are not expected to understand git, SHA-256, YAML, Jinja, or the
Python ecosystem going in. The tutorials walk you through what each
tool does and why, and the skills under `.claude/skills/` are designed to be
invoked from a Claude Code session where you answer questions in plain
English.

What you will gain:

1. An **append-only, hash-verified evidence tree** that a third party
   can audit without trusting your word.
2. A **packet** — complaint narrative, labeled exhibits, reference
   appendices — assembled into a single PDF suitable for filing with a
   state regulator, an ombuds office, or counsel.
3. A **case dashboard** that surfaces deadlines, pending items, and the
   next concrete step.
4. **Publication-safety scrubbers** with mandatory post-checks so that
   if you decide to go public with a sanitized derivative, you do not
   accidentally leak PII through a PDF text layer, docx metadata, or
   EXIF data.

## Explicit non-goals

- **Not for becoming your own lawyer.** The toolkit makes you a better
  client to counsel — it does not replace counsel.
- **Not for skipping a lawyer when you need one.** Every tool that
  emits a date, an authority, or a legal-framework cite does so with a
  "verify with counsel" disclaimer. That disclaimer is load-bearing.
- **Not a pro-se litigation automator.** Use Document Assembly Line or
  Docassemble for that. This toolkit handles the evidence-organization
  step that those platforms generally assume has already happened.
- **Not for criminal-matter evidence.** The chain-of-custody model
  here is designed for civil and regulatory contexts. Criminal
  evidentiary standards are stricter and should involve law
  enforcement.
- **Not an encryption tool.** Evidence integrity and confidentiality
  are separate problems. The toolkit proves a file hasn't been changed
  since you collected it; it does not hide the file from prying eyes.
  If confidentiality matters, encrypt at the filesystem or repo level
  in addition to running this toolkit.

## Secondary audience

**Civic-legal-tech practitioners** evaluating the mechanics for
integration with their platforms:

- **Suffolk LIT Lab / Document Assembly Line.** The packet assembler
  is a plausible upstream feed into DAL. DAL handles interview →
  document; this toolkit handles raw-evidence → organized exhibits +
  provenance report.
- **LSC TIG grantees** building self-help tools for legal-aid clients.
  The three-layer ingest pipeline and the forensic-integrity model
  are reusable as library code.
- **United Policyholders** and similar consumer-advocacy groups who
  already coach claimants through complaint processes. The worked
  Maryland insurance playbook is the demonstration case; the template
  shape is usable for other states.
- **Legal-aid tech staff** who need a stable fixture corpus (the
  fully-synthetic Maryland-Mustang example) to build UX on top of.

See [`docs/concepts/evidence-integrity.md`](concepts/evidence-integrity.md)
for the full interop story and the four independently-verifiable
sources of chain-of-custody that make the toolkit trustworthy for
regulator and attorney handoff.

## Tertiary audience

The author's own portfolio. This repo is the generalized, publicly
shareable derivative of a private project built to fight a single
Maryland auto-insurance bad-faith dispute. Nothing real from that
project ships here; the `Maryland-Mustang` example is
fully-synthetic.
