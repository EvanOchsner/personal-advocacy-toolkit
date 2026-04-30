---
name: pat-workflow
description: Walk the user end-to-end through the personal-advocacy-toolkit case-building workflow — triggers when a user describes a fresh dispute or asks "where do I start", "help me build a complaint / packet", "I have a problem with my insurer / landlord / employer / hospital / debt collector / merchant / online platform / etc.", or anytime there is no orienting context for the current case yet.
---

# pat-workflow

The personal-advocacy-toolkit (PAT) is a workflow, not a single tool.
This skill is the orchestrator: it sequences the eight phases below,
points at the per-phase skill that owns each one, and tells you when
to hand back to the user vs when to keep going.

You **do not duplicate** content from per-phase skills here. When a
phase fires, invoke the skill that owns it. This skill exists so the
AI knows the *order*, the *transitions*, and *what done looks like*
for each phase.

## When this skill fires

- The user describes a dispute or grievance for the first time.
- The user asks "where do I start" or "what's next" without a
  specific phase in mind.
- A previous phase has just completed and the user has not yet
  named the next step.

## Posture

- **Drive the user forward.** They are not expected to know what
  comes next. After each phase, name the next phase and offer to
  start it.
- **Accept partial information.** If the user can't answer something,
  note it as a gap and continue. Do not block on missing data unless
  the next phase truly requires it.
- **Run the commands for them.** When a per-phase skill specifies a
  CLI invocation, run it via the shell rather than dictating it. The
  user is here because they don't want to run commands themselves.
- **Verify with counsel disclaimers** on every authority cite, every
  deadline, every statute reference. Carry the disclaimer through
  drafts and into final outputs.

## Workflow

### Phase 1 — Setup the case workspace

**Owner:** `scripts.init_case` CLI (no skill needed; the CLI is
self-guiding).
**What done looks like:** a directory outside the toolkit repo with
`evidence/`, `drafts/`, `complaint_packet/`, `provenance/`, `notes/`
subdirs, plus a fresh `CLAUDE.md` and `intake-answers.yaml`.
**Trigger to next phase:** the workspace is created.

If the user is in the toolkit repo itself and starting a real (non-
synthetic) case, refuse to put case materials in the repo (the CLI
guard rail does this automatically). Offer to run:

```
uv run python -m scripts.init_case --output ~/cases/<short-name> --git
```

The CLI's interactive intake covers Phase 2 inline. Skip to Phase 3
once `case-intake.yaml` exists.

### Phase 2 — Intake (situation classification)

**Owner skill:** `case-intake`.
**What done looks like:** `case-intake.yaml` written, `situation_type`
non-`unknown`, jurisdiction set, loss date set if there is a discrete
incident.
**Trigger to next phase:** the user confirms the classification reads
right.

If the situation classifies as `unknown`, hand off to
`situation-triage`. If the user is unsure of any field, accept blanks
— the downstream skills are designed to gracefully skip what they
can't compute.

### Phase 3 — Authorities lookup

**Owner skill:** `authorities-finder` (deterministic lookup against
`data/authorities.yaml`).
**Optional follow-up:** `authorities-reconcile` (web research +
reconciliation) when the local data is sparse for the user's
jurisdiction or when the situation has multiple plausible regulators.
**What done looks like:** the user knows which regulator(s) and which
secondary venues (state AG, federal CFPB/FTC, bar associations) apply
to their dispute, with disclaimer banners attached.
**Trigger to next phase:** the user has chosen a primary forum.

### Phase 3b — Trusted reference docs (optional, on-demand)

**Owner skill:** `trusted-sources`.
**What done looks like:** every statute, regulation, official policy,
and ToS the case will cite has a copy under `<case>/references/`,
with sidecar metadata recording where it came from (user-supplied,
fetched from a trusted source, or downloaded manually) and a
disclaimer banner.
**Trigger to next phase:** the user has the reference text they need
on disk, or has consciously deferred specific docs to acquire later
(some are best pulled closer to filing).

This phase is optional in the sense that not every case needs it (a
purely factual evidence packet may not cite outside text), but for
any complaint that quotes or relies on a specific statutory
provision, regulation, or ToS clause, the cited text should be in
`references/` *before* the complaint is drafted, not after — drafting
against the actual text catches paraphrase drift early.

