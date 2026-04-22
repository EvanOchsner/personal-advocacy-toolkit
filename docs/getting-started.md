# Getting started

New here? Do these four things, in order:

1. **Read [`who-this-is-for.md`](who-this-is-for.md)** to confirm the
   toolkit fits your situation. If you are in a criminal matter or
   need a lawyer immediately, this toolkit is not the right first
   step.
2. **Install the package:**
   ```sh
   pip install -e .
   ```
   Python 3.11 or 3.12. Optional extras for specific features:
   ```sh
   pip install -e ".[publish]"          # scrubbers (Pillow, pypdf, reportlab)
   pip install -e ".[synthetic-case]"   # regenerate the synthetic example
   pip install -e ".[dev]"              # pytest + ruff
   ```
3. **Run the synthetic walkthrough end-to-end** to confirm your
   environment works:
   [`examples/mustang-in-maryland/WALKTHROUGH.md`](../examples/mustang-in-maryland/WALKTHROUGH.md).
   Every command is real and should complete in under a minute.
4. **Start Tutorial 01** to set up your own case:
   [`tutorials/01-setting-up-your-case.md`](tutorials/01-setting-up-your-case.md).

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

## Playbooks (pick the one that fits your situation)

[`playbooks/`](playbooks/) covers insurance disputes (worked for MD),
medical billing, consumer scams, harassment, landlord-tenant, debt
collectors, and employment retaliation.

## Need help?

- GitHub issue templates under
  [`.github/ISSUE_TEMPLATE/`](../.github/ISSUE_TEMPLATE/) for bugs,
  feature requests, and reference-data contributions.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) for how to contribute.
