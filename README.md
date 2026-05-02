# PAT: Personal Advocacy Toolkit

<p align="center">
  <img src="PAT-logo-3.png" alt="PAT Logo" width="400">
</p>

<p align="center">
  <em>An AI toolkit that helps non-technical people in a dispute hand attorneys, regulators, and journalists something they can actually act on.</em>
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/License-Apache_2.0-blue.svg"></a>
  <a href="https://github.com/EvanOchsner/personal-advocacy-toolkit/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/EvanOchsner/personal-advocacy-toolkit/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue.svg">
  <img alt="Status: pre-1.0" src="https://img.shields.io/badge/status-pre--1.0-orange.svg">
</p>

<!--
TODO before launch: replace the placeholder below with a real screenshot of the
case-map app (scripts/app) running locally — three-column entity graph plus
timeline drilldown is the highest-leverage visual on this page.
Suggested path: docs/img/case-map-app.png  (~1600px wide, PNG).
-->
<p align="center">
  <img src="docs/img/case-map-app.png" alt="Case-map app: entity graph and timeline" width="900">
</p>

## Thesis

You have a situation — a bad-faith insurance claim, a surprise medical bill, a harassment campaign, a landlord trying to retaliate, a debt collector who won't follow the rules, a scam that took your money. There are people and offices whose job it is to help: state regulators, consumer-protection advocates, attorneys, journalists. They can only help you if you hand them something they can act on.

PAT does the legwork — evidence intake with forensic integrity, situation-specific reference material, drafting tools with anti-hallucination guard rails, and a publication-safety pipeline — so the person who helps you can spend their time on your case instead of cleaning up your file.

> **Do the legwork so whoever helps you can actually help you.**

## What's in the box

### 1. Auditable evidence curation

Collect, process and organize all digital evidence (emails, texts, call records, photos, documents) related to your case.
Enter your evidence files in the project to prove they have not been tampered with post check-in.
Maintain original, human-friendly and machine-friendly versions of your documents with reproducible, auditable, customizable scripts.
Creates a forensic audit trail a regulator or attorney can verify without trusting the author:

- **Hash manifest** ([`scripts/evidence_hash.py`](scripts/evidence_hash.py)) — SHA-256 of every file, human-readable.
- **Pre-commit immutability hook** ([`scripts/hooks/pre_commit.py`](scripts/hooks/pre_commit.py)) — refuses git commits that modify or delete files under the protected `evidence/` path.
- **xattr / provenance snapshots** ([`scripts/provenance_snapshot.py`](scripts/provenance_snapshot.py)) — captures `kMDItemWhereFroms` download URLs and quarantine timestamps that git does not track.
- **Unified provenance report** ([`scripts/provenance.py`](scripts/provenance.py)) — joins the manifest, xattr snapshot, git history, and pipeline-metadata sidecars into a single JSON document a reviewer can skim.
- **Layered extraction cascade** ([`scripts/extraction/`](scripts/extraction/)) — converts PDFs, HTML, emails, and images into searchable plaintext via a tiered fallback (stdlib → Docling / Trafilatura → local VLM → Tesseract backstop) with garble detection per page. Every extracted document gets a per-source reproducibility script under `<case>/extraction/scripts/extract_<source_id>.py` so any reviewer can re-run the exact recipe (settings, overrides, provider) and assert byte-identical output.
- **Single-format ingest pipelines** ([`scripts/ingest/`](scripts/ingest/)) — SMS / iMessage exports, voicemail metadata, medical EOBs, screenshots of live URLs, mailbox splits. These wrap format-specific oddities the cascade isn't responsible for.

### 2. Analysis with anti-hallucination guard rails

The drafting and review tools are designed to ground the analysis in the facts of the case and the exact text of the relevant laws, terms and regulations.

