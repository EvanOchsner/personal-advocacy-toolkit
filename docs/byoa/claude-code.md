# Claude Code

Anthropic's official terminal coding agent. The toolkit's skills auto-
discover here — there is nothing to configure.

## Prerequisites

- [Install Claude Code](https://docs.claude.com/claude-code/quickstart) and
  authenticate.
- `uv` and `git` (the same toolkit prerequisites — see [README §
  Install](../../README.md#install)).

## First session

```sh
git clone https://github.com/EvanOchsner/personal-advocacy-toolkit.git
cd personal-advocacy-toolkit
uv sync
claude
```

When the prompt appears, just describe your situation in plain English.

> *"I'm fighting my insurance company about a totaled car. They're
>  deducting $5,000 for some kind of rate adjustment and I think it's
>  bogus. Where do I start?"*

The `pat-workflow` skill fires, walks you through case-intake, and
sets up a workspace **outside** this repo (you'll be asked where to put
it). After that the assistant moves through authorities → deadlines →
evidence → drafts → packet → publication-safety in order, asking what
you have at each phase and accepting "I don't know yet" as a valid
answer.

## Smoke test

To confirm skills are loading:

```
> /skills
```

You should see all 13 PAT skills listed (`pat-workflow`, `case-intake`,
`situation-triage`, `authorities-finder`, `authorities-reconcile`,
`authorities-web-research`, `evidence-intake`, `provenance`,
`packet-builder`, `pii-scrubber`, `going-public`,
`docx-comment-roundtrip`, `tone-modes`).

If they don't appear, confirm:

- You're inside the toolkit repo (`pwd` shows
  `.../personal-advocacy-toolkit`).
- The repo has the `.claude/skills/` directory (`ls .claude/skills/`).
- You ran `claude` from the repo root, not from a parent directory.

## Working on a real case

The repo-level [`CLAUDE.md`](../../CLAUDE.md) tells the assistant to
refuse putting case materials inside the toolkit repo. If you say
"let's start a real case", you'll be redirected to:

```
uv run python -m scripts.init_case --output ~/cases/<short-name> --git
```

…and the conversation continues in that workspace. Your case folder
gets its own `CLAUDE.md` (instantiated from the
[template](../../templates/CLAUDE.md.template)) so the assistant has
case-specific context the next time you `cd` into it.

## When to drop back to the manual workflow

The CLI works fine without the assistant — see the [README quick-
start](../../README.md). Reasons to drop back:

- You want determinism / reproducibility over conversation.
- You're scripting something against the toolkit (CI, batch
  processing).
- You want to learn what each tool actually does before letting an
  assistant run it for you (recommended at least once).

The skills don't replace the CLI; they wrap it.
