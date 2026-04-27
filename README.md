# PAT: Personal Advocacy Toolkit

<p align="center">
  <img src="PAT-logo-3.png" alt="PAT Logo" width="400">
</p>

This is an AI toolkit to help individuals in a dispute understand the facts, legal and regulatory frameworks in play, find advocates who can assist you, and what information they need to help you.
The goal is that a non-technical person can organize their evidence and arguments in the dispute so that an attorney, regulator, journalist, or other advocate can act on it effectively.


## Thesis

You have a situation — a bad-faith insurance claim, a surprise medical
bill, a harassment campaign, a landlord trying to retaliate, a debt
collector who won't follow the rules, a scam that took your money.
There are people and offices whose job it is to help: state regulators,
consumer-protection advocates, attorneys, journalists. They can only
help you if you hand them something they can act on.

This toolkit does the legwork:
- Organize your digital evidence, tracking forensic signatures (hashes, timestamps, xattrs) to prove integrity. Just drop files into the project root and ask the agent or process and file them, or use included skills and scripts to automate bulk loading and processing of emails, photos, phone and SMS records and other data in a consistent, auditable way.
- Evidence integrity: git pre-commit hooks ensure everything filed under `evidence/` cannot be overwritten without an explicit override.
- Automatically extract full machine searchable text from pdfs, html documents and emails that obscure the plaintext. Uses version-controlled tools that can be audited and fine-tuned to ensure fidelity and reproducibility.
- Helps you locate the exact text of policies, regulations, laws from trusted public sources and store within the project as original copies plus machine-searchable plaintext markdown versions.
- Skills and tools to draft correspondence, filings, complaints, briefs and other written documents.
- Interactive comment system with Anti-hallucination guard rails: Specialized subagents are included to fact check, answer questions and provide analysis **using only the project materials**. Subagents are denied web search or network access and instructed to use only project materials to fact-check, analyze, answer questions or propose any text.
- Interactive case map and timeline: an interactive dashboard view showing allied, neutral and adversarial parties in the dispute, relationships among parties, and a timeline of events in the case. You can interact with the parties and events on the timeline to get citations and links to all tracked project documents associated with that entity/event.

**Do the legwork so whoever helps you can actually help you.**

## Core principles

- Understand and document the facts of the case. If you are acting in good faith and the other party is not, the facts are on your side and you need to document them in a thorough, airtight manner.
- Every dispute has a case folder that holds information you believe to be the ground truth in the dispute. YOU are the steward of information pulled inside the project. The agent and other resources help you find the right authorities, laws, policies, etc. but ultimately you need to use your own judgement to ensure you are adding the correct source materials to the case folder.
- Every assertion, claim and analysis must be grounded in materials in the case folder. If additional information is required that's not in the project, you must track down that information, vet it, and have the agent pull it into the project as a tracked, searchable document.


## What this isn't

- **Not legal advice.** Nothing here tells you what to argue or predicts
  an outcome in your specific case. Every tool that emits a date, an
  authority, or a statute cite does so with a "verify with counsel"
  disclaimer.
- **Not a substitute for counsel.** When you need a lawyer, hire one.
  The toolkit makes you a better client, not your own attorney.
- **Not for criminal-matter evidence collection.** The chain-of-custody
  model here is designed for civil and regulatory contexts. Criminal
  evidentiary standards are stricter and should involve law enforcement.
- **Not a tool for mass-producing slop.** These tools are intended to help people acting in good faith protect themselves from bad actors by understanding and demonstrating the facts of the case and rules in play. Using them as intended means meticulously constructing the facts and arguments for your specific dispute. The goal is to produce the antithesis of careless, vibe-lawyered AI slop.

## Situations it fits

The initial playbooks cover:

- Insurance bad-faith / claim handling
- Medical balance-billing and surprise bills
- Consumer scams (romance, crypto, impersonation, fake invoices)
- Harassment and cyberbullying
- Landlord retaliation / habitability disputes
- Debt-collector abuse (FDCPA)
- Employment retaliation

The framework generalizes further. See `docs/playbooks/` for each
situation's reference material.

## 60-second demo

Uses the fully synthetic Mustang-in-Maryland example. Nothing real is
at stake.

