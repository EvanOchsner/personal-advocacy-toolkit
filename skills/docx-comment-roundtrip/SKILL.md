---
name: docx-comment-roundtrip
description: |
  Read all review comments in a .docx, classify each (factual / question /
  analysis / skip), dispatch specialist subagents to research and draft
  replies against PROJECT MATERIALS ONLY, reconcile multi-specialist
  responses, and write threaded replies as author "Claude". Use when the
  user asks to "reply to comments in this .docx", "round-trip the review
  pass on this draft", "process the comments on <file>.docx", or any
  similar phrasing.

  The skill has two faces: (1) the full LLM-driven reply workflow
  (this SKILL.md — router, F/Q/A specialists, reconciler, verify); and
  (2) a primitive comment-strip/restore round-trip that leaves no
  residuals in the zip (see "Primitive: comment extract/inject" below).
  Use the primitive when preparing a .docx for a counterparty; use the
  full workflow when replying to comments on an internal draft.
---

# `docx-comment-roundtrip` — driver playbook

## When to use

The user has a `.docx` with review comments and wants Claude to reply
where there's something substantive to say (verification of a fact,
answer to a question, sharp analytical take), and to leave a persistent
skip marker where there isn't (vent, non-sequitur, no project hook).
Replies are written threaded under each top-level comment as author
"Claude".

Trigger examples:

- "Reply to all the comments in `drafts/foo.docx`"
- "Round-trip the review pass on `proposal.docx`"
- "Process the new comments on the MIA complaint"
- "I added comments to the draft — handle them"

If the user wants something fundamentally different (accept tracked
changes, edit body text, resolve comments), this is the wrong skill.

## Hard rules

Restate these to subagents in their prompts.

1. **Project materials only.** No WebFetch, no WebSearch, no recalled
   facts from training. Specialists are spawned as the
   `project-materials-specialist` subagent type which has file-read
   tools only (Read / Grep / Glob / Bash), no network tools. The
   verify phase also greps replies for `http://` / `https://` as a
   belt-and-suspenders check.
2. **Reply, never resolve.** The skill never sets `w:done="1"` on any
   comment. The user closes threads.
3. **Body-text edits are opt-in only.** Default behavior is reply-only
   (no document text changes). Body-text edits — Word tracked changes
   or silent inline replacement — happen only when the user passes
   `--edit-mode tracked` or `--edit-mode silent`.
4. **Author identity is "Claude" by default.** Configurable via
   `--author` / `--initials`. The default matters for the
   "needs-reply = last commenter is not Claude" rule.
5. **Default is internal.** Run in `--internal-only` mode by default.
   When the user is about to hand the .docx to a lawyer, regulator,
   opposing counsel, or unknown recipient, pass `--for-external-use`
   to trigger the publication-safety advisory.
6. **Citations are mandatory.** Every substantive F or A reply that
   cites a project source ends with a `Source: <path>:<line>  sha256=<hex>@<provenance>`
   footer. The driver rejects replies that mention a file path
   without a matching footer.

## Tag grammar (user-side)

Users can pre-route by prefixing a comment with a tag. Tags are
case-insensitive. The trailing colon is optional.

| Form | Routes to | Behavior |
|------|-----------|----------|
| `F`, `F:`, `F: <body>` | Factual | Verify against materials. |
| `Q`, `Q:`, `Q: <body>` | Question | Answer from materials. |
| `A`, `A:`, `A: <body>` | Analysis | Reasoned take grounded in materials. |
| `S`, `S:`, `S: <body>` | (skip) | Write `[skip — user-tagged]` marker. |
| `F+Q`, `Q+A`, `F+A`, `F+Q+A` | Multiple → reconciler | Each specialist runs; reconciler merges. |
| (anything else) | Router | Router classifies. |

A tag matches only at the start of the comment. `F:` mid-text is
ignored.

## Persistent skip markers

