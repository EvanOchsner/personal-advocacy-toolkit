# Tutorial 03: Understanding the situation

> **Reference material, not legal advice.** Every output from the
> triage tools carries a "verify with counsel" tag. Use them to plan,
> not to file on.

By the end of this tutorial, you'll know:

- What situation-type your dispute falls under (insurance, medical
  billing, consumer scam, harassment, landlord-tenant, debt
  collection, employment retaliation).
- Which authorities plausibly have jurisdiction (state regulator,
  state AG, federal agencies).
- What deadlines are live (statute of limitations, notice windows).
- Whether the situation is a DIY regulator-complaint case or needs
  counsel now.

Running example: the
[`Mustang-in-Maryland`](../../examples/mustang-in-maryland/) synthetic
case.

```sh
cd examples/mustang-in-maryland
```

## 1. Classify the situation

If you don't already know what kind of dispute this is — or you're
not sure whether it's primarily one thing vs. another — run the
classifier:

```sh
cat > /tmp/answers.yaml <<'YAML'
claimant_name: "Delia Vance"
jurisdiction_state: "MD"
counterparty_kind: "insurer"
situation: "Classic-car agreed-value policy, insurer deducted from payout and moved vehicle to salvage during active negotiation."
loss_date: "2025-03-15"
YAML

python -m scripts.intake.situation_classify \
  --answers /tmp/answers.yaml \
  --out /tmp/case-intake.yaml
```

The classifier is rules-based (no LLM). It scores each candidate
situation by:

- `+2` for a counterparty_kind match (insurer, landlord, employer,
  etc.).
- `+1` for each keyword substring hit in the free-text "situation"
  field.

It writes a minimal `case-intake.yaml` tagged with which rules fired.
For Mustang-in-Maryland you should see:

```
situation_type: insurance_dispute
matched on: counterparty_kind=insurer, keyword='salvage'...
```

For your own case, inspect
[`data/situation_types.yaml`](../../data/situation_types.yaml) to see
the full list of recognized situations and their router rules.

## 2. Look up authorities

```sh
python -m scripts.intake.authorities_lookup \
  --situation insurance_dispute --jurisdiction MD
```

Expected output for the synthetic case:

- **Lead (state):** Maryland Insurance Administration (MIA) — regulator.
- **Secondary (federal):** Consumer Financial Protection Bureau (CFPB).
- **Secondary (federal):** FTC ReportFraud.
- **Secondary (state):** Maryland AG consumer-protection (verify
  populated vs stub status in current data).

Each entry tags its `status` as `populated` or `stub`. Stubs mean
"this is a placeholder until someone contributes real data" —
don't rely on them.

For JSON output (pipe into other tools):

```sh
python -m scripts.intake.authorities_lookup \
  --situation insurance_dispute --jurisdiction MD --format json
```

See
[`docs/concepts/authorities-and-regulators.md`](../concepts/authorities-and-regulators.md)
for the full landscape.

## 3. Compute deadlines

```sh
python -m scripts.intake.deadline_calc \
  --situation insurance_dispute --jurisdiction MD \
  --loss-date 2025-03-15
```

The calculator reads
[`data/deadlines.yaml`](../../data/deadlines.yaml), applies the
relevant clock to your `loss-date`, and emits every deadline tagged
`[VERIFY WITH COUNSEL]`.

You can add more reference dates for deadlines that aren't measured
from loss-date:

```sh
python -m scripts.intake.deadline_calc \
  --situation insurance_dispute --jurisdiction MD \
  --loss-date 2025-03-15 \
  --notice-of-loss 2025-03-16 \
  --denial-date 2025-05-09 \
  --last-act 2025-06-24
```

If the YAML defines a deadline whose clock starts on, say,
`denial_date`, the tool uses that date. If you didn't supply it, the
tool falls back to `loss-date` and flags the fallback in the output
(so you know which deadlines need a more specific anchor).

## 4. Read the matching playbook

With the situation classified, read the playbook:

- [`insurance-dispute.md`](../playbooks/insurance-dispute.md) (worked
  for MD; mechanics transfer to other states).
- Others:
  [`medical-billing.md`](../playbooks/medical-billing.md),
  [`consumer-scam.md`](../playbooks/consumer-scam.md),
  [`harassment-cyberbullying.md`](../playbooks/harassment-cyberbullying.md),
  [`landlord-tenant.md`](../playbooks/landlord-tenant.md),
  [`debt-collector.md`](../playbooks/debt-collector.md),
  [`employment-retaliation.md`](../playbooks/employment-retaliation.md).

Each playbook explains the core mechanic, the tool surface for that
situation, and the "populate-this" list to convert stub data to real
for your jurisdiction.

## 5. Render the dashboard

```sh
python -m scripts.status.case_dashboard \
  --intake case-facts.yaml \
  --manifest correspondence-manifest.yaml \
  --packet-dir complaint_packet/
```

<!-- TODO: verify after dogfood pass -->
(The dashboard expects an *evidence manifest yaml* with a list of
entries, not the SHA-256 manifest. For the synthetic case the
`correspondence-manifest.yaml` produced by Tutorial 02 serves; if
you don't have one yet, the dashboard still renders — just with an
empty evidence section.)

Expected output: a Markdown status document with:

- Header (caption, situation type, jurisdiction, loss date).
- Evidence counts by source type.
- Deadlines table (with `[VERIFY WITH COUNSEL]` tags).
- Packet validation status.
- Done / Pending checklist.

## 6. Decide: DIY regulator complaint or call counsel now?

Signals pointing to *file the regulator complaint yourself* first:

- Amount in dispute is below your state's small-claims threshold.
- Deadlines (SOL, notice windows) are > 90 days out.
- Core grievance is clean and well-documented (one core fact, not
  ten entangled ones).
- You have a regulator with clear jurisdiction.

Signals pointing to *call counsel now*:

- Any employment-retaliation situation (EEOC deadlines are brutal).
- Suit has been filed against you (collector, landlord).
- Deadlines are inside 90 days.
- Counterparty has institutional resources and represents a class
  pattern you may be part of.
- Damages are calculable and above small-claims threshold.
- Criminal conduct is plausibly involved (threats, fraud above a
  threshold, stalking).

The toolkit is designed to make you a **better client** either way —
the forensic audit trail, organized exhibits, and provenance report
shorten the intake call dramatically and let counsel assess your
case in minutes instead of hours.

## Where next

- [`04-building-a-packet.md`](04-building-a-packet.md) — assemble the
  complaint narrative + exhibits for filing.
- [`docs/playbooks/`](../playbooks/) — the matching playbook for your
  situation.
- [`docs/concepts/tone-modes.md`](../concepts/tone-modes.md) — before
  you write anything for the record.