- **Networkless subagents.** The interactive comment workflow ([`.claude/skills/docx-comment-roundtrip/`](.claude/skills/docx-comment-roundtrip/)) spawns specialized subagents with file-read tools only — **no network access** — and instructs them to fact-check, analyze, and propose text **using only project materials**. Replies that contain unauthorized URLs are rejected automatically.
- **Project-materials-only grounding.** Every assertion the toolkit emits is expected to cite a file under your case folder. If the agent needs information that isn't there, the workflow stops and helps you to track it down, vet it, and ingest it as a tracked document.
- **Trusted reference acquisition** ([`.claude/skills/trusted-sources/`](.claude/skills/trusted-sources/), [`scripts/references/`](scripts/references/)) — pulls authoritative text (statutes, regulations, official policies, terms of service) into `<case>/references/` via three independent paths (user-supplied / project-known trusted source / constrained allowlist fetch), cross-checks them, and assesses user-supplied copies for completeness. Every doc is sha256-tracked with a sidecar that carries the verbatim disclaimer. See [`docs/concepts/trusted-sources.md`](docs/concepts/trusted-sources.md).
- **Mandatory verify-with-counsel disclaimers** on every tool that emits a date, an authority, or a statute cite.

### 3. Document and Packet Creation

- **Packet assembler** ([`scripts/packet/`](scripts/packet/)) — Create an organized packets of evidence, filings attachments, etc. to hand off to an attorney or agency. Driven by a declarative `packet-manifest.yaml` (schema at [`templates/packet-manifests/schema.yaml`](templates/packet-manifests/schema.yaml)).
- **Correspondence drafting** ([`scripts/letters/`](scripts/letters/), [`templates/`](templates/)) — letters, complaints, filings, briefs.
- **Publication-safety scrubbers with mandatory post-checks** ([`scripts/publish/`](scripts/publish/)) — Redact sensitive information from case materials before sharing publicly. Designed to prevent creation of a "redacted" PDF whose text layer still contains the redacted content. Every scrubber ships with a verification pass.
- **Case-map and timeline dashboard** ([`scripts/app/`](scripts/app/)) — local-only browser UI rendering a three-column entity graph (self/allies, neutrals, adversaries) and a chronological event timeline, with drilldown to every cited document. **Binds 127.0.0.1, strict CSP, no external resources** — the local-first claim is enforced by the server, not just the policy.

## Get started

Run with the AI assistant of your choice, or run scripts yourself. Both leverage the same underlying tools.

- **A — Bring your own assistant (BYOA).** An AI walks you through the workflow conversationally and runs the commands on your behalf. Pick this if you'd rather describe your situation than learn a CLI.
- **B — Run the CLI yourself.** Follow the README and tutorials; invoke the scripts directly. Pick this if you'd rather see exactly what each tool does, or if you want deterministic / scriptable / reproducible runs.

Both paths use the same artifacts (skills, data tables, templates, CLI scripts) and produce the same outputs — they're just different drivers. You can mix freely (e.g., let the assistant drive intake and authorities, then run the packet build and publication-safety scrubbers yourself).

