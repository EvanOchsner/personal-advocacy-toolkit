---
name: provenance
description: Forensic provenance skill — joins evidence hashes, filesystem xattrs/mtimes, git history, and pipeline sidecars into a single report a non-technical reader can audit. Triggers when the user asks "where did this evidence come from" or prepares a provenance bundle for a regulator or attorney.
---

# provenance

Build a single report that answers, for every file in an evidence tree,
the four questions a regulator, attorney, or journalist will ask:

1. **What is the file?** (content hash — SHA-256)
2. **Where did it come from?** (filesystem xattrs — macOS WhereFroms /
   quarantine; source URL when present; ingest-pipeline sidecar)
3. **When did we receive it, and when has it been touched?**
   (filesystem mtime; git first-commit + last-commit timestamps)
4. **Who or what transformed it?** (ingestion pipeline — e.g. email
   `.eml` → canonical JSON → readable `.txt`; each step records its
   inputs, outputs, and tool version in a `<file>.meta.json` sidecar)

The skill wraps three scripts already in this repo:

- `scripts/evidence_hash.py` — content hashes, line manifest in shasum
  format.
- `scripts/provenance_snapshot.py` — xattr + mtime capture.
- `scripts/provenance.py` — joins hash manifest + latest snapshot + git
  log + pipeline sidecars into the unified report.

## When to invoke

Invoke this skill when:

- The user is preparing a regulator complaint and needs a provenance
  bundle to attach. (For the worked synthetic case,
  `examples/mustang-in-maryland/`, that is the MIA packet.)
- The user asks "how do I prove where this came from?"
- Counsel has asked for chain-of-custody documentation.
- Evidence is about to leave the workspace (hand-off to attorney,
  publication, subpoena response).

Do **not** invoke it for:

- A one-off "hash this file" request. Use `shasum -a 256` directly.
- Scrubbing metadata before publication — that is the
  `docx-comment-roundtrip` skill (for Word) or
  `scripts/publish/exif_scrub.py` / `scripts/publish/pdf_redact.py`.
  Provenance captures history; scrub removes it. Different job.

## Standard sequence

Run from the case root (e.g.
`examples/mustang-in-maryland/` for the worked synthetic case):

```
python -m scripts.evidence_hash --root evidence/
python -m scripts.provenance_snapshot --root evidence/
python -m scripts.provenance --root evidence/ --out provenance/provenance-report.json
```

Step-by-step:

1. **Hash manifest** (`scripts.evidence_hash`). One line per file under
   the evidence root, `<sha256>  <posix-relative-path>`. Shasum-compatible
   so any reader can verify it with `shasum -a 256 -c`.
2. **Snapshot** (`scripts.provenance_snapshot`). Captures filesystem
   xattrs (macOS `com.apple.metadata:kMDItemWhereFroms`,
   `com.apple.quarantine`) and mtimes to a timestamped file under
   `provenance/snapshots/`. This must run **before** any copy / tar /
   cloud sync operation that would strip xattrs.
3. **Unified report** (`scripts.provenance`). Joins the three sources
   and the pipeline sidecars into a single JSON document (or YAML with
   `--forensic`). Each row carries a verdict (`pass` / `warn` / `fail`)
   and reason codes, so the reader can skim verdicts and only drill in
   on warnings.

For the worked synthetic Mustang case, `provenance/provenance-report.json`
accompanies the MIA complaint packet. It is referenced by the packet's
manifest (see `examples/mustang-in-maryland/complaint_packet/packet-manifest.yaml`)
but is not itself an exhibit — it is a standing attestation of the
evidence tree's integrity.

## Verify-only mode

When the user asks "has anything in the evidence tree changed?":

```
python -m scripts.evidence_hash --verify --root evidence/
```

Exits 0 on a clean verify, non-zero on any mismatch. Use `--check`
instead of `--verify` to also flag untracked files under the root.

## Forensic mode (attorney / regulator handoff)

```
python -m scripts.provenance --root evidence/ --forensic \
  --out provenance/provenance-report.yaml
```

YAML output, macOS xattr plist decoders expanded (so a reader sees the
actual source URL from `kMDItemWhereFroms`, not a base64 blob). Pair
with a plain-English preamble that names the case and lists the tools
and versions the report was generated with.

## Reason codes a reader will see

The joined report tags each row with reason codes. The ones a
non-technical reader most often asks about:

- `no-snapshot` — the file exists in the hash manifest but was not
  present in the most recent snapshot. Usually means it was added after
  the snapshot was taken. Re-run `provenance_snapshot` and regenerate.
- `stale-snapshot` — the snapshot backing this row is older than
  ~30 days. Re-run the snapshot step.
- `xattr-stripped` — the file has no xattrs. On macOS this is expected
  for files created in-tree; for downloaded / received files it means
  provenance was lost before capture (tar, cloud sync, cross-OS copy).
  Note the limitation in the report preamble.
- `no-git-history` — the file is not tracked in git. Acceptable for
  ignored artifacts; flag-worthy for anything a complaint packet
  references.
- `hash-mismatch` — the file on disk no longer matches the hash
  manifest. Investigate before shipping anything.

## Do not

- Do not treat the SHA-256 manifest alone as provenance. Provenance
  joins hashes *with* the ingestion pipeline, git history, and
  filesystem xattrs. Any one of those alone is insufficient.
- Do not claim full-fidelity provenance on a filesystem that does not
  preserve xattrs across transfers. Note the limitation explicitly in
  the report preamble — a knowledgeable reader will look for that
  caveat.
- Do not run `provenance_snapshot` *after* a `mv` / `cp` / `tar` /
  cloud-sync step that would strip xattrs. Snapshot first, then move.
- Do not edit the hash manifest or snapshot files by hand. If
  something is wrong, regenerate — the manifests are the audit trail,
  and a hand-edit invalidates it.

## Related

- `scripts/evidence_hash.py` — content-hash manifest.
- `scripts/provenance_snapshot.py` — xattr + mtime capture.
- `scripts/provenance.py` — unified report builder.
- `scripts/publish/exif_scrub.py`, `docx_metadata_scrub.py`,
  `pdf_redact.py` — the *scrub* side; run after provenance capture,
  never before.
- Worked synthetic case: `examples/mustang-in-maryland/`.