When a comment is judged not to warrant a substantive reply, Claude
writes:

    [skip — <one-line reason>]

(em-dash, not hyphen). This makes Claude the last commenter on the
thread, so re-running the skill naturally skips it. Users re-trigger
by deleting the skip marker.

## Edit modes

| `--edit-mode` | With `edit_proposal` | Without |
|---|---|---|
| `reply` (default) | Synthesize "Suggested edit: «X» → «Y». <rationale>" as prose comment; no doc-text change. | Normal threaded comment. |
| `tracked` | Apply Word tracked-change markup at find target; write paired rationale comment. | Normal threaded comment. |
| `silent` | Replace text directly in `<w:t>`; write paired rationale comment. | Normal threaded comment. |

Guardrails (all must hold; failure downgrades the entry to prose):

1. `find` occurs **exactly once** in the anchor text.
2. `find` falls entirely within a single `<w:r>` whose only
   text-bearing element is one `<w:t>`.
3. `find` is non-empty. (For pure deletion, set `replace: ""`.)

Q specialist replies never carry `edit_proposal`.

## Commenter roles (`.claude-commenters.yaml`)

Optional file at `<PROJECT_ROOT>/.claude-commenters.yaml` tells the
skill who each commenter is. Format:

```yaml
commenters:
  - match:
      author: "Elena Rojas"
    role: lawyer
  - match:
      author: "Carlos Mendez"
      initials: "CM"
    role: opposing-counsel
  - match:
      author: "MIA Intake"
    role: regulator
  - match:
      author: "Sally Ridesdale"
    role: complainant
  - match:
      author: "Claude"
    role: self
default_role: unknown
```

Role → tone rule:

| Role | Register |
|---|---|
| `lawyer` | Precise legal. Cite exact paragraph + statute. Don't hedge. |
| `regulator` | Formal, minimal, factual. Answer only what was asked. |
| `complainant` | Plain language. Short paragraphs. Answer fully. |
| `opposing-counsel` | Literal-only. Never concede. Never volunteer. Driver appends `[risk: check with counsel before sending]` automatically. |
| `self` | Never reply — Claude's own prior turns. Router always skips these. |
| `unknown` / default | Plain language, fully sourced. |

Tone lookup uses the **latest commenter in the thread**, not the
original — so a complainant responding to a lawyer's thread gets a
complainant-tone reply.

## Inputs

**Required**
- Path to a `.docx` file with review comments.

**Optional**
- `--author` (default: `Claude`) — author identity for replies.
- `--initials` (default: `C`) — initials for replies.
- `--out` (default: overwrites the input) — alternative output path.
- `--edit-mode {reply,tracked,silent}` (default: `reply`).
- `--commenters <path>` (default: `<PROJECT_ROOT>/.claude-commenters.yaml`).
- `--for-external-use` / `--internal-only` (default: `--internal-only`) —
  publication-safety advisory.
- `--dry-run` — execute through routing + specialist dispatch but skip
  apply/repack.
- `--keep-artifacts` — leave `.tmp/<stem>_*` artifacts after a
  successful run.

## Phase-by-phase execution

Per-phase scratch artifacts go under `<PROJECT_ROOT>/.tmp/<docx-stem>_*`.

### Phase 0 — Preflight

1. Verify the input `.docx` exists.
2. Refuse if `<input_dir>/.~lock.<filename>#` exists (file is open in
   another editor; writing would corrupt). Tell the user to close it.
3. Discover **project root**: walk up from the docx until you find a
   `.git` directory or a `CLAUDE.md`. Use that path as `PROJECT_ROOT`.
   If neither exists, use the docx's parent directory and warn.
4. Note whether `<PROJECT_ROOT>/CLAUDE.md` exists (specialists will
   read it for context).
5. Unpack the docx:
   ```bash
   uv run python -m scripts.publish.docx_unpack <input.docx> .tmp/<stem>_unpacked/
   ```

### Phase 1 — Catalog

