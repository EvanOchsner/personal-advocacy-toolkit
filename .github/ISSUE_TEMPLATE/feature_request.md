---
name: Feature request
about: A new tool, format, or mechanic the toolkit should support
title: "[feature] <short description>"
labels: enhancement
assignees: ''
---

**Before you open this, please confirm:**

- [ ] The feature is not already covered by an existing tool.
  (`scripts/` has 15+ tools; skim the directory listing first.)
- [ ] You have read
  [`docs/who-this-is-for.md`](../../docs/who-this-is-for.md) to
  confirm the feature fits the primary audience (non-technical
  people organizing fact-heavy disputes).

## The situation

What problem are you trying to solve? Describe the user's situation
in one or two sentences. Examples of good framings:

- "I have a pile of voice memos from tenant calls and the toolkit
  can't ingest them today."
- "My state's AG office accepts complaints via a JSON API; a packet
  exporter for that format would save me an hour of copy-paste."

## Proposed shape

What should the tool do? Try to be specific about:

- CLI signature (`uv run python -m scripts.foo --bar BAZ`).
- Inputs (file formats, directory layout).
- Outputs (where things land, what shape the output takes).
- Whether this is a new tool or an extension to an existing one.

## Scope

Which slice should ship first? The toolkit deliberately ships
prototypes for one format and stubs for the rest, to avoid scope
creep. A single-format prototype plus follow-on tickets for
additional formats is usually the right shape.

## Alternatives considered

Other ways to solve the same problem, and why this is the right one
for the toolkit (vs. a user doing it manually, or using a different
project entirely). If an existing civic-legal-tech project
(Docassemble, DAL, DocumentCloud, etc.) already does this, flag it.

## Who else would benefit

Is this specific to your situation, or do other users in the same
situation-type have the same need? Feature requests tied to broad
playbook coverage (medical billing across states, employment
retaliation outside Title VII) are higher priority than one-off
needs.

## Willingness to contribute

Would you be able to:

- [ ] Write the code with review guidance.
- [ ] Write tests against a synthetic fixture.
- [ ] Populate reference data
      (`data/authorities.yaml`, `data/deadlines.yaml`) for your
      jurisdiction.
- [ ] Just file this and hope someone picks it up.

Any of the above is fine. We ask because contribution history helps
prioritize.