Prerequisite: [uv](https://docs.astral.sh/uv/getting-started/installation/)
(e.g. `curl -LsSf https://astral.sh/uv/install.sh | sh` or
`brew install uv`).

```sh
git clone https://github.com/EvanOchsner/personal-advocacy-toolkit.git
cd personal-advocacy-toolkit
uv sync

# See the case context
cat examples/mustang-in-maryland/case-facts.yaml

# 1. Hash every file under the evidence tree
uv run python -m scripts.evidence_hash \
  --root examples/mustang-in-maryland/evidence \
  --manifest examples/mustang-in-maryland/.evidence-manifest.sha256

# 2. Look up which authorities have jurisdiction over a MD insurance dispute
uv run python -m scripts.intake.authorities_lookup \
  --situation insurance_dispute --jurisdiction MD

# 3. Compute statute-of-limitations / notice deadlines from the loss date
uv run python -m scripts.intake.deadline_calc \
  --situation insurance_dispute --jurisdiction MD \
  --loss-date 2025-03-15
```

For the full end-to-end run (ingest → triage → packet → dashboard →
publication-safety scrub), see
[`examples/mustang-in-maryland/WALKTHROUGH.md`](examples/mustang-in-maryland/WALKTHROUGH.md).

For a guided first-time setup against your own situation, see
[`docs/tutorials/01-setting-up-your-case.md`](docs/tutorials/01-setting-up-your-case.md).

## For tech-minded evaluators

If you are from Suffolk LIT Lab, United Policyholders, an LSC TIG
grantee, or any civic-legal-tech group: the differentiator is not the
letter templates or the packet PDF — those are table stakes. The
differentiator is a *forensic audit trail* a regulator or attorney can
verify without trusting the author:

- **Hash manifest** (`scripts/evidence_hash.py`) — SHA-256 of every
  file, human-readable.
- **Pre-commit immutability hook** (`scripts/hooks/pre_commit.py`) —
  refuses git commits that modify or delete files under the protected
  evidence path.
- **xattr / provenance snapshots** (`scripts/provenance_snapshot.py`) —
  captures `kMDItemWhereFroms` download URLs and quarantine timestamps
  that git does not track.
- **Unified provenance report** (`scripts/provenance.py`) — joins the
  manifest, the xattr snapshot, git history, and pipeline-metadata
  sidecars into a single JSON document a reviewer can skim.
- **Publication-safety scrubbers** with mandatory post-checks
  (`scripts/publish/`) — the failure mode these exist to prevent is a
  "redacted" PDF whose text layer still contains the redacted content.
- **Case-map app** (`scripts/app/`) — local-only browser UI that
  renders a three-column entity graph (self/allies, neutrals,
  adversaries) and drilldown panel from `entities.yaml` +
  `case-facts.yaml`. Binds 127.0.0.1, strict CSP, no external
  resources. See
  [`docs/concepts/case-map-app.md`](docs/concepts/case-map-app.md)
  for the airgap caveats and the "paranoid mode" recipe.

Full write-up and interop notes:
[`docs/concepts/evidence-integrity.md`](docs/concepts/evidence-integrity.md).

The packet assembler (`scripts/packet/build.py`) is driven by a
declarative `packet-manifest.yaml` (schema at
`templates/packet-manifests/schema.yaml`) and is a plausible upstream
feed into Document Assembly Line / Docassemble: DAL handles interview
→ document; this handles the pre-filing evidence-organization step
that DAL assumes has already happened.

## Repository layout

```
scripts/       CLI tools (evidence_hash, provenance, ingest, intake,
               packet, publish, letters, status, hooks)
skills/        Portable Claude Code skills (case intake, situation
               triage, provenance review, packet building, PII scrub,
               tone-modes, going-public checks)
data/          Community-maintainable reference data (authorities by
               jurisdiction, deadline tables, situation types)
templates/     Case-intake, letter, and packet-manifest templates
docs/          Concepts, playbooks, tutorials
examples/      Fully synthetic worked examples (mustang-in-maryland)
tests/         pytest suite; fixtures derived from the synthetic case
```

## Install

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first,
then:

```sh
uv sync                                 # core runtime
# Optional extras:
uv sync --extra dev                     # pytest + ruff
uv sync --extra publish                 # Pillow, pypdf, reportlab for scrubbers
uv sync --extra synthetic-case          # Pillow, python-docx for regenerating the example
# Combine extras with multiple --extra flags, e.g.:
uv sync --extra dev --extra synthetic-case
```

Every CLI invocation in the docs is shown as `uv run python -m scripts...`;
`uv run` resolves the project-managed virtualenv automatically, so there is
nothing to activate.

`git filter-repo` (for history sanitizing) is a separate binary;
install via your package manager (`brew install git-filter-repo` on
macOS).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Good first contributions:

- Populate a jurisdiction in `data/authorities.yaml` or
  `data/deadlines.yaml`.
- Flesh out one of the stub playbooks under `docs/playbooks/`.
- Add a new ingest format (SMS / iMessage, voicemail-metadata, medical
  EOB) following the three-layer pattern in `scripts/ingest/`.

## License

Apache-2.0 — see [LICENSE](LICENSE). Permissive license with explicit patent grant, chosen to keep the toolkit integrable with legal-aid and civic-tech platforms without license friction.
