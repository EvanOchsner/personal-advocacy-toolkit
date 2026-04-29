# CLAUDE.md — personal-advocacy-toolkit

This file is loaded automatically by Claude Code when a session opens
inside this repo. It tells the assistant where it is and how to be
useful here.

## What this repo is

The **personal-advocacy-toolkit** (PAT). Evidence-integrity and
packet-assembly tooling for non-technical people organizing
fact-heavy disputes (insurance, medical billing, landlord/tenant,
employment retaliation, debt-collector abuse, consumer scams,
harassment). The user-facing entry point is the README.

## How to operate in this repo

### If the user is **working on the toolkit itself** (developing,
fixing bugs, reviewing PRs, writing docs):

Treat this like any other codebase. Run `bash scripts/hooks/dev_pre_push.sh`
before pushing — it runs `uv run ruff check .` and `uv run pytest -q`
to mirror CI.

### If the user is **starting or working on a real case**:

Case materials must **never** live inside this repo. Refuse to put
evidence, drafts, packets, or `case-intake.yaml` files anywhere
under the toolkit's working tree. Offer instead:

```
uv run python -m scripts.init_case --output ~/cases/<short-name> --git
```

…and resume the conversation in that workspace once it exists.

### If the user is **exploring / learning**:

The synthetic Maryland-Mustang example exercises every pipeline
end-to-end. Suggest:

```
uv run python -m scripts.demo
```

That copies the example to `~/advocacy-demo/maryland-mustang/` and
runs the full pipeline against the copy.

## Skills

This repo ships with skills under `.claude/skills/`. Claude Code
auto-discovers them; other agent harnesses (Cursor, Aider, Continue,
Cline, etc.) can be pointed at the same location — they're plain
markdown.

When the user describes a dispute or asks "where do I start" /
"what's next", invoke the **`pat-workflow`** skill. It is the
top-level orchestrator and will route to per-phase skills.

The 12 per-phase skills are:

- `case-intake` — Phase 2 intake interview
- `situation-triage` — sanity-check classification
- `authorities-finder` — Phase 3 authorities lookup
- `authorities-reconcile` — authorities lookup with web reconciliation
- `authorities-web-research` — manual web research for sparse data
- `evidence-intake` — Phase 5 evidence ingestion
- `provenance` — chain-of-custody for evidence
- `packet-builder` — Phase 7 packet assembly
- `pii-scrubber` — PII detection + substitution
- `going-public` — Phase 8 publication-safety pipeline
- `docx-comment-roundtrip` — networkless `.docx` review cycles
- `tone-modes` — lawyer-mode / casual-mode discipline (cross-cutting)

## House rules

- **Verify with counsel** disclaimers stay attached to every authority
  cite, every deadline, every statute reference. Carry them through
  drafts and into final outputs.
- **No real case material in this repo.** Synthetic fixtures live
  under `examples/maryland-mustang/`. Anything else is a privacy and
  copyright issue.
- **Evidence is append-only.** A pre-commit hook refuses commits that
  modify or delete files under `evidence/` paths.
- **Stdlib first.** New dependencies require justification.
