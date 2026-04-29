---
name: provenance
description: Forensic provenance skill — joins evidence hashes, filesystem xattrs/mtimes, git history, and pipeline sidecars into a single report a non-technical reader can audit. Triggers when the user asks "where did this evidence come from" or prepares a provenance bundle for a regulator or attorney.
---

# provenance

Build a single report that answers, for every file the user asks
about, the four questions a regulator, attorney, or journalist will
ask:

1. **What is the file?** (content hash — SHA-256)
2. **Where did it come from?** (filesystem xattrs — macOS WhereFroms
   URLs + quarantine; source URL when present; ingest-pipeline
   sidecar)
3. **When did we receive it, and when has it been touched?**
   (filesystem mtime; git commit trail — every commit that touched
   the file, classified as `initial` / `content` / `rename-or-metadata`)
4. **Who or what transformed it?** (ingestion pipeline — e.g. email
   `.eml` → canonical JSON → readable `.txt`; each layer visible
   through a config-driven dispatcher)

The skill wraps four scripts in this repo:

- `scripts/evidence_hash.py` — content hashes, line manifest in
  shasum format.
- `scripts/provenance_snapshot.py` — xattr + mtime capture.
- `scripts/provenance.py` — **per-file** forensic report (6 sections,
  human or YAML output).
- `scripts/provenance_bundle.py` — **whole-packet** attestation: runs
  the per-file tool over every manifest entry and aggregates.

## Per-file vs bundle

These are different tools for different questions.

- **`provenance PATH`** — use when the user asks about a *specific
  file*: "where did this exhibit come from?", "is this file clean?",
  "what's the history on `evidence/…`?". Produces the rich 6-section
  report and flags any integrity concerns inline.
- **`provenance_bundle --manifest M`** — use when the user is
  *preparing a regulator/attorney handoff* and wants a single
  attestation document for a whole packet of evidence. Produces one
  YAML file with per-file sections inline and a top-level
  `verdict_counts` summary.

If in doubt, start with `provenance PATH` on the specific file the
user named. The bundle is for "everything at once", not exploration.

## When to invoke

Invoke this skill when:

- The user is preparing a regulator complaint and needs a provenance
  bundle to attach. (For the worked synthetic case,
  `examples/maryland-mustang/`, that is the MIA packet.)
- The user asks "how do I prove where this came from?" or "is this
  file still intact?"
- Counsel has asked for chain-of-custody documentation.
- Evidence is about to leave the workspace (hand-off to attorney,
  publication, subpoena response).
- The user mentions "lawyer", "regulator", "attorney", "counsel",
  "export", "handoff", or a specific regulator acronym (MIA, CDI,
  CFPB, etc.) — in that case, prefer `--forensic` (YAML output) for
  a structured format the recipient can parse.

Do **not** invoke it for:

- A one-off "hash this file" request. Use `shasum -a 256` directly.
- Scrubbing metadata before publication — that's the
  `docx-comment-roundtrip` skill (for Word) or
  `scripts/publish/exif_scrub.py` / `scripts/publish/pdf_redact.py`.
  Provenance **captures** history; scrub **removes** it. Different
  job, different time in the workflow (capture first, scrub second).

## How to reply — hard rules

These are the contract. Other skills get by without them; this one
can't.

1. **Run the script first.** Capture the full output. Do not
   paraphrase from memory, invent fields, or describe what the output
   "would look like." The script is the source of truth for every
   fact in your reply.
2. **For reports under ~60 lines, reproduce the output verbatim.** A
   regulator / attorney / non-technical reader needs to see exactly
   what the tool said, not a summary. For longer reports, reproduce
   the Verdict line, the Flags block, and any section the user is
   asking about.
3. **Narrate each ⚠ flag in one sentence** using the table below.
   Say what it means and whether it's expected in the user's context.
4. **Do not reimplement the script's logic in natural language.** If
   a section is missing or a flag seems wrong, call it out explicitly
   — do not paper over with a summary. If the user's claim conflicts
   with the script's output, point at the script's output, not at
   your own reasoning.
5. **Do not run anything destructive.** The per-file tool and bundle
   are both read-only. If the user asks to "fix" a flagged issue,
   surface the relevant tool (`evidence_hash.py`,
   `provenance_snapshot.py`, or a commit) and let the user run it.

## ⚠ flag reference

When the script flags a warning, use this table to narrate it for the
user. The third column is written for a non-technical reader.

