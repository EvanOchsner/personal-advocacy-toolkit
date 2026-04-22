# Phase 2 — Synthetic case "Mustang in Maryland"

One agent, running in parallel with Phase 1. Authors the fully synthetic
worked example under `examples/mustang-in-maryland/`.

## Facts (canonical — do not drift)

See §Synthetic case: "Mustang in Maryland" in the master plan. Key
identifiers:

- Claimant: **Delia Vance** (Towson, MD).
- Vehicle: **1969 Ford Mustang Mach 1**, 84,000 mi, agreed-value classic
  policy. VIN placeholder only.
- Insurer: **Chesapeake Indemnity Mutual** (fictional — run
  USPTO/SERFF/web check before shipping; rename if collision).
- Policy: `CIM-VEH-2023` and related fictional form numbers.
- Adjuster **Harlan Whitlock**, appraiser **Joyce Pemberton**.
- Agent: **Meritor Insurance Group**, Annapolis MD.
- Loss: rear-ended **March 15, 2025** in Columbia, MD.
- First shop: **Pikesville Collision Center** (declines).
- Specialist shop: **Brandywine Classic Restoration**, Wilmington, DE.
- Valuation vendor: **MidAtlantic Vehicle Appraisers** (substitutes
  for CCC).
- Regulator: **real MIA**, synthetic case number `MIA-SYN-0000-0000`.
- Timeline: March 15 – October 1, 2025.
- Agreed value $58,000; disputed deduction $5,280.50.

## Deliverables

- 18–22 synthetic emails across the three-layer format.
- Fictional valuation PDF from MidAtlantic Vehicle Appraisers.
- 2–3 synthetic photos, clearly tagged synthetic.
- Fictional Chesapeake Indemnity policy form set (short, stylized).
- Finished MIA-style complaint docx + assembled packet.
- `CLAUDE.md` instance and `case-facts.yaml` that demonstrate the
  templates in `templates/`.
- `WALKTHROUGH.md` narrating a clean end-to-end run.

## Safety checks (before merging)

- USPTO TESS, SERFF, and a web search on every fictional entity name.
  Rename on any hit.
- Quick LinkedIn/web check on every invented person name.
- Every generated document carries `SYNTHETIC — NOT A REAL CASE` in
  footers and filenames.
- No document visually mimics a real insurer's form layout.
