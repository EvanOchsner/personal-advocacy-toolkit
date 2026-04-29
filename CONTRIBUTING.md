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
   `examples/maryland-mustang/`. If you need a new fixture, extend the
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

To enforce the lint + test step automatically on every `git push`, install
the dev pre-push hook once:

```sh
bash scripts/hooks/install_dev_hooks.sh
```

This wires `uv run ruff check .` and `uv run pytest -q` into
`.git/hooks/pre-push` — the same commands CI runs, so a green local push
should produce a green CI run. Use `git push --no-verify` in an
emergency, but treat that as a sign the hook needs fixing rather than
bypassing.

## Airgap rules for the case-map app

Anything under `scripts/app/` must remain airgapped. Concretely:

- `scripts/app/server.py`'s `BIND_HOST` stays at `"127.0.0.1"` — do not
  add a CLI flag to change it. (True network isolation is covered by
  the "paranoid mode" recipe in
  [`docs/concepts/case-map-app.md`](docs/concepts/case-map-app.md).)
- The HTTP Content-Security-Policy stays `'self'`-only for every
  fetch-bearing directive. No `https:` sources, no `*`.
- Files under `scripts/app/static/` and `scripts/app/templates/` must
  not contain `http://`, `https://`, `//cdn.`, or `//fonts.` — CI
  greps for these and fails the build on any match. XML namespace
  URIs (e.g. `http://www.w3.org/2000/svg`) are allowlisted because
  browsers treat them as identifiers, not fetch targets.
- The markdown renderer in `scripts/app/_markdown.py` must not grow
  support for raw HTML passthrough, external anchor tags, or image
  embedding. These are intentional omissions, not missing features.
- No new runtime dependencies for this app. The package-wide rule
  ("kept small on purpose") applies here most strictly — the airgap
  surface is easier to audit with stdlib + Jinja2 than with a larger
  framework.

## Authorship model

The initial build is split across phase-scoped subagent tracks. See
`.claude/plans/advocacy-toolkit/` for the per-phase working plans.