```bash
uv run python -m scripts.publish.docx_catalog .tmp/<stem>_unpacked/ \
  --claude "<author>" \
  --commenters <PROJECT_ROOT>/.claude-commenters.yaml \
  --out .tmp/<stem>_catalog.json
```

The script reports `threads_total=N threads_needing_reply=M` to stderr.

**Short-circuit:** if `threads_needing_reply == 0`, print "Nothing to
do — N threads, all current with Claude reply" and exit (still clean
up on success).

### Phase 2 — Routing

Read `.tmp/<stem>_catalog.json`. Split `needs_reply` into:

- **Tagged entries** (`tag` non-empty): route deterministically.
  - `S` → skip with reason `"user-tagged S:"`.
  - `F` / `Q` / `A` → single specialist.
  - `F+Q` / `F+A` / `Q+A` / `F+Q+A` → multiple.
- **Entries with `latest_author_role == "self"`**: skip with reason
  `"author is self"`.
- **Entries with `prior_substantive_reply`**: hand to router, which may
  pre-skip re-asks.
- **Remaining untagged entries**: hand to router.

If there are any router-eligible entries:

1. Write the slice to `.tmp/<stem>_router_input.json`.
2. Spawn a `project-materials-specialist` subagent with the prompt at
   `skills/docx-comment-roundtrip/prompts/router.md`, substituting
   `{{PROJECT_ROOT}}`, `{{INPUT_PATH}}`, `{{OUTPUT_PATH}}`.

Merge the router's output with the deterministic tagged routes into
`.tmp/<stem>_routing.json`.

### Phase 3 — Specialist dispatch (parallel)

For each non-empty specialist (F, Q, A) that has at least one
assigned comment, build the input slice and spawn the corresponding
specialist. **Spawn all active specialists in parallel** (single
message, multiple `Agent` tool calls).

For each specialist X in {F, Q, A}:

1. Collect entries routed to X.
2. Build per-entry input:
   ```json
   {
     "thread_root_id": ...,
     "latest_comment_id": ...,
     "latest_author_role": ...,
     "stripped_text": ...,
     "anchor_text": ...,
     "thread_context": [...],
     "prior_substantive_reply": {...}
   }
   ```
3. Write slice to `.tmp/<stem>_specialist_<X>_input.json`.
4. Spawn `project-materials-specialist` subagent with prompt
   `prompts/<factual|question|analysis>_specialist.md`.

Outputs land at `.tmp/<stem>_specialist_<X>_output.json`.

### Phase 4 — Reconciliation

For each `thread_root_id` that was multi-routed, gather responses.

- **All specialists skipped** → single skip marker,
  `reply_text = "[skip — " + combined_reasons + "]"`.
- **Otherwise** → reconciler subagent. Write cases to
  `.tmp/<stem>_reconciler_input.json`, spawn with
  `prompts/reconciler.md`, output to
  `.tmp/<stem>_reconciler_output.json`.

For single-route comments, take the specialist's output as-is.

Build merged replies at `.tmp/<stem>_replies_merged.json`:

```json
[
  {
    "thread_root_id": <int>,
    "reply_text": "<final reply or skip marker>",
    "edit_proposal": {"find": "...", "replace": "..."}
  }
]
```

`edit_proposal` is optional per entry. Order: ascending by
`thread_root_id`.

### Phase 5 — Apply

If `--dry-run`, stop here.

```bash
uv run python -m scripts.publish.docx_apply_replies \
  .tmp/<stem>_unpacked/ \
  .tmp/<stem>_replies_merged.json \
  --author "<author>" --initials "<initials>" \
  --edit-mode "<reply|tracked|silent>" \
  --commenters <PROJECT_ROOT>/.claude-commenters.yaml \
  [--for-external-use]
```

Stats line to stderr:

    apply_replies: applied N replies, M tracked-edits, K silent-edits, D downgrades, F failures