The skill walks three independent acquisition paths (user-supplied
copy, project-known trusted source, constrained web search) and
cross-checks when more than one is available. See
[trusted-sources](../trusted-sources/SKILL.md) for the procedure.

### Phase 4 — Deadline computation

**Owner:** `scripts.intake.deadline_calc` CLI (no skill needed).
**What done looks like:** statute-of-limitations and notice deadlines
printed, each tagged `[VERIFY WITH COUNSEL]`.
**Trigger to next phase:** the user understands what dates they are
working against.

If the loss date is not yet known, skip this phase and revisit later.
If the situation/jurisdiction pair is not in `data/deadlines.yaml`,
say so and offer to fall back to the `authorities-web-research` skill
to find the rules manually.

### Phase 5 — Evidence intake

**Owner skill:** `evidence-intake`.
**Cross-cutting skill:** `provenance` (chain-of-custody discipline
applies whenever evidence is added).
**What done looks like:** raw evidence is in
`<case>/evidence/<kind>/raw/`, structured-and-readable derivatives
exist where the toolkit's three-layer ingesters apply (emails, PDFs,
HTML, screenshots, voicemails, SMS), and `.evidence-manifest.sha256`
covers everything.
**Trigger to next phase:** the user has nothing more to ingest right
now (the manifest can be re-run as more evidence arrives).

### Phase 6 — Drafting

**Cross-cutting skill:** `tone-modes` (always-on for any draft).
**Owner:** the user, supported by `scripts.letters.draft` for
templated correspondence (demand, FOIA, preservation, withdrawal,
cease-desist) and freehand markdown for the complaint narrative.
**What done looks like:** drafts in `<case>/drafts/` for everything
the packet will need: complaint narrative, position letters, opinion
letters, comparables, anything else the per-situation playbook calls
out.
**Trigger to next phase:** the user is ready to assemble exhibits.

For the complaint narrative specifically, refer to the relevant
playbook under `docs/playbooks/<situation_type>.md`. Honor the
read-aloud test from `tone-modes`.

### Phase 7 — Packet assembly

**Owner skill:** `packet-builder`.
**What done looks like:** `complaint_packet/packet-manifest.yaml` is
populated and validated, `scripts.packet.build` produces the merged
packet PDF plus per-exhibit standalones plus reference-document
appendices, and `scripts.provenance_bundle` produces the whole-packet
attestation YAML.
**Trigger to next phase:** the user has the packet PDFs in hand.

### Phase 8 — Publication safety

**Owner skill:** `going-public`.
**Sub-skill:** `pii-scrubber` for the PII pass specifically.
**What done looks like:** if (and only if) the user plans to share
case materials publicly or with anyone outside their counsel /
regulator pipeline, the four-scrubber sequence (PII → DOCX metadata
→ EXIF → git history) has been run with verification at each step.
**Trigger to next phase:** none — this is the last phase.

If the user is *only* filing with the regulator and not publishing
anywhere, you can skip this phase. Confirm that with the user
explicitly before skipping.

## Cross-cutting skills (always available)

- **`tone-modes`** — applies whenever Claude is about to draft
  user-facing language or is about to treat a script's output as
  final.
- **`docx-comment-roundtrip`** — applies when there is `.docx`
  feedback (real-world co-counsel comments, regulator markups,
  user's own review marks) that needs structured response cycles.

## Common pitfalls

- **Inventing authorities.** Never cite a regulator that is not in
  `data/authorities.yaml` or surfaced by the `authorities-web-research`
  skill. If the user asks "is there anyone else?", offer to run that
  skill rather than guessing.
- **Inventing deadlines.** Same rule — cite from `data/deadlines.yaml`
  or research them transparently. Every date carries
  `[VERIFY WITH COUNSEL]`.
- **Skipping `tone-modes`.** Internal reasoning may be casual mode;
  any outbound paragraph that lands in a draft should be lawyer mode
  by default and pass the read-aloud test.
- **Treating script output as oracle.** Scripts are scaffolds. If a
  classifier emits `unknown`, the user is not wrong — the rules are
  incomplete. Hand off to `situation-triage` rather than forcing a
  bad fit.
- **Forgetting publication safety.** If the user is going to share
  the packet anywhere outside the original-recipient pipeline,
  Phase 8 is not optional.
