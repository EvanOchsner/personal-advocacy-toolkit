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
- **Bulk ingest pipelines** ([`scripts/ingest/`](scripts/ingest/)) — emails (EML / mbox), SMS, voicemail metadata, screenshots, medical EOBs. PDFs and HTML get OCR / plaintext extraction so adversaries can't hide behind unsearchable formats. Every ingester lands originals plus a machine-searchable plaintext copy under the same audit trail.

### 2. Analysis with anti-hallucination guard rails

The drafting and review tools are designed to ground the analysis in the facts of the case and the exact text of the governing.

- **Networkless subagents.** The interactive comment workflow ([`.claude/skills/docx-comment-roundtrip/`](.claude/skills/docx-comment-roundtrip/)) spawns specialized subagents with file-read tools only — **no network access** — and instructs them to fact-check, analyze, and propose text **using only project materials**. Replies that contain unauthorized URLs are rejected automatically.
- **Project-materials-only grounding.** Every assertion the toolkit emits is expected to cite a file under your case folder. If the agent needs information that isn't there, the workflow stops and helps you to track it down, vet it, and ingest it as a tracked document.
- **Mandatory verify-with-counsel disclaimers** on every tool that emits a date, an authority, or a statute cite.

### 3. Output

- **Packet assembler** ([`scripts/packet/`](scripts/packet/)) — driven by a declarative `packet-manifest.yaml` (schema at [`templates/packet-manifests/schema.yaml`](templates/packet-manifests/schema.yaml)).
- **Correspondence drafting** ([`scripts/letters/`](scripts/letters/), [`templates/`](templates/)) — letters, complaints, filings, briefs.
- **Publication-safety scrubbers with mandatory post-checks** ([`scripts/publish/`](scripts/publish/)) — Redact sensitive information from case materials before sharing publicly. Designed to prevent creation of a "redacted" PDF whose text layer still contains the redacted content. Every scrubber ships with a verification pass.
- **Case-map and timeline dashboard** ([`scripts/app/`](scripts/app/)) — local-only browser UI rendering a three-column entity graph (self/allies, neutrals, adversaries) and a chronological event timeline, with drilldown to every cited document. **Binds 127.0.0.1, strict CSP, no external resources** — the local-first claim is enforced by the server, not just the policy.

## Why this might interest legal-aid and civic-tech orgs

If you are from Suffolk LIT Lab, United Policyholders, an LSC TIG grantee, or any civic-legal-tech group: the differentiator is **not** the letter templates or the packet PDF — those are table stakes. The differentiator is the forensic audit trail described above, which a regulator or attorney can verify without trusting the author.

The packet assembler is a plausible upstream feed into Document Assembly Line / Docassemble: DAL handles **interview → document**; PAT handles the **pre-filing evidence-organization step that DAL assumes has already happened**. The two compose cleanly; we'd love to talk about integration points.

Full write-up and interop notes: [`docs/concepts/evidence-integrity.md`](docs/concepts/evidence-integrity.md), [`docs/concepts/case-map-app.md`](docs/concepts/case-map-app.md), [`docs/concepts/chain-of-custody.md`](docs/concepts/chain-of-custody.md).

## Why this might interest academic and scholarly readers

