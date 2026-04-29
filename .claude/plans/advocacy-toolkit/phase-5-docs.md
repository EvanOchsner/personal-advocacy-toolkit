# Phase 5 — Documentation, framing, integration walkthrough

Single serial agent.

## Deliverables

- Full `README.md` rewrite: thesis, non-goals, audience, 60-second demo
  that actually works.
- `docs/who-this-is-for.md` — final audience framing.
- All `docs/concepts/*.md` filled to production quality.
- All `docs/playbooks/*.md` — one jurisdiction worked, others scaffolded
  with clear populate-these lists.
- All `docs/tutorials/*.md` — written against the synthetic case.
- `examples/maryland-mustang/WALKTHROUGH.md` — end-to-end narrated
  run (clone, set up, ingest, triage, packet, dashboard, scrub preview).
- `.github/workflows/ci.yml` — runs pytest, ruff, and the post-check
  jobs from Phase 3C.
- `.github/ISSUE_TEMPLATE/` — bug, feature, new-authority-data,
  new-jurisdiction-playbook.

## Dogfood pass

Run the synthetic walkthrough top-to-bottom using only the documented
commands. Any tool that trips a user in the walkthrough opens a bug
against the Phase 1/3/4 owner.

## Publication prep (do not push without)

1. `grep -ri` for every real name, email, claim number, VIN, and policy
   form ID from the source project across the entire public repo. Zero
   hits required.
2. `git log --all -p | grep -i <term>` for the same terms. Zero hits.
3. A fresh human reader confirms the framing lands.
