---
name: case-intake
description: Walk the user through populating a fresh case-intake.yaml from a blank slate — triggers when a user says they have a new dispute, grievance, or situation and no case-intake.yaml exists yet in the workspace.
---

# case-intake

Populate `case-intake.yaml` for a new matter by interviewing the user,
then let `scripts/intake/situation_classify.py` do the routing.

## When this skill fires

- The user describes a fresh dispute and there is no `case-intake.yaml`
  in the current working directory.
- The user explicitly asks to "start a new case" or "set up intake."

## Procedure

1. **Don't ask for everything at once.** The questionnaire below is
   driven by `data/situation_types.yaml`'s router. You only need six
   fields to get a usable first draft:
   - `claimant_name` — how the user wants to be named in paperwork.
   - `jurisdiction_state` — 2-letter US state where the user lives or
     where the loss occurred.
   - `counterparty_kind` — one of the router vocab values (insurer,
     landlord, employer, medical_provider, debt_collector, etc.).
     If the user isn't sure, ask them to describe the counterparty
     and pick the closest.
   - `situation` — one or two sentences in the user's own words.
     Don't paraphrase into lawyer mode; the classifier uses the
     user's keywords.
   - `loss_date` — ISO `YYYY-MM-DD` if there is a discrete incident.
     Optional for slow-rolling disputes.
   - `notes` — anything the user wants future-you to remember.

2. **Write the six answers to `intake-answers.yaml`** (a scratch file,
   not the final case-intake). Then run:

   ```
   uv run python -m scripts.intake.situation_classify \
       --answers intake-answers.yaml \
       --out case-intake.yaml
   ```

3. **Read back the classified `situation_type`** and confirm with the
   user. If the slug is `unknown`, the router didn't match — either
   the situation isn't yet covered in `data/situation_types.yaml` or
   the user's framing missed the keywords. Offer to retry with a
   different phrasing, or fall through to the `situation-triage`
   skill.

## Synthetic example

For the Maryland-Mustang example the answers file would look like:

```yaml
claimant_name: "Sally Ridesdale"
jurisdiction_state: "MD"
counterparty_kind: "insurer"
situation: >
  Classic-car insurer is deducting specialist-shop rates from a total-loss
  agreed-value payout and transferred the vehicle to salvage while
  negotiations were ongoing.
loss_date: "2025-03-15"
notes: "Agreed-value endorsement — CIM-AV-ENDT-2023."
```

Running the classifier against that yields `situation_type:
insurance_dispute`. That becomes the key for every downstream skill
(`authorities-finder`, `packet-builder`, letter templates).

## Definition of done

`case-intake.yaml` exists with at least the six core fields the user
answered, the classifier has produced a `situation_type` (or
`unknown` if nothing matched), and the user has confirmed the
classification reads right. If `unknown`, hand off to
`situation-triage`. Otherwise hand back to `pat-workflow` (which
proceeds to Phase 3 authorities lookup).

## Do not

- Do not fill in fields the user hasn't answered. Leave them blank; the
  schema tolerates partial records and other skills (`situation-triage`)
  will prompt for the rest later.
- Do not paste real names or numbers into example text you show the user.
  The example above is synthetic; use it, don't swap it.
- Do not skip the disclaimer banner at the top of `case-intake.yaml`.
  The classifier writes one; don't delete it.
