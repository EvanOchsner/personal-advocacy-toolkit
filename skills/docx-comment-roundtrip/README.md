# docx-comment-roundtrip skill — port pending

The canonical authored `SKILL.md` for this skill lives in a private
project (`lucy-repair-fight/.claude/skills/docx-comment-roundtrip/`)
that Phase 4A (Agent 4A) did not have read access to. The current
`SKILL.md` in this directory is a stub describing the intent and
noting that no wrapper script exists in this repo yet.

## Follow-up task

1. Pull the full `SKILL.md` contents from the source repo.
2. Port the underlying comment-strip script (if it exists in the
   source repo) into `scripts/publish/` alongside the other
   scrubbers.
3. Wire the new script into the `going-public` skill's pipeline if
   appropriate.
4. Delete this README.