- **Reproducible audit trails on synthetic data.** The fully synthetic [Maryland-Mustang](examples/maryland-mustang/) example exercises every pipeline end-to-end with no real PII at stake — a citable artifact for legal-tech, HCI, or AI-safety coursework and clinics.
- **Networkless-subagent design as a concrete anti-hallucination pattern.** The "deny network, restrict to project files, reject replies with external URLs" architecture in [`.claude/skills/docx-comment-roundtrip/`](.claude/skills/docx-comment-roundtrip/) is implementable in any agent harness and is, to our knowledge, an underexplored pattern in the published literature on LLM grounding.
- **Apache-2.0 with explicit patent grant.** Permissive enough for derivative academic work and downstream legal-aid integration without license friction.
- **CI on every push** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)): pytest suite, ruff lint, and CLI smoke tests. Fixtures derive from the synthetic case so the test suite doubles as executable documentation.
- **Collaborations welcome** — case studies, evaluation work, integration with existing legal-aid platforms, formal review of the chain-of-custody model. See [Citation and contact](#citation-and-contact) below.

## 60-second demo

Uses the fully synthetic Maryland-Mustang example. Nothing real is at stake.

Prerequisite: [uv](https://docs.astral.sh/uv/getting-started/installation/) (e.g. `curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`).

```sh
git clone https://github.com/EvanOchsner/personal-advocacy-toolkit.git
cd personal-advocacy-toolkit
uv sync

# One-command demo: copies the synthetic example and runs the full
# pipeline (hash, ingest, classify, authorities, deadlines, packet,
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

To start your own case:

```sh
uv run python -m scripts.init_case --output ~/cases/my-case
```

This creates the full directory structure, copies starter templates, and runs an interactive intake questionnaire. See [`docs/tutorials/01-setting-up-your-case.md`](docs/tutorials/01-setting-up-your-case.md) for details.

## BYOA — Bring your own assistant

If you'd rather have an AI walk you through this workflow than run the commands yourself, the toolkit ships with a skill bundle under [`.claude/skills/`](.claude/skills/) that does exactly that. The assistant interviews you, runs the CLI commands on your behalf, validates the outputs, and walks you through each phase end-to-end.

**Recommended: [Claude Code](https://docs.claude.com/claude-code/quickstart).** Auto-discovers `.claude/skills/`. Just `cd` into the repo and run `claude` — no configuration. The orchestrator skill (`pat-workflow`) fires when you describe a dispute, and routes through the eight phases (intake → authorities → deadlines → evidence → drafting → packet → publication safety).

**Other shell-having harnesses** — Cursor, Windsurf, Aider, Continue, Cline, OpenCode, plus homebrew local-model rigs — work too. The skill content is plain markdown plus YAML frontmatter; point your harness at `.claude/skills/` (one-line config in most of them).

**No-shell surfaces** — claude.ai web chat, NotebookLM, ChatGPT, Gemini — can read the skills as guidance and walk you through the workflow conversationally, but they can't run the CLI for you. Roughly equivalent to following the tutorials with a chatbot beside you. For a case heading to a regulator filing or litigation, the forensic chain-of-custody steps need a real CLI run; consider running those locally even if the rest is chat-only.

Per-harness setup recipes: [`docs/byoa/README.md`](docs/byoa/README.md).

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
uv sync                                 # core runtime
uv sync --extra dev                     # pytest + ruff
uv sync --extra publish                 # Pillow, pypdf, reportlab for scrubbers
uv sync --extra synthetic-case          # Pillow, python-docx for regenerating the example
```

Combine extras with multiple `--extra` flags. Every CLI invocation in the docs runs as `uv run python -m scripts...`; `uv run` resolves the project-managed virtualenv automatically, so there is nothing to activate.

`git filter-repo` (for history sanitizing) is a separate binary; install via your package manager (`brew install git-filter-repo` on macOS).

## What this isn't

- **Not legal advice.** Nothing here tells you what to argue or predicts an outcome in your specific case. Every tool that emits a date, an authority, or a statute cite does so with a "verify with counsel" disclaimer.
- **Not a substitute for counsel.** When you need a lawyer, hire one. The toolkit makes you a better client, not your own attorney.
- **Not for criminal-matter evidence collection.** The chain-of-custody model here is designed for civil and regulatory contexts. Criminal evidentiary standards are stricter and should involve law enforcement.
- **Not a tool for mass-producing slop.** These tools are intended to help people acting in good faith protect themselves from bad actors by understanding and demonstrating the facts of the case and rules in play. Using them as intended means meticulously constructing the facts and arguments for *your* specific dispute. The goal is to produce the antithesis of careless, vibe-lawyered AI slop.

## Core principles

- Understand and document the facts of the case. If you are acting in good faith and the other party is not, the facts are on your side and you need to document them in a thorough, airtight manner.
- Every dispute has a case folder that holds information you believe to be the ground truth in the dispute. **You** are the steward of information pulled inside the project. The agent and other resources help you find the right authorities, laws, and policies, but ultimately you must use your own judgement to ensure the right source materials are landing in the case folder.
- Every assertion, claim, and analysis must be grounded in materials in the case folder. If additional information is required, you track it down, vet it, and ingest it as a tracked, searchable document before relying on it.

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
