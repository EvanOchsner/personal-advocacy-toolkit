# No-shell surfaces

claude.ai web chat (without Skills enabled), ChatGPT chat, Gemini
chat, NotebookLM, etc. The assistant can read the toolkit's skills
as guidance and walk you through the workflow conversationally —
but it can't run the CLI for you. **You'll be running commands
yourself**, which makes this approach roughly equivalent to following
the [tutorials](../tutorials/) with a chatbot beside you.

If your goal is "I want the AI to do as much as possible", a shell-
having harness ([Claude Code](claude-code.md) or
[the others](other-shell-agents.md)) is dramatically better. This
doc is for users who can't or won't install those.

## Setup

There is no bundle export, no system-prompt artifact, no installer.
The skills are markdown files in this repo. To put them in front of
your AI:

1. Open the repo on GitHub: <https://github.com/EvanOchsner/personal-advocacy-toolkit>
2. Open [`CLAUDE.md`](../../CLAUDE.md) and the
   [`pat-workflow` SKILL.md](../../.claude/skills/pat-workflow/SKILL.md).
3. Paste both into your chat session as a single message. Tell the
   AI: "This is the operating manual for the personal-advocacy-
   toolkit. Walk me through it."
4. When the AI asks you to run a command, run it yourself in a
   separate terminal and paste back the output.

That's the whole protocol. When you're ready for a specific phase
(authorities, evidence, packet, publication safety), open the
matching `.claude/skills/<name>/SKILL.md` and paste it in.

## Surface-specific notes

### claude.ai web

If you're on a Claude plan that includes the **Skills** feature,
upload the `.claude/skills/` directory there instead of pasting —
Claude will discover and use the skills the same way Claude Code
does. The bottleneck is still no shell access: you'll still run
commands yourself, but at least the AI will follow the orchestrator
without you copy-pasting it.

### NotebookLM

NotebookLM is excellent at grounded Q&A over uploaded sources. Upload:

- `CLAUDE.md` and `pat-workflow/SKILL.md` for orientation.
- All five YAML files under [`data/`](../../data/) for authority and
  deadline lookups.
- The relevant playbook from
  [`docs/playbooks/`](../playbooks/) for your situation type.

Ask: *"For an insurance_dispute in Maryland, who do I file with and
what deadlines apply?"* — and you'll get a citation-grounded answer
rather than guessing.

NotebookLM doesn't run code; it cites your uploads. For drafting and
packet assembly, you'll move back to a different surface.

### ChatGPT

For one-off use, paste-and-go works. For ongoing case work, build a
**Custom GPT** with the SKILL.md files plus the data tables uploaded
as Knowledge files. The Custom GPT remembers the operating manual
across sessions.

ChatGPT's Code Interpreter sandbox can run small Python scripts in
isolation, but the toolkit's CLI assumes a real `uv`-managed
workspace and persistent `evidence/` tree, neither of which the
sandbox provides. Treat ChatGPT as guidance-only; run the CLI on
your own machine.

### Gemini

Same shape as ChatGPT. Build a **Gem** with the operating manual and
data tables; use it for guidance; run the CLI yourself.

## Honest framing

This is the lowest-bandwidth path through the toolkit. You get:

- A workflow guide that stays consistent across sessions.
- Authority and deadline lookups grounded in the toolkit's data
  tables.
- Drafting help anchored in the tone-modes discipline and the
  per-situation playbooks.

You don't get:

- Forensic chain of custody (no SHA-256 manifests, no xattr capture).
- Deterministic packet PDF assembly.
- Pre-commit hook protections on the evidence tree.
- Anything else the CLI scripts do under the hood.

For a case heading to a regulator filing or litigation, the chain-of-
custody story matters. Consider running the CLI yourself for the
forensic-integrity steps even if you do the rest via no-shell chat.
