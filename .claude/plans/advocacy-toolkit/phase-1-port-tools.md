# Phase 1 — Port & generalize existing tools

Three parallel tracks. Each track delivers generalized code + unit tests
against the synthetic case (or temporary fixtures if Phase 2 hasn't
produced its pieces yet) + short concept/tutorial docs.

Source of truth for the tool mapping: §Tool inventory in the master plan.

## Agent 1A — Evidence-integrity track

**Files to port** (from `/Users/evanochsner/workplace/lucy-repair-fight/scripts/`):

- `hash_evidence.py` → `scripts/evidence_hash.py` (add `--root` flag,
  drop hardcoded `evidence/`, read config from `advocacy.toml` or CLI).
- `provenance.py` → `scripts/provenance.py` (parameterize manifest path
  and snapshot dir).
- `refresh_provenance_snapshot.py` → `scripts/provenance_snapshot.py`.
- `pre-commit` + `install_hooks.sh` → `scripts/hooks/` (config-driven
  protected paths, not hardcoded `evidence/`).

**Also:** wire `.pre-commit-config.yaml` at repo root to call the hook,
author `docs/concepts/evidence-integrity.md` + `docs/concepts/chain-of-custody.md`,
initialize `git` once the hook is ready.

## Agent 1B — Correspondence-ingest track

- `process_eml.py` → `scripts/ingest/email_eml_to_json.py` (drop
  claim-number hardcoding; no coupling to the manifest tool; optional
  manifest integration via a flag).
- `extract_emails.py` → `scripts/ingest/email_json_to_txt.py`.
- `split_mbox.py` → `scripts/ingest/mbox_split.py` (decouple from
  manifest; allow unfiltered split).
- `find_claim_emails.py` → `scripts/manifest/correspondence_manifest.py`
  (rename; accept search criteria as config, not hardcoded).

**Also:** introduce a `correspondence_manifest.yaml` schema doc.

## Agent 1C — Packet track

- `build_complaint_packet.py` → `scripts/packet/build.py` (**major
  rework**: driven by `packet-manifest.yaml`, not hardcoded exhibit
  letters/filenames).
- `build_policy_appendix_cover.py` → `scripts/packet/appendix_cover.py`
  (generalize to "governing-documents appendix cover").
- `compile_policy.py` → `scripts/packet/compile_reference.py`
  (generalize; watermark + disclaimer stay).
- `build_mia_complaint_pdf.sh` → `scripts/packet/build_pdf.sh`
  (generalize to "complaint-PDF assembler").

**Also:** publish the `packet-manifest.yaml` schema in
`templates/packet-manifests/` with at least one worked example.

## Hard rules for all Phase 1 agents

- **Read** the source scripts; do not copy. Generalize the design; match
  interfaces only where that design is sound.
- **No real case data** in tests, docs, or fixtures. Use the synthetic
  case once Phase 2 has produced it, or minimal made-up fixtures inline.
- **Tests matter.** Each tool ships with at least smoke tests under
  `tests/`.
