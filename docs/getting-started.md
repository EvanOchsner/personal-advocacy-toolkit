# Getting started

New here? Do these four things, in order:

1. **Read [`who-this-is-for.md`](who-this-is-for.md)** to confirm the
   toolkit fits your situation. If you are in a criminal matter or
   need a lawyer immediately, this toolkit is not the right first
   step.
2. **Install [uv](https://docs.astral.sh/uv/getting-started/installation/)
   and sync the project:**
   ```sh
   uv sync
   ```
   Python 3.11 or 3.12 (uv will provision the interpreter if needed).
   Optional extras for specific features:
   ```sh
   uv sync --extra publish          # scrubbers (Pillow, pypdf, reportlab)
   uv sync --extra synthetic-case   # regenerate the synthetic example
   uv sync --extra dev              # pytest + ruff
   ```
   Every CLI in the docs is run via `uv run` — no virtualenv to activate.
3. **Run the one-command demo** to confirm your environment works:
   ```sh
   uv run python -m scripts.demo
   ```
   This copies the synthetic Maryland-Mustang example to
   `~/advocacy-demo/maryland-mustang/` and runs the full pipeline
   (hash, ingest, classify, authorities, deadlines, packet, letters,
   PII scrub). Or follow the manual walkthrough step-by-step:
   [`examples/maryland-mustang/WALKTHROUGH.md`](../examples/maryland-mustang/WALKTHROUGH.md).
4. **Start your own case:**
   ```sh
   uv run python -m scripts.init_case --output ~/cases/my-case
   ```
   This creates the full directory structure, copies starter templates,
   and walks you through an interactive intake questionnaire. Add
   `--git` to initialize a git repo with the evidence-immutability
   hook. For the detailed manual setup, see
   [`tutorials/01-setting-up-your-case.md`](tutorials/01-setting-up-your-case.md).
   Tutorials 02–05 cover ingest, triage, packet assembly, and going
   public safely. Tutorial 06 covers the case-map app:
   [`tutorials/06-case-map-app.md`](tutorials/06-case-map-app.md).

   Prefer to have an AI walk you through it instead? See
   [`byoa/README.md`](byoa/README.md) — the toolkit ships with a
   skill bundle under `.claude/skills/` that turns any compatible
   assistant (Claude Code recommended; Cursor / Aider / others
   supported; no-shell surfaces work as guidance) into a workflow
   guide. The CLI commands above stay the same — the assistant just
   runs them for you.

## Concept docs (read before making decisions)

- [`concepts/evidence-integrity.md`](concepts/evidence-integrity.md)
  — why hashes, xattrs, and the pre-commit hook matter.
- [`concepts/chain-of-custody.md`](concepts/chain-of-custody.md) —
  the four sources a reviewer verifies.
- [`concepts/authorities-and-regulators.md`](concepts/authorities-and-regulators.md)
  — the "who cares about this?" map.
- [`concepts/tone-modes.md`](concepts/tone-modes.md) — lawyer mode
  vs. casual mode; when to use which.
- [`concepts/pii-and-publication.md`](concepts/pii-and-publication.md)
  — read before publishing *anything* derived from a real case.
- [`concepts/case-map-app.md`](concepts/case-map-app.md) — the local
  browser UI for visualising parties and timeline; airgap caveats
  and paranoid-mode recipe.

## Playbooks (pick the one that fits your situation)

[`playbooks/`](playbooks/) covers insurance disputes (worked for MD),
medical billing, consumer scams, harassment, landlord-tenant, debt
collectors, and employment retaliation.

## Need help?

- GitHub issue templates under
  [`.github/ISSUE_TEMPLATE/`](../.github/ISSUE_TEMPLATE/) for bugs,
  feature requests, and reference-data contributions.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) for how to contribute.