| Flag code | What the script means | How to narrate it |
|---|---|---|
| `content change(s) after placement` (git trail) | The file was modified after its initial commit under `evidence/`. For a real evidence file this is a serious red flag. | "This file was edited after it was recorded as evidence. Name the commit and ask whether the change was intentional — evidence files are supposed to be write-once." |
| `HASH MISMATCH` (hash manifest) | The recorded SHA-256 disagrees with what's on disk right now. | "The file on disk no longer matches the hash we recorded. Something changed the file without updating the manifest. Investigate before relying on this file." |
| `not recorded in manifest` | The file is under `evidence/` but no SHA-256 was captured for it. | "This file hasn't been hashed yet. Run `uv run python -m scripts.evidence_hash` to record it before using it in a packet." |
| `no git history / not tracked` | The file isn't committed to version control. | "This file isn't yet committed, so there's no durable timestamp on it. Acceptable for work-in-progress; flag-worthy for anything a complaint packet references." |
| `no download provenance` | No live xattr on disk AND no historical snapshot for this basename. | "We don't know how this file arrived — no download URL, no quarantine timestamp. Probably copied through a process that strips xattrs (tar, cloud sync, AirDrop, screenshot). Weaker paper trail than a direct download." |
| `no live xattr; snapshot available` | The file's live xattrs were stripped but we have a historical snapshot. | "The xattrs got removed at some point — probably by a copy or sync. The snapshot we took earlier still records where it came from; use that as the durable record." |
| `no sibling .json / .md / …` (pipeline section) | The pipeline expected a companion file that isn't there. | "The ingestion pipeline should have produced a sibling file for this one but didn't. Either the pipeline step was skipped or the file was added outside the pipeline. May or may not matter depending on the file's role." |
| `not in catalog` (policy/README or similar) | The path-specific catalog doesn't mention this file. | "This file is in a directory that's supposed to be catalogued, but it's not in the catalog. Usually means the catalog wasn't updated when the file was added." |

Flags not in this table: read the script's wording literally and say
what it said. Don't invent a narrative.

## How to run it

Per-file deep dive (human report):

```
uv run python -m scripts.provenance PATH
```

Per-file deep dive (YAML for regulator / attorney):

```
uv run python -m scripts.provenance PATH --forensic
```

Per-file verify-only (silent unless warnings; exit 1 on any ⚠):

```
uv run python -m scripts.provenance PATH --verify
```

Whole-packet attestation bundle:

```
uv run python -m scripts.provenance_bundle \
  --manifest PATH_TO_MANIFEST \
  --out attestation.yaml
```

Configuration — `--hash-manifest`, `--snapshot-dir`,
`--evidence-root`, `--pipeline-config`, `--repo-root` — all default
from `advocacy.toml` or a sensible fallback (e.g. manifest's sibling
`evidence/` dir). Override explicitly when working against a non-
default location (the Mustang example in particular).

## Standard provenance-capture sequence

Run from the repo root, before doing anything that might strip
xattrs:

```
uv run python -m scripts.evidence_hash --root <evidence-tree>
uv run python -m scripts.provenance_snapshot --root <evidence-tree>
# Then, later, when preparing a handoff:
uv run python -m scripts.provenance_bundle --manifest <path-to-.sha256> --out bundle.yaml
```

Order matters. Hash before snapshot so the snapshot covers the
committed state. Snapshot **before** any `mv` / `cp` / `tar` /
cloud-sync step — those operations strip xattrs, destroying the
most valuable download provenance on macOS.

## Do not

- Do not treat the SHA-256 manifest alone as provenance. Provenance
  joins hashes *with* the ingestion pipeline, git history, and
  filesystem xattrs. Any one of those alone is insufficient.
- Do not claim full-fidelity provenance on a filesystem that doesn't
  preserve xattrs across transfers. Note the limitation explicitly in
  the report preamble — a knowledgeable reader will look for that
  caveat.
- Do not run `provenance_snapshot` *after* a `mv` / `cp` / `tar` /
  cloud-sync step that would strip xattrs. Snapshot first, then move.
- Do not edit the hash manifest or snapshot files by hand. If
  something is wrong, regenerate — the manifests are the audit
  trail, and a hand-edit invalidates it.
- Do not paraphrase or re-derive the script's output. Reproduce it.

## Related

- `scripts/evidence_hash.py` — content-hash manifest (+ `--verify`).
- `scripts/provenance_snapshot.py` — xattr + mtime capture.
- `scripts/provenance.py` — per-file report builder.
- `scripts/provenance_bundle.py` — whole-packet aggregator.
- `data/pipeline_dispatch.yaml` — registry of pipeline handlers
  (email / catalog-README / YAML-frontmatter-sibling).
- `scripts/publish/exif_scrub.py`, `docx_metadata_scrub.py`,
  `pdf_redact.py` — the *scrub* side; run after provenance capture,
  never before.
- Worked synthetic case: `examples/maryland-mustang/`.
