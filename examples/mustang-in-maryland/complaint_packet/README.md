# Complaint packet — Mustang in Maryland

**SYNTHETIC — NOT A REAL CASE.**

This directory reflects what `scripts/packet/build.py` (Phase 1C) will
produce given the `packet-manifest.yaml` in this directory and the
source materials in `../evidence/` and `../drafts/`.

Until the builder ships, the contents were staged by hand so that the
structure is a valid target for Phase 1C and for the Phase 5 walkthrough.

Layout:

- `packet-manifest.yaml` — declarative manifest: complaint, exhibit
  ordering, appendix contents, output filenames. Future runs of
  `scripts/packet/build.py` consume this.
- `complaint.md` — copy of `../drafts/mia-complaint.md`. Phase 5
  should emit `complaint.pdf` alongside (TODO-Phase-1C).
- `exhibits/` — per-exhibit subdirectories A–G with a cover page and
  the underlying materials.
- `appendix/` — governing-documents appendix (the insurer's full
  policy form set, with appendix cover).
- `MANIFEST.md` — human-readable index of the assembled packet.
