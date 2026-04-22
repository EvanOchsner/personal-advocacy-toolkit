---
name: Populate a jurisdiction playbook (stub → worked)
about: Convert a stub playbook in docs/playbooks/ into worked reference material for a specific state
title: "[playbook] <jurisdiction>: <situation>"
labels: docs, good-first-issue
assignees: ''
---

**What this issue tracks:** converting one of the stub playbooks under
[`docs/playbooks/`](../../docs/playbooks/) from scaffolded-only into
worked reference material for a specific jurisdiction (analogous to
the Maryland insurance-dispute worked example).

## Which playbook

- [ ] `insurance-dispute.md` (MD worked; add another state)
- [ ] `medical-billing.md`
- [ ] `consumer-scam.md`
- [ ] `harassment-cyberbullying.md`
- [ ] `landlord-tenant.md`
- [ ] `debt-collector.md`
- [ ] `employment-retaliation.md`

**Jurisdiction:** (e.g., CA, NY, TX, etc.)

## Worked vs. stub

A *stub* playbook lists mechanics but has placeholders for authority
names, deadlines, and statute citations. A *worked* playbook has all
of those populated for one specific jurisdiction, confirmed against
primary sources.

To make a playbook worked, you need to:

1. Populate the jurisdiction's entry in
   [`data/authorities.yaml`](../../data/authorities.yaml) (see the
   [Populate authority data](?template=new_authority_data.md)
   template if you haven't already).
2. Populate the jurisdiction's entry in
   [`data/deadlines.yaml`](../../data/deadlines.yaml).
3. Edit the playbook file to replace its **Populate-this list** with
   a "Worked [jurisdiction] specifics" section, mirroring the shape
   of the Maryland section in
   [`insurance-dispute.md`](../../docs/playbooks/insurance-dispute.md).

## Checklist

- [ ] `data/authorities.yaml` entries populated (file a separate
      issue if there are a lot — authority data and playbook prose
      are often best as separate PRs).
- [ ] `data/deadlines.yaml` entries populated.
- [ ] Playbook Markdown updated with a "Worked <jurisdiction>
      specifics" section.
- [ ] `VERIFY WITH COUNSEL` disclaimer retained throughout.
- [ ] No real case material referenced (use hypothetical or the
      synthetic Mustang shape as the example).
- [ ] The four toolkit commands run cleanly against the new data:
      ```
      python -m scripts.intake.situation_classify ...
      python -m scripts.intake.authorities_lookup --situation <slug> --jurisdiction <STATE>
      python -m scripts.intake.deadline_calc     --situation <slug> --jurisdiction <STATE> --loss-date 2025-01-01
      python -m scripts.letters.draft --kind foia --intake <fixture>.yaml --out /tmp/test.docx
      ```

## Scope

A single jurisdiction × single situation playbook is a good PR size.
If you want to populate multiple jurisdictions in one pass, please
open separate issues / PRs — smaller PRs review faster and the
jurisdiction-specific statutes often require different reviewers.

## Sources

Please cite the primary sources (statute, regulation, agency page)
for each populated claim. Secondary sources are fine as pointers but
should not be the sole cite for a deadline or a statutory citation.

## Disclosure

- [ ] I am a licensed attorney in this jurisdiction (optional).
- [ ] I am not; I have confirmed each claim against the cited
      primary source; I understand the `VERIFY WITH COUNSEL` tag
      remains on every deadline and authority entry regardless.