Prerequisite for both paths: [uv](https://docs.astral.sh/uv/getting-started/installation/) (e.g. `curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`).

```sh
git clone https://github.com/EvanOchsner/personal-advocacy-toolkit.git
cd personal-advocacy-toolkit
uv sync
```

### A — Bring your own assistant (BYOA)

The toolkit ships with a skill bundle under [`.claude/skills/`](.claude/skills/) that turns any compatible AI assistant into a workflow guide. The orchestrator skill (`pat-workflow`) interviews you, runs the CLI commands on your behalf, validates the outputs, and walks you through each phase end-to-end.

**[Claude Code](https://docs.claude.com/claude-code/quickstart).** Auto-discovers `.claude/skills/`. From the repo:

```sh
claude
```

Then describe your situation in natural language and ask it to use the project skills to setup your case. The orchestrator routes through the workflow phases (intake → authorities → trusted reference docs → deadlines → evidence → drafting → packet → publication safety).

**AI harnesses with shell access** — Cursor, Windsurf, Aider, Continue, Cline, OpenCode — work too. The skill content is plain markdown plus YAML frontmatter; point your harness at `.claude/skills/` (typically a one-line config change).

**No-shell assistants** — claude.ai web chat, NotebookLM, ChatGPT, Gemini — can read the skills as guidance and walk you through the workflow conversationally, but they can't run the CLI for you. Roughly equivalent to following the tutorials with a chatbot beside you.

Setup recipes for your weapon of choice can be found here: [`docs/byoa/README.md`](docs/byoa/README.md).

### B — Run the CLI manually

The one-command demo against the fully synthetic Maryland Mustang example (nothing real is at stake):

```sh
# Copies the synthetic example and runs the full pipeline
# (hash, ingest, classify, authorities, deadlines, packet,
# letters, PII scrub).
uv run python -m scripts.demo
```

Or run individual tools against the in-repo example:

```sh
# Launch the local case-map app (127.0.0.1 only).
uv run python -m scripts.app --case examples/maryland-mustang

# Hash the evidence tree.
uv run python -m scripts.evidence_hash \
  --root examples/maryland-mustang/evidence \
  --manifest examples/maryland-mustang/.evidence-manifest.sha256

# Look up authorities for a MD insurance dispute.
uv run python -m scripts.intake.authorities_lookup \
  --situation insurance_dispute --jurisdiction MD
```

For the step-by-step walkthrough, see [`examples/maryland-mustang/WALKTHROUGH.md`](examples/maryland-mustang/WALKTHROUGH.md).

### Start your own case (either path)

```sh
uv run python -m scripts.init_case --output ~/cases/my-case
```

This creates the full directory structure, copies starter templates, and runs an interactive intake questionnaire. From there, either point your assistant at the new workspace (BYOA) or follow the tutorials yourself (CLI). See [`docs/tutorials/01-setting-up-your-case.md`](docs/tutorials/01-setting-up-your-case.md) for details.

## Situations it fits

The initial playbooks cover:

- Insurance bad-faith / claim handling
- Medical balance-billing and surprise bills
- Consumer scams (romance, crypto, impersonation, fake invoices)
- Harassment and cyberbullying
- Landlord retaliation / habitability disputes
- Debt-collector abuse (FDCPA)
- Employment retaliation

The framework generalizes further. See [`docs/playbooks/`](docs/playbooks/) for each situation's reference material.

## Repository layout

```
scripts/       CLI tools (demo, init_case, evidence_hash, provenance,
               ingest, intake, packet, publish, letters, status,
               hooks, app)
.claude/skills/  Portable assistant skills (case intake, situation
                 triage, provenance review, packet building, PII scrub,
                 tone-modes, going-public checks, docx-comment-roundtrip,
                 plus the pat-workflow orchestrator); auto-discovered
                 by Claude Code, readable by any shell-having agent
data/          Community-maintainable reference data (authorities by
               jurisdiction, deadline tables, situation types)
templates/     Case-intake, letter, and packet-manifest templates
docs/          Concepts, playbooks, tutorials
examples/      Fully synthetic worked examples (maryland-mustang)
tests/         pytest suite; fixtures derived from the synthetic case
```

## Install

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first, then:

```sh
uv sync                                 # core runtime (tier-0 extraction works out of the box)
uv sync --extra dev                     # pytest + ruff
uv sync --extra publish                 # Pillow, pypdf, reportlab for scrubbers
uv sync --extra synthetic-case          # Pillow, python-docx for regenerating the example
uv sync --extra extraction              # Docling, Trafilatura, Playwright, Tesseract for tier-1+
uv sync --extra extraction-vlm          # olmOCR — local 7B VLM for the hardest PDFs
uv sync --extra extraction-cloud-openai # OpenAI vision provider (cloud — privacy trade-off)
uv sync --extra llm                     # Anthropic SDK (also enables the `claude` VLM provider)
```

Combine extras with multiple `--extra` flags. Every CLI invocation in the docs runs as `uv run python -m scripts...`; `uv run` resolves the project-managed virtualenv automatically, so there is nothing to activate.

System binaries (graceful fallback when missing — extraction prints a hint):

- `tesseract` — `brew install tesseract`
- `chromium` — after `uv sync --extra extraction`, run `playwright install chromium`
- `poppler` (provides `pdftoppm` for `pdf2image`) — `brew install poppler`
- `ocrmypdf` — `brew install ocrmypdf` (used by tier-0 PDF for image-only inputs)
- `git-filter-repo` (for history sanitizing) — `brew install git-filter-repo`

## Extraction

The `document-extraction` skill (and `python -m scripts.extraction`) runs a **layered cascade** that converts adversary-supplied PDFs, HTML, emails, and images into searchable plaintext — with **garble detection** at each tier so the cheap path can't silently lie about what's in a bezier-glyph PDF or a JS-rendered page.

Tier ladder:

| Tier | PDF                    | HTML                       | Image     | Email |
|------|------------------------|----------------------------|-----------|-------|
| 0    | `pypdf` + `ocrmypdf`   | stdlib `html.parser`       | —         | stdlib `email` |
| 1    | Docling                | Trafilatura                | Tesseract | (single tier) |
| 2    | VLM provider (per page)| Playwright + Trafilatura   | —         | — |
| 3    | Tesseract backstop     | —                          | —         | — |

Tier 2 routes garbled PDF pages to a VLM provider. **Pick providers in this recommended order:**

1. **`tesseract`** — local OCR, no GPU, no network. **Default.** Adequate for most documents.
2. **`olmocr`** — local 7B VLM, GPU recommended. **When tesseract isn't enough AND privacy matters.** Stays on the user's machine.
3. **`claude` / `openai` / `http`** — cloud VLMs. **Last resort.** Powerful but page images leave the machine; the cascade prompts for per-case consent and records the answer in `<case>/extraction/vlm-consent.yaml`. The `going-public` skill reads that file before publication so externally-processed pages can be re-extracted locally for the public copy.

**Privacy callout.** Raw evidence pages frequently contain SSNs, medical info, account numbers, and other sensitive content. PII scrubbing runs *after* extraction by design. So if you point the cascade at a cloud VLM, the unscrubbed page images go to that vendor before any redaction. Default to local providers; only opt into cloud VLMs when you've consciously accepted the trade-off.

Every extraction writes a per-source reproducibility script under `<case>/extraction/scripts/extract_<source_id>.py` that re-runs the cascade with the recorded recipe and asserts byte-identical output. A regulator or attorney's expert can run it cold to verify the chain.

## What this isn't

- **Not legal advice.** Nothing here tells you what to argue or predicts an outcome in your specific case. Every tool that emits a date, an authority, or a statute cite does so with a "verify with counsel" disclaimer.
- **Not a substitute for counsel.** When you need a lawyer, hire one. The toolkit makes you a better client, not your own attorney.
- **Not for criminal-matter evidence collection.** The chain-of-custody model here is designed for civil and regulatory contexts. Criminal evidentiary standards are stricter and should involve law enforcement.
- **Not a tool for mass-producing slop.** These tools are intended to help people acting in good faith protect themselves from bad actors by understanding and demonstrating the facts of the case and rules in play. Using them as intended means meticulously constructing the facts and arguments for *your* specific dispute. The goal is to produce the antithesis of careless, vibe-lawyered AI slop.

## Core principles

- Understand and document the facts of the case. If you are acting in good faith and the other party is not, the facts are on your side and you need to document them in a thorough, airtight manner.
- Store everything you believe to be "ground truth" inside the case folder. **You** are the steward of information pulled inside the project. The assistant and workflow can help you locate, process and understand these documents, but ultimately you must use your own judgement to ensure the right source materials land in the case folder.
- Gather and track all information within the project. Everything is machine-searchable (and human grep-able). Understand the full picture and how everything fits together.
- Every assertion, claim, and analysis must be grounded in materials in the case folder. If additional information is required, you track it down, vet it, and ingest it as a tracked, searchable document before relying on it.

## Why this might interest legal, academic or civil groups

If you work on legal aid, civic tech, AI safety / alignment, legal informatics, or HCI:

- **Reproducible audit trails on synthetic data.** The fully synthetic [Maryland-Mustang](examples/maryland-mustang/) example exercises every pipeline end-to-end with no real PII at stake — a citable artifact for legal-tech, HCI, or AI-safety coursework and clinics.
- **Networkless-subagent design as a concrete anti-hallucination pattern.** The "deny network, restrict to project files, reject replies with external URLs" architecture in [`.claude/skills/docx-comment-roundtrip/`](.claude/skills/docx-comment-roundtrip/) is implementable in any agent harness and is, to our knowledge, an underexplored pattern in the published literature on LLM grounding.
- **Plausible upstream feed into Document Assembly Line / Docassemble.** DAL handles **interview → document**; PAT handles the **pre-filing evidence-organization step that DAL assumes has already happened**. The two compose cleanly.
- **Apache-2.0 with explicit patent grant.** Permissive enough for derivative academic work and downstream legal-aid integration without license friction.
- **CI across Ubuntu / macOS / Windows on every push** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)): pytest suite, ruff lint, CLI smoke tests, publication-safety post-checks. Fixtures derive from the synthetic case so the test suite doubles as executable documentation.
- **Collaborations welcome** — case studies, evaluation work, integration with existing legal-aid platforms, formal review of the chain-of-custody model. See [Citation and contact](#citation-and-contact) below.

### Concept docs

`docs/concepts/` is where the toolkit's design philosophy lives:

- [`evidence-integrity.md`](docs/concepts/evidence-integrity.md) — why hashes, xattrs, and the immutability hook matter; how a regulator or attorney verifies an evidence tree without trusting the author.
- [`chain-of-custody.md`](docs/concepts/chain-of-custody.md) — the four sources a reviewer joins (hash manifest, filesystem download metadata, git history, pipeline sidecars) into a per-file forensic story; cross-platform metadata coverage notes for macOS, Linux, and Windows.
- [`case-map-app.md`](docs/concepts/case-map-app.md) — local-only entity-graph + timeline UI; the airgap posture (127.0.0.1 binding, strict CSP, no external resources) and "paranoid mode" recipe for true network isolation.
- [`pii-and-publication.md`](docs/concepts/pii-and-publication.md) — the four-leakage model (text, DOCX metadata, image EXIF, git history) and the verification pass each scrubber ships.
- [`tone-modes.md`](docs/concepts/tone-modes.md) — lawyer mode vs casual mode; the read-aloud test; the "scripts as scaffolds, not oracles" rule.
- [`authorities-and-regulators.md`](docs/concepts/authorities-and-regulators.md) — the "who cares about this?" map: regulators, ombuds, state AGs, federal backstops, by jurisdiction and situation type.
- [`correspondence-manifest-schema.md`](docs/concepts/correspondence-manifest-schema.md) — the per-message metadata shape used to track exhibits, threads, and matched-rule provenance.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Good first contributions:

- Populate a jurisdiction in [`data/authorities.yaml`](data/authorities.yaml) or [`data/deadlines.yaml`](data/deadlines.yaml).
- Flesh out one of the stub playbooks under [`docs/playbooks/`](docs/playbooks/).
- Add a new ingest format (iMessage export, voicemail-metadata variant, additional medical EOB layouts) following the three-layer pattern in [`scripts/ingest/`](scripts/ingest/).

## License

Apache-2.0 — see [LICENSE](LICENSE). Permissive license with explicit patent grant, chosen to keep the toolkit integrable with legal-aid and civic-tech platforms without license friction.

## Citation and contact

<!--
TODO before launch: replace the placeholder citation below with a real
arXiv preprint reference once the writeup is posted, and fill in a real
contact route (email, project alias, or issue-tracker link).
-->

If you reference PAT in academic or journalistic work, please cite as:

```bibtex
@misc{ochsner2026pat,
  author       = {Ochsner, Evan},
  title        = {PAT: Personal Advocacy Toolkit},
  year         = {2026},
  howpublished = {\url{https://github.com/EvanOchsner/personal-advocacy-toolkit}},
  note         = {arXiv preprint forthcoming — TODO}
}
```

Press and academic inquiries welcome. Contact: **TBD** (will be filled in before public launch).
