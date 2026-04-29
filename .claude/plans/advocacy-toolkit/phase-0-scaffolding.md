# Phase 0 — Scaffolding (done)

Serial pass. Author: Claude (this session).

## Deliverables (complete)

- Directory tree matching §Top-level structure in the master plan.
- `README.md` with thesis, non-goals, audience, TBD 60-sec demo.
- `CONTRIBUTING.md` with the four hard rules (no real case material,
  synthetic-first, evidence integrity, tools-not-advice).
- `CODE_OF_CONDUCT.md` placeholder.
- `pyproject.toml` with name, description, Python version, dev deps, and
  empty runtime `dependencies` list (phase-1 agents will populate as they
  port).
- `.gitignore` — Python, editor, OS, `.tmp/`, env.
- `LICENSE` — TBD placeholder.
- `.pre-commit-config.yaml` — empty repos list; Phase 1A wires it.
- Stub `docs/concepts/` (5 files), `docs/playbooks/` (7 files),
  `docs/tutorials/` (5 files), `docs/getting-started.md`,
  `docs/who-this-is-for.md`.
- Stub `examples/maryland-mustang/README.md` + `WALKTHROUGH.md`.
- Stub `templates/CLAUDE.md.template`.
- Per-phase plan files in `.claude/plans/advocacy-toolkit/`.

## Explicitly NOT done in Phase 0

- No script code.
- No data files populated.
- No skills written.
- No synthetic-case content.
- `git init` deferred — Phase 1A will initialize git when the pre-commit
  hook is ready to land in the initial commit.

## Notes for downstream agents

- All stub files carry a `*(Stub — authored in Phase X.)*` marker
  indicating which phase owns them.
- The master plan's §Tool inventory table maps source-file-in-`lucy-repair-fight`
  → destination-file-in-this-repo. Honor that mapping exactly; do not
  re-architect the tool set without an issue.
