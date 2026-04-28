# Tutorial 01: Setting up your case

> **Reference material, not legal advice.** This tutorial walks you
> through the mechanics. Every step that produces a date, a deadline,
> or an authority reference carries a "verify with counsel" caveat.

This tutorial takes you from "I cloned the repo" to "my evidence tree
is hashed, my case facts are captured, and I know which authorities
to look at next." It uses the
[`Maryland-Mustang`](../../examples/maryland-mustang/) synthetic
case as the running example so you can see every command produce real
output before you point it at your own situation.

Expected time: 20-30 minutes.

## 0. Prerequisites

- Python 3.11 or 3.12 (uv will provision it if missing).
- `git` on your PATH.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) installed,
  and `uv sync` run from the repo root.

```sh
git clone https://github.com/EvanOchsner/personal-advocacy-toolkit.git
cd personal-advocacy-toolkit
uv sync
```

## 1. Pick a working directory for your case

Everything case-specific goes in a separate directory. Two options:

**Option A — use the synthetic example to learn.** Skip step 2 and
just `cd examples/maryland-mustang/`. All commands below assume
this for the demo.

**Option B — start a real case.** Create a fresh directory *outside*
this repo (so the repo stays upgrade-able):

```sh
mkdir -p ~/cases/my-case && cd ~/cases/my-case
git init
cp /path/to/personal-advocacy-toolkit/advocacy.toml.example advocacy.toml
cp /path/to/personal-advocacy-toolkit/templates/CLAUDE.md.template CLAUDE.md
mkdir -p evidence drafts complaint_packet
```

The rest of this tutorial uses the synthetic case as an example. The
commands are identical against your own workspace once you've
populated `evidence/` and `case-facts.yaml`.

## 2. Read the case-context file

From inside the example directory:

```sh
cd examples/maryland-mustang
cat CLAUDE.md
cat case-facts.yaml
```

`CLAUDE.md` is a two-paragraph situation summary a fresh Claude Code
session reads automatically. `case-facts.yaml` is the structured fact
sheet that drives the letter templates, the dashboard, and the
deadline calculator.

For your own case, start from
[`templates/CLAUDE.md.template`](../../templates/CLAUDE.md.template)
and populate the fields against your situation. See
[`docs/concepts/tone-modes.md`](../concepts/tone-modes.md) for the
writing conventions.

## 3. Run the evidence hash manifest

The single most important property of your evidence is that a third
party can tell nothing has changed since you collected it. Build the
SHA-256 manifest:

```sh
uv run python -m scripts.evidence_hash \
  --root evidence \
  --manifest .evidence-manifest.sha256
```

Output: "wrote N entries to .evidence-manifest.sha256" where N is the
file count under `evidence/`. The manifest is a plain-text file, one
line per file:

```
<sha256-hex>  <relative-path>
```

Anyone can re-run `shasum -a 256 evidence/**/*` and compare to this
manifest to prove nothing has been edited.

Verify the manifest against the tree (no rewriting):

```sh
uv run python -m scripts.evidence_hash --root evidence --manifest .evidence-manifest.sha256 --verify
```

Verify *and* flag untracked files:

```sh
uv run python -m scripts.evidence_hash --root evidence --manifest .evidence-manifest.sha256 --check
```

Full explanation in
[`docs/concepts/evidence-integrity.md`](../concepts/evidence-integrity.md).

## 4. Capture the xattr snapshot

On macOS especially, Safari and Mail write the original source URL
(`com.apple.metadata:kMDItemWhereFroms`) into every file they
download. That is forensic gold — but git doesn't track xattrs. The
snapshot tool captures them into a timestamped JSON file under
`provenance/snapshots/` that *can* be committed:

```sh
uv run python -m scripts.provenance_snapshot --root evidence
```

Output: "wrote N entries to provenance/snapshots/<UTC-timestamp>.json".

On Linux the xattr block is usually empty; that's fine. The snapshot
still records size, mtime, and SHA-256.

## 5. Install the pre-commit immutability hook (optional but recommended)

If you're keeping your case in a git repo, install the hook so that
future commits cannot silently modify files under `evidence/`:

```sh
bash scripts/hooks/install_hooks.sh
```

Additions are allowed. Edits and deletions are refused. If you
genuinely need to override, set
`ADVOCACY_ALLOW_EVIDENCE_MUTATION=1` for that one commit — the
environment-variable form ensures the override shows up in shell
history.

## 6. (Optional) Classify your situation

If you haven't yet decided what situation-type your dispute falls
under, run the classifier. This is useful when you haven't framed
the problem yet. For the synthetic case we already know it's
`insurance_dispute`, but try it anyway:

```sh
# Create a minimal answers file
cat > /tmp/answers.yaml <<'YAML'
claimant_name: "Sally Ridesdale"
jurisdiction_state: "MD"
counterparty_kind: "insurer"
situation: "Classic-car agreed-value policy, insurer deducted from payout and moved vehicle to salvage during negotiation."
loss_date: "2025-03-15"
YAML

uv run python -m scripts.intake.situation_classify \
  --answers /tmp/answers.yaml \
  --out /tmp/case-intake.yaml
```

The classifier scores situations against the
[`data/situation_types.yaml`](../../data/situation_types.yaml) rules
and writes a minimal `case-intake.yaml`. You can then hand-edit the
output to add richer facts (see `case-facts.yaml` in the synthetic
example for what a fully-populated intake looks like).

## 7. Look up authorities and deadlines

```sh
uv run python -m scripts.intake.authorities_lookup \
  --situation insurance_dispute --jurisdiction MD

uv run python -m scripts.intake.deadline_calc \
  --situation insurance_dispute --jurisdiction MD \
  --loss-date 2025-03-15
```

Every date returned is tagged `[VERIFY WITH COUNSEL]`. Use the
output to plan — never to file on.

## Where next

- [`02-ingesting-evidence.md`](02-ingesting-evidence.md) — put emails,
  SMS, voicemails, and web captures into the three-layer pipeline.
- [`03-understanding-the-situation.md`](03-understanding-the-situation.md)
  — decide what playbook fits and whether to escalate to counsel.
- [`04-building-a-packet.md`](04-building-a-packet.md) — assemble the
  complaint packet for filing.
- [`05-going-public-safely.md`](05-going-public-safely.md) — only if
  you decide to publish a sanitized derivative.

Or jump to the full synthetic walkthrough:
[`examples/maryland-mustang/WALKTHROUGH.md`](../../examples/maryland-mustang/WALKTHROUGH.md).
