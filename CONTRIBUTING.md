# Contributing

*(Placeholder — will be filled out in Phase 5. Key rules recorded here now
so phase agents don't regress them.)*

## Hard rules

1. **No real case material.** This repo is seeded from a private precursor
   project (`lucy-repair-fight`), but no blobs, filenames, paths, names,
   claim numbers, or policy form IDs from that project may enter this repo.
   The *patterns* generalize; the *specifics* do not cross the boundary.
2. **Everything demo-worthy uses the synthetic case.** Tests, fixtures,
   tutorials, and screenshots all run against
   `examples/mustang-in-maryland/`. If you need a new fixture, extend the
   synthetic case — don't pull from anywhere else.
3. **Evidence integrity is non-negotiable.** Scripts that touch evidence
   must preserve hashes, xattrs, and the three-layer email pipeline. If
   you need to change how the manifest works, open an issue first.
4. **Tools, not advice.** Playbook documents point at authorities and
   describe mechanics. They do not say "argue this" or "cite that case
   against them."

## Local setup

The project is managed with [uv](https://docs.astral.sh/uv/). One-time
install (e.g. `curl -LsSf https://astral.sh/uv/install.sh | sh` or
`brew install uv`), then from the repo root:

```sh
uv sync --extra dev            # runtime + pytest + ruff
uv run pytest                  # full test suite
uv run ruff check .            # lint
```

Add `--extra synthetic-case` or `--extra publish` when working on those
subsystems. Every CLI in the docs is invoked as `uv run python -m scripts.X`
— `uv run` resolves the project venv automatically; there is no activation
step.

Before pushing, the publication-safety and banned-terms post-checks can be
rehearsed locally with `bash scripts/ci/local_postchecks.sh`, which mirrors
the CI job.

## Authorship model

The initial build is split across phase-scoped subagent tracks. See
`.claude/plans/advocacy-toolkit/` for the per-phase working plans.
