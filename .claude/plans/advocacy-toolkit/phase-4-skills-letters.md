# Phase 4 — Skills, letters, dashboard

Two parallel tracks.

## Agent 4A — Skills

Author or port the 8 skills below into `skills/<name>/`. Use the
Anthropic skill format (SKILL.md with frontmatter).

1. `case-intake` — walks user through populating `case-intake.yaml`.
2. `situation-triage` — reads `case-intake.yaml`, proposes situation
   type + authorities, sanity-checks the framing.
3. `tone-modes` — portable codification from the source project's
   `CLAUDE.md` (lawyer vs casual, read-aloud test, scripts-as-scaffolds).
4. `authorities-finder` — wraps `authorities_lookup.py` conversationally.
5. `evidence-intake` — walks through adding a new piece of evidence via
   the correct pipeline for its type.
6. `pii-scrubber` — wraps `pii_scrub.py` with a review-and-confirm loop.
7. `packet-builder` — interactive packet assembly guided by
   `packet-manifest.yaml`.
8. `going-public` — publication-safety walkthrough before any derivative
   leaves the private repo.

Also port (minor doc updates only):

- `skills/provenance/` — from `lucy-repair-fight/.claude/skills/provenance/`.
- `skills/docx-comment-roundtrip/` — same source.

## Agent 4B — Letters + dashboard

- `scripts/letters/draft.py` — jinja-templated letter generation from
  `case-intake.yaml` + a template kind. Kinds to ship: `demand`, `foia`,
  `preservation` (litigation hold), `withdrawal` (withdrawal of consent),
  `cease-desist`.
- `templates/letter-templates/<kind>.docx.j2` — one template each.
- `scripts/status/case_dashboard.py` — reads `case-intake.yaml` +
  manifest + deadlines + packet status; renders a markdown status
  dashboard.
