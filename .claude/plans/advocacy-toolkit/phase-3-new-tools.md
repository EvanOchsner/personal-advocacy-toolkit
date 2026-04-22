# Phase 3 — Gap-filling new tools

Three parallel tracks.

## Agent 3A — Intake / situation / authorities

- `scripts/intake/situation_classify.py` — (LLM-assisted) questionnaire →
  `case-intake.yaml` + playbook recommendation.
- `scripts/intake/authorities_lookup.py` — `(situation, jurisdiction)` →
  authority shortlist, backed by `data/authorities.yaml`.
- `scripts/intake/deadline_calc.py` — `(situation, jurisdiction,
  loss_date)` → SOL and notice windows from `data/deadlines.yaml`, with
  explicit "verify with counsel" disclaimers.
- `data/authorities.yaml`, `data/deadlines.yaml`,
  `data/situation_types.yaml`. Populate **MD + insurance-dispute** as the
  worked row; scaffold the other jurisdictions/situations as stubs with
  clear `TODO: populate` markers.

## Agent 3B — Non-email ingest

Prototype one format per tool; stub the rest with a clear format-support
matrix.

- `scripts/ingest/sms_export.py` — iOS/Android SMS/iMessage backups →
  three-layer format.
- `scripts/ingest/screenshot_capture.py` — headless browser wrapper:
  PDF + full DOM + screenshot, with SHA-256 + timestamp + URL captured
  in the manifest at creation.
- `scripts/ingest/voicemail_meta.py` — call-log / voicemail metadata
  (not audio, unless jurisdiction allows).
- `scripts/ingest/medical_eob.py` — one common EOB PDF format, generic
  CSV fallback.

## Agent 3C — Publication safety

This track is delicate; post-checks matter as much as scrubbers.

- `scripts/publish/pii_scrub.py` — detector + replacer, `substitutions.yaml`
  for consistent pseudonymization, refuses to run against `evidence/`,
  produces a sidecar change report.
- `scripts/publish/pdf_redact.py` — flatten, remove text layer under
  redactions, scrub XMP/DocInfo, **post-check** that no redacted term
  survives in any text layer.
- `scripts/publish/docx_metadata_scrub.py` — unzip, scrub
  `docProps/core.xml` + `app.xml`, rezip.
- `scripts/publish/exif_scrub.py` — batch EXIF scrub for images.
- `scripts/publish/history_sanitizer.py` — `git filter-repo` wrapper +
  post-check that scans all blobs for any banned term.

Each tool's post-check is a mandatory CI job.