Downgrades are non-fatal (guardrail rejected the edit; prose comment
written). Failures → fail loud, preserve `.tmp/`.

If `--for-external-use`, the advisory prints the set of publication-
sensitive roles present in the threads. The driver follows up by
asking the user whether to run `pii_scrub` + `docx_metadata_scrub`
before handoff.

Repack:

```bash
uv run python -m scripts.publish.docx_pack .tmp/<stem>_unpacked/ <output.docx> \
  --original <input.docx>
```

### Phase 6 — Verify

Re-unpack the output:

```bash
uv run python -m scripts.publish.docx_unpack <output.docx> .tmp/<stem>_verify/
uv run python -m scripts.publish.docx_catalog .tmp/<stem>_verify/ --claude "<author>" \
  --out .tmp/<stem>_verify_catalog.json
```

Assertions (fail loud on any miss):

1. `comments` count = (original count) + (replies applied).
2. Every Claude reply has a non-empty `para_id_parent`.
3. Every Claude reply's `para_id_parent` matches some existing
   comment's `para_id`.
4. In `document.xml`: count of `<w:commentRangeStart` =
   `<w:commentRangeEnd` = `<w:commentReference`.
5. Spot-check 3 random replies' text matches the merged list.
6. **If `--edit-mode tracked`**: Claude-authored `<w:ins>` / `<w:del>`
   counts match the applied-edits tally. Use
   `docx_edit_ops.count_claude_revisions`.
7. **If `--edit-mode silent`**: 3 random applied-edit `find` strings
   no longer appear; corresponding `replace` strings now do.
8. **Citation-footer assertion.** Every Claude-authored substantive
   reply that names a file path contains a matching
   `Source: … sha256=…@…` line.
9. **External-URL assertion.** No Claude-authored reply contains
   `http://` or `https://` unless listed in
   `<PROJECT_ROOT>/.claude-citation-allowlist.txt` (one URL prefix
   per line; missing file = empty allowlist).
10. **Opposing-counsel suffix assertion.** For every thread whose
    `last_author_role == "opposing-counsel"`, the applied reply ends
    with `[risk: check with counsel before sending]`.

### Phase 7 — Report

Print to the user:

- Total replies written (substantive vs. skip markers).
- Breakdown by specialist (F / Q / A / multi).
- **Findings worth surfacing**:
  - Discrepancies (F specialist `discrepancy` outcomes).
  - Gaps (`gap` / `outreach-blocked`).
  - Contradictions (reconciler `had_contradiction: true`).
- Skipped threads with reasons.
- Path to the output `.docx`.

### Phase 8 — Cleanup (success only)

If all phases succeeded and `--keep-artifacts` was not passed:

```bash
rm -rf .tmp/<stem>_unpacked/ .tmp/<stem>_verify/
rm -f .tmp/<stem>_catalog.json .tmp/<stem>_router_input.json \
      .tmp/<stem>_router_output.json .tmp/<stem>_routing.json \
      .tmp/<stem>_specialist_*_input.json .tmp/<stem>_specialist_*_output.json \
      .tmp/<stem>_reconciler_input.json .tmp/<stem>_reconciler_output.json \
      .tmp/<stem>_replies_merged.json .tmp/<stem>_verify_catalog.json
```

(Standalone Bash call, per user-global CLAUDE.md rule for destructive
ops.)

On any failure earlier, skip cleanup.

