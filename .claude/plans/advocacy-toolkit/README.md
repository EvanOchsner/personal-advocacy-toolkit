# Advocacy Toolkit — phase plans

Working plans for the subagent-driven build of this repo. The master plan
lives at `/Users/evanochsner/.claude/plans/ok-think-very-carefully-rosy-dewdrop.md`
on the author's machine; the files in this directory are the scoped
working documents for each phase / track.

## Phase order

| Phase | File | Mode | Depends on |
|---|---|---|---|
| 0 | `phase-0-scaffolding.md` | serial (done) | — |
| 1 | `phase-1-port-tools.md` | 3 agents parallel (1A/1B/1C) | Phase 0 |
| 2 | `phase-2-synthetic-case.md` | 1 agent, parallel to Phase 1 | Phase 0 |
| 3 | `phase-3-new-tools.md` | 3 agents parallel (3A/3B/3C) | Phases 1, 2 |
| 4 | `phase-4-skills-letters.md` | 2 agents parallel (4A/4B) | Phase 3 |
| 5 | `phase-5-docs.md` | 1 agent serial | Phase 4 |

After each phase, author runs the synthetic-case walkthrough end-to-end
as an integration checkpoint before the next phase launches.

## Hard constraint for every agent

Nothing from `/Users/evanochsner/workplace/lucy-repair-fight/evidence/` or
`drafts/` may be copied into this repo. Tools are to be read and
generalized, not the data. Real names, claim numbers, policy form IDs,
VINs, and addresses from the source project are banned strings in this
repo.
