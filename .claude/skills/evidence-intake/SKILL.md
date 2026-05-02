---
name: evidence-intake
description: Route a new piece of evidence (email, SMS, screenshot, voicemail, medical EOB, PDF, HTML, image) through the correct ingestion pipeline and into the three-layer evidence tree — triggers when the user says "I have a new email/text/screenshot/voicemail/PDF to add" or drops a file into evidence/.
---

# evidence-intake

Pick the right ingester for a piece of evidence and run it.

For PDFs, HTML, and images — the formats where extraction is genuinely
hard (bezier-glyph PDFs, JS-rendered pages, photos of text) —
**delegate to the `document-extraction` skill**. It owns the layered
cascade, garble detection, and per-evidence reproducibility scripts.

## When this skill fires

- User drops a new file into `evidence/` and asks to ingest it.
- User says "I got a new email/text/screenshot/voicemail/EOB/PDF" for
  the case.
- Before the `packet-builder` is rerun after evidence was added.

## The three-layer model

Every evidence type lands in three parallel trees:

- `evidence/<type>/raw/` — the original artifact, untouched. This
  is the forensic record; treat it as immutable.
- `evidence/<type>/structured/` — canonical JSON. Machine-readable.
- `evidence/<type>/readable/` — a human-readable rendering (`.txt`
  or markdown) for skimming and for inclusion in a packet exhibit.

The ingestion scripts produce layers 2 and 3 from layer 1. Never
hand-edit the derived layers; rerun the ingester.

## Pipeline selector

| Evidence type  | Skill / script                                   |
|----------------|--------------------------------------------------|
| `.eml` / `.html` / `.htm` / `.pdf` / `.png` / `.jpg` / `.jpeg` / `.tiff` | **`document-extraction` skill** (cascade) |
| Mailbox export (`.mbox`) | `uv run python -m scripts.ingest.mbox_split` → loop the resulting `.eml` files through `document-extraction` |
| SMS / iMessage | `uv run python -m scripts.ingest.sms_export`           |
| Voicemail (metadata only) | `uv run python -m scripts.ingest.voicemail_meta` |
| Medical EOB / billing | `uv run python -m scripts.ingest.medical_eob`     |
| Screenshot / live webpage capture | `uv run python -m scripts.ingest.screenshot_capture` (use this when you need a tamper-evident snapshot of a *live URL*; for a previously-saved HTML file, use `document-extraction`) |

The cascade-based ingesters under `document-extraction` and the
single-format ingesters above all append to a manifest via
`scripts/ingest/_manifest.py` so the provenance report sees the new
item.

## Procedure (formats handled by document-extraction)

1. **Identify the type.** A PDF could be a screenshot, an EOB, or a
   scanned letter; these route differently. If it's a one-off PDF /
   HTML / image, use `document-extraction`. If it's a bulk medical
   EOB or SMS export, use the type-specific ingester.

2. **Place the raw file correctly.** Under
   `evidence/<type>/raw/<NNN>_<YYYY-MM-DD>_<slug>.<ext>` (or directly
   into `evidence/<type>/raw/` for non-numbered evidence). The
   numbered prefix is chronological within the case; it is how
   exhibits reference the item.

3. **Invoke `document-extraction`** to run the cascade. It will
   write `structured/<id>.json`, `readable/<id>.txt`, the
   reproducibility script under `<case>/extraction/scripts/`, and
   append to the manifest.

4. **Re-hash the evidence tree.** After ingest:

   ```
   uv run python -m scripts.evidence_hash --root evidence/
   ```

5. **Reconfirm chronology.** If the new item inserts into the middle
   of the sequence, you may need to renumber. Renumbering is
   expensive — it breaks every `packet-manifest.yaml` source line
   that references the old number. Prefer to append with the next
   available number even if the date is out of order; exhibits
   order by date at packet-build time, not by filename number.

## Definition of done

For each item the user is ingesting now: layer 1 is in place, layers
2 and 3 exist for any type that has an ingester, the
reproducibility script (when applicable) is written, the SHA-256
manifest is refreshed, and the user has confirmed there's nothing
more to ingest right now. Hand back to `pat-workflow`.

If a piece of evidence has no matching ingester (an audio recording,
a paper document), place the raw file under `evidence/<type>/raw/`
anyway and note in `notes/` that the structured/readable layers
are not generated. The hash manifest still covers it; downstream
packet exhibits can reference the raw file directly.

## Do not

- Do not edit anything under `evidence/*/raw/`. Ever. That tree is
  the ground truth.
- Do not hand-author the `structured/` or `readable/` layers. Rerun
  the ingester instead.
- Do not forget the hash refresh. A packet built against stale
  hashes has no chain of custody.
- Do not skip the `document-extraction` skill for PDFs and HTML even
  if they "look easy". The cascade's garble detection catches silent
  failures that the cheap path produces on bezier-glyph and
  JS-rendered inputs.
