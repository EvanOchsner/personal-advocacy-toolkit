# BYOA — Bring Your Own Assistant

The toolkit ships with a skill bundle under [`.claude/skills/`](../../.claude/skills/)
that turns any compatible AI assistant into a guide for building your
case. The assistant interviews you, runs the CLI commands on your
behalf, validates the outputs, and walks you through each phase of
the workflow.

This is **optional**. If you'd rather run the commands yourself, the
[README's quick-start](../../README.md) and the
[tutorials](../tutorials/) walk you through the same workflow without
any AI involvement. The skill bundle is for users who'd rather have a
conversation than learn the CLI.

## Three flavors of assistant

### 1. Claude Code (recommended)

Anthropic's terminal coding agent. Auto-discovers `.claude/skills/`,
no configuration needed. **Setup time: zero.**

See [`claude-code.md`](claude-code.md).

### 2. Other shell-having agent harnesses

Cursor, Windsurf, Aider, Continue, Cline, OpenCode, plus anyone running
a local-model rig with their own agent loop. The skill content is plain
markdown plus YAML frontmatter — every harness can read it. The only
variation is *how* you tell that harness "the operating manual lives at
`.claude/skills/`."

See [`other-shell-agents.md`](other-shell-agents.md).

### 3. No-shell surfaces

claude.ai default chat (without Skills enabled), ChatGPT default chat,
Gemini chat, etc. The assistant can read the skills as guidance and
walk you through the workflow conversationally — but it can't run the
CLI for you. You'll be running commands yourself, which makes this
roughly equivalent to following the tutorials with a chatbot
beside you.

See [`no-shell-surfaces.md`](no-shell-surfaces.md).

## What you keep / what you give up

| Capability                                | Shell-having agent | No-shell surface |
|-------------------------------------------|--------------------|------------------|
| Workflow orchestration & coaching         | ✓                  | ✓                |
| Authorities & deadlines lookup            | ✓ (auto)           | ✓ (manual)       |
| Letter drafting                           | ✓                  | ✓                |
| Evidence ingestion (three-layer pipeline) | ✓                  | ✗ (you run it)   |
| SHA-256 manifest + chain of custody       | ✓                  | ✗ (you run it)   |
| Packet PDF assembly                       | ✓                  | ✗ (you run it)   |
| Publication-safety scrubbers              | ✓                  | ✗ (you run it)   |

A no-shell surface still gets you the workflow; it just shifts the
"run this command" labor back to you.

## Provider-agnostic by design

The skill content is markdown. We follow Anthropic's directory
convention (`.claude/skills/<name>/SKILL.md`) because it's the most
concretely-published spec, but nothing about the *content* is
Claude-specific. If you're running an open or local model under your
own agent harness, point your harness at `.claude/skills/` and you're
in business.

## House rules every assistant inherits

The orchestrator skill (`.claude/skills/pat-workflow/SKILL.md`) and
the per-phase skills carry these rules forward:

- Every authority cite, every deadline, every statute reference is
  reference information — **not legal advice**.
- The assistant must not invent authorities or deadlines. If the data
  table is sparse, say so and offer web research as an opt-in.
- Internal reasoning may be casual ("they're trying to re-underwrite
  the policy after the loss"); outbound paragraphs are lawyer mode by
  default and pass the read-aloud test.
- Evidence is append-only. The assistant will not modify or delete
  files under `evidence/` paths.

If you encounter an assistant that violates one of these — invents
authorities, drops disclaimers, mixes tone modes inappropriately —
that's a skill-content bug. Open an issue.
