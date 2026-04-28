# Packet Manifest — The Maryland Mustang (MIA complaint)

**SYNTHETIC — NOT A REAL CASE.**

This is the human-readable index of the assembled packet. The
authoritative declarative manifest lives in `packet-manifest.yaml`.

## Cover documents

- `complaint.md` — MIA complaint (Markdown stand-in; Phase 1C will emit
  `complaint.pdf`).

## Exhibits

| Exhibit | Title                                                 | Source                                    |
| ------- | ----------------------------------------------------- | ----------------------------------------- |
| A       | Declarations page (CIM-CLS-0000-0000)                 | `exhibits/A/` (TODO-Phase-2-followup)      |
| B       | Full policy form set                                  | `exhibits/B/`                              |
| C       | Correspondence compilation (20 emails, chrono)        | `exhibits/C/`                              |
| D       | MAVA valuation report MAVA-2025-04-0117               | `exhibits/D/`                              |
| E       | Photographs (placeholders until Phase 5)              | `exhibits/E/`                              |
| F       | Midlife Crisis Restorations opinion letter + parts-market comps        | `exhibits/F/`                              |
| G       | Salvage-transfer notification                          | `exhibits/G/`                              |

## Appendix

- Governing documents — Chesapeake Indemnity Mutual policy form set.
  See `appendix/`.

## TODO markers

- TODO-Phase-1C: `scripts/packet/build.py` should consume
  `packet-manifest.yaml` and render `complaint.pdf` plus per-exhibit
  cover-paginated PDFs.
- TODO-Phase-2-followup: a declarations-page extract was not separately
  authored; Exhibit A currently points at the policy set.
- TODO-Phase-5: regenerate the MAVA valuation report as a PDF via
  reportlab, regenerate photos as PNGs via Pillow, and regenerate
  the complaint as `mia-complaint.docx` via python-docx.
