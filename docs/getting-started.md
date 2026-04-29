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
3. **Run the synthetic walkthrough end-to-end** to confirm your
   environment works:
   [`examples/maryland-mustang/WALKTHROUGH.md`](../examples/maryland-mustang/WALKTHROUGH.md).
   Every command is real and should complete in under a minute.
4. **Start Tutorial 01** to set up your own case:
   [`tutorials/01-setting-up-your-case.md`](tutorials/01-setting-up-your-case.md).
   Tutorials 02–05 cover ingest, triage, packet assembly, and going
   public safely. Tutorial 06 covers the case-map app:
   [`tutorials/06-case-map-app.md`](tutorials/06-case-map-app.md).

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
