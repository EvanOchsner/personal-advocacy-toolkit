---
name: provenance
description: Forensic provenance skill — joins evidence hashes, filesystem xattrs/mtimes, git history, and pipeline sidecars into a single report a non-technical reader can audit. Triggers when the user asks "where did this evidence come from" or prepares a provenance bundle for a regulator or attorney.
---

# provenance

**PORT PENDING.** This skill is a stub. The authored source lives
in a private project (`lucy-repair-fight/.claude/skills/provenance/`)
that this Phase 4A session cannot read. The intent and the script
surface it wraps are well-defined below; a follow-up task should
pull the full SKILL.md contents from the source repo and replace
this stub.

## Script surface (already in this repo)

- `scripts/provenance.py` — joins four sources:
  1. SHA-256 manifest from `scripts/evidence_hash.py`.
  2. Most recent filesystem snapshot (xattrs + mtimes) under
     `provenance.snapshot_dir`.
  3. Git history per tracked file (first + last commit touching).
  4. Pipeline metadata sidecars (`<file>.meta.json`) left by the
     ingesters.

- `scripts/provenance_snapshot.py` — captures the xattrs + mtimes
  snapshot the first script reads.

## Minimal interim procedure

Until the full port lands, run this sequence when the user asks
for a provenance bundle:

```
python -m scripts.evidence_hash --root evidence/
python -m scripts.provenance_snapshot --root evidence/
python -m scripts.provenance --root evidence/ --out provenance-report.json
```

The output is designed for a non-technical reader (regulator,
attorney, journalist) to skim: one row per evidence file with every
derivable fact visible.

## Do not

- Do not treat the hash manifest alone as provenance. Provenance
  includes the ingestion pipeline metadata, the git history, and
  the filesystem xattrs (where supported).
- Do not claim full-fidelity provenance on a filesystem that
  doesn't preserve xattrs across transfers (tar, cloud sync,
  cross-OS copy). Note the limitation in the report.
