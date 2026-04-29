# Other shell-having agents

Cursor, Windsurf, Aider, Continue, Cline, OpenCode, your-favorite-
local-model-rig — anything that gives an LLM `bash` access to a
working directory. The skills are plain markdown; getting them in
front of your assistant is a one-line config in most cases.

## The pattern

Every shell-having harness has some way to feed the LLM a system-
level "operating manual". Tell yours that the manual is at
`.claude/skills/`. Concretely, it should:

- Read `CLAUDE.md` at the repo root for orientation.
- Treat `.claude/skills/<name>/SKILL.md` as a directory of skills,
  loading the relevant one when its `description` matches user
  intent.
- Honor the `pat-workflow` skill as the top-level orchestrator when
  the user describes a fresh dispute or asks "where do I start."

## Per-harness recipes

These are starting points; each project's docs are the authority.

### Cursor

Cursor reads `.cursor/rules/*.mdc` files for project-level rules. The
simplest path:

```sh
cd personal-advocacy-toolkit
mkdir -p .cursor/rules
ln -s ../../.claude/skills .cursor/rules/pat-skills
```

Then add a top-level `.cursor/rules/pat-orchestrator.mdc` that points
at `CLAUDE.md` and the `pat-workflow` skill.

(`.cursor/rules/` is per-project and not committed to this repo by
default — you set it up locally to match your workflow.)

### Aider

Aider takes `--read` flags pointing at files the model should treat
as read-only context. The toolkit's CLAUDE.md plus the orchestrator
skill is usually enough to get the workflow started:

```sh
cd personal-advocacy-toolkit
aider \
  --read CLAUDE.md \
  --read .claude/skills/pat-workflow/SKILL.md
```

…and let aider read individual per-phase skills as needed (it can
open them on demand).

### Continue / Cline / OpenCode / generic VS-Code-style harness

These typically have a "system prompt" or "rules" config field. Paste
something like:

```
You are operating in the personal-advocacy-toolkit repo. Read CLAUDE.md
at the repo root for orientation. Skills live under .claude/skills/;
the entry point is .claude/skills/pat-workflow/SKILL.md. When the user
describes a dispute or asks "where do I start", load and follow the
pat-workflow skill. Refuse to put case materials inside this repo —
direct the user to `uv run python -m scripts.init_case` instead.
```

### Local-model agent rigs (homebrew)

If you've rolled your own agent harness, the shape is the same: feed
the model `CLAUDE.md` first, treat `.claude/skills/*/SKILL.md` as a
loadable manual indexed by the `description` frontmatter. Whatever
"tool use" mechanism your harness exposes (bash, file read, file
write) is what the skills will reach for.

Local models with weaker instruction-following may not honor the
"never invent authorities" rule reliably. If you're driving a local
model, plan to spot-check authority cites against
[`data/authorities.yaml`](../../data/authorities.yaml) yourself.

## What if my harness doesn't auto-load skills by directory?

Then it's a manual-load workflow: when the user says something that
should fire a particular skill, paste the relevant SKILL.md into the
context window yourself. It's clunky but works. If you find yourself
doing this often, consider switching to a harness that auto-discovers
project-level skills, or scripting a small "load skill on intent
match" helper for your harness.