## Failure modes and recovery

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Lock file present | Phase 0 stat | Refuse; tell user to close in editor |
| No comments needing reply | Phase 1 short-circuit | "Nothing to do"; clean up; exit 0 |
| Router invalid JSON | Phase 2 parse | Re-run router once with output-format reminder; fail if still invalid |
| Specialist invalid JSON | Phase 3 parse | Same: re-run once, then fail |
| Specialist references unknown `thread_root_id` | Phase 3 validation | Drop entry, warn, continue |
| Reconciler reply for non-multi-routed comment | Phase 4 validation | Drop entry, warn, continue |
| `apply_replies.py` parent_id not found | Phase 5 stderr | Fail loud, preserve `.tmp/` |
| Edit `find` fails guardrail | Phase 5 `DOWNGRADE` | Non-fatal; prose "Suggested edit" comment |
| Citation footer missing when file cited | Phase 5 `ApplyError` | Fail loud; specialist must re-draft |
| Repack validation fails | Phase 5 pack.py | Fail loud; preserve `.tmp/` |
| Verify assertion fails | Phase 6 | Fail loud; preserve both `unpacked/` and `verify/` |
| External URL in reply | Phase 6 assertion 9 | Fail loud; specialist violated project-materials-only rule |

## Primitive: comment extract/inject

A secondary entry point — unrelated to the LLM reply workflow — lives
at `scripts/publish/docx_comment_roundtrip.py`. It strips every
`<w:comment>` and its anchor elements out of a `.docx` into a YAML
sidecar and emits a cleaned `.docx` with all residuals gone (including
`commentsExtended.xml`, `commentsIds.xml`,
`commentsExtensible.xml`, the content-type override, and the rels
entry). Use this when preparing a `.docx` for a counterparty.

```bash
# Strip all comments; keep sidecar to restore later.
uv run python -m scripts.publish.docx_comment_roundtrip \
    --extract \
    --in drafts/demand-letter.docx \
    --out out/demand-letter-clean.docx \
    --sidecar out/demand-letter-comments.yaml

# Restore onto the stripped copy.
uv run python -m scripts.publish.docx_comment_roundtrip \
    --inject \
    --in out/demand-letter-clean.docx \
    --sidecar out/demand-letter-comments.yaml \
    --out drafts/demand-letter-restored.docx
```

This primitive does NOT invoke the LLM workflow. It's pure OOXML
surgery.

## Related

- `scripts/publish/docx_metadata_scrub.py` — `dc:creator` etc.
- `scripts/publish/exif_scrub.py` — image EXIF scrub.
- `scripts/publish/pdf_redact.py` — PDF redaction.
- `scripts/publish/pii_scrub.py` — PII scrub across packet sources.
- `skills/going-public/` — orchestrates the full publication-safety
  sequence for an external hand-off.

## Prompt substitution

Before passing to the Agent tool, substitute these tokens:

| Token | Meaning |
|-------|---------|
| `{{PROJECT_ROOT}}` | Absolute path to discovered project root |
| `{{INPUT_PATH}}` | Absolute path to the JSON file the subagent reads |
| `{{OUTPUT_PATH}}` | Absolute path to the JSON file the subagent writes |

Plain string replace. Never embed JSON in the prompt; always go
through a file.

## Worked invocation example

User: "Reply to all the new comments on `drafts/foo.docx`"

Driver:

1. Phase 0: locate `drafts/foo.docx`, check no lock file, walk up to
   project root (where CLAUDE.md lives), unpack to
   `.tmp/foo_unpacked/`.
2. Phase 1: extract catalog → 12 threads, 4 need reply (3 untagged,
   1 tagged `F:`, 1 with prior_substantive_reply).
3. Phase 2: route 1 tagged → F. 1 pre-skipped as re-ask. Spawn router
   for 2 untagged → 1 → F, 1 → Q. Merged routing: 2 to F, 1 to Q,
   1 skip.
4. Phase 3: parallel — F-specialist (2 comments), Q-specialist (1
   comment). Two Agent calls in one message.
5. Phase 4: no multi-routed → no reconciler. Merged list: 3
   substantive + 1 skip = 4 entries.
6. Phase 5: apply 4 replies, repack to `drafts/foo.docx`.
7. Phase 6: verify all 10 assertions pass.
8. Phase 7: report — "4 replies (3 substantive, 1 skip). 0
   discrepancies. Output: `drafts/foo.docx`".
9. Phase 8: clean up `.tmp/foo_*`.
