---
name: evidence-intake
description: Route a new piece of evidence (email, SMS, screenshot, voicemail, medical EOB) through the correct ingestion pipeline and into the three-layer evidence tree — triggers when the user says "I have a new email/text/screenshot/voicemail to add" or drops a file into evidence/.
---

# evidence-intake

Every evidence type has its own ingester. This skill picks the right
one and runs it.

## When this skill fires

- User drops a new file into `evidence/` and asks to ingest it.
- User says "I got a new email/text/screenshot/voicemail/EOB" for
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

| Evidence type  | Script                                           |
|----------------|--------------------------------------------------|
| Single `.eml`  | `uv run python -m scripts.ingest.email_eml_to_json`     |
| Mailbox export | `uv run python -m scripts.ingest.mbox_split` → loop EML |
| Readable email | `uv run python -m scripts.ingest.email_json_to_txt`     |
| SMS / iMessage | `uv run python -m scripts.ingest.sms_export`            |
| Screenshot / webpage capture | `uv run python -m scripts.ingest.screenshot_capture` |
| Voicemail (metadata only)    | `uv run python -m scripts.ingest.voicemail_meta`     |
| Medical EOB / billing        | `uv run python -m scripts.ingest.medical_eob`        |

Each script has `--help`; use it. Each also appends to a
correspondence manifest via `scripts/ingest/_manifest.py` so the
provenance report sees the new item.

## Procedure

1. **Identify the type.** Ask the user if it's not obvious from the
   extension. A PDF could be a screenshot, an EOB, or a scanned
   letter — these route differently.

2. **Place the raw file correctly.** Under
   `evidence/<type>/raw/<NNN>_<YYYY-MM-DD>_<slug>.<ext>`. The
   numbered prefix is chronological within the case; it is how
   exhibits reference the item.

3. **Run the ingester.** For email, the two-step pipeline is
   EML → JSON → TXT. Running the first step writes
   `structured/NNN_...json`; running the second writes
   `readable/NNN_...txt`.

4. **Re-hash the evidence tree.** After ingest:

   ```
   uv run python -m scripts.evidence_hash --root evidence/
   ```

   This updates the SHA-256 manifest that `scripts/provenance.py`
   joins.

5. **Reconfirm chronology.** If the new item inserts into the middle
   of the sequence, you may need to renumber. Renumbering is
   expensive — it breaks every `packet-manifest.yaml` source line
   that references the old number. Prefer to append with the next
   available number even if the date is out of order; exhibits
   order by date at packet-build time, not by filename number.

## Synthetic example

For Maryland-Mustang, email `018_2025-06-25_sally-escalation.eml`
enters the pipeline as:

```
# layer 1: the raw EML drops into place
cp incoming.eml evidence/emails/raw/018_2025-06-25_sally-escalation.eml

# layer 2: canonical JSON
uv run python -m scripts.ingest.email_eml_to_json \
    --input evidence/emails/raw/018_2025-06-25_sally-escalation.eml \
    --output evidence/emails/structured/

# layer 3: readable transcript
uv run python -m scripts.ingest.email_json_to_txt \
    --input evidence/emails/structured/018_2025-06-25_sally-escalation.json \
    --output evidence/emails/readable/
```

The readable layer is what `packet-manifest.yaml` references in
exhibit B.

## Definition of done

For each item the user is ingesting now: layer 1 is in place, layers
2 and 3 exist for any type that has an ingester, the SHA-256
manifest is refreshed, and the user has confirmed there's nothing
more to ingest right now. Hand back to `pat-workflow` (typically
proceeds to drafting in Phase 6, or back to evidence-intake when
more evidence arrives later).

If a piece of evidence has no matching ingester (an arbitrary PDF,
an audio recording, a paper document), place the raw file under
`evidence/<type>/raw/` anyway and note in `notes/` that the
structured/readable layers are not generated. The hash manifest
still covers it; downstream packet exhibits can reference the raw
file directly.

## Do not

- Do not edit anything under `evidence/*/raw/`. Ever. That tree is
  the ground truth.
- Do not hand-author the `structured/` or `readable/` layers. Rerun
  the ingester instead.
- Do not forget the hash refresh. A packet built against stale
  hashes has no chain of custody.
