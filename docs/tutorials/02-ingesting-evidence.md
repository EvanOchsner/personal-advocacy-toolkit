# Tutorial 02: Ingesting evidence

> **Reference material, not legal advice.**

By the end of this tutorial, your raw evidence — an mbox from Gmail
Takeout, a pile of .eml files, an SMS export, a voicemail log, a web
page you want to preserve — will live under `evidence/` in a
consistent three-layer shape that every downstream tool understands.

Running example: the
[`Mustang-in-Maryland`](../../examples/mustang-in-maryland/) case,
which ships 20 synthetic emails already laid out across
`evidence/emails/{raw,structured,readable}/`. We'll re-validate them
as if you were doing the ingest yourself.

```sh
cd examples/mustang-in-maryland
```

## The three-layer pattern

Every ingest pipeline lands at the same shape:

```
evidence/<kind>/
  raw/         <- original, untouched (RFC-5322, XML export, etc.)
  structured/  <- canonical JSON the tools consume
  readable/    <- human-readable .txt for exhibits and review
```

- **raw/** is immutable. The pre-commit hook refuses to modify it.
- **structured/** is regeneratable from raw/. Keep it under version
  control; tools consume JSON, not MIME.
- **readable/** is what goes into the packet as an exhibit. Regenerate
  freely from structured/.

## Email ingest

### From a Gmail Takeout mbox

Split the mbox into individual .eml files:

```sh
uv run python -m scripts.ingest.mbox_split path/to/All.mbox \
  --out-dir evidence/emails/raw \
  --prefix claim
```

Output filenames look like `claim_0017_20250315T093012_Re-Claim-intake.eml`.

If your inbox is large and you only want messages touching this
dispute, write a filter config. See
[`docs/concepts/correspondence-manifest-schema.md`](../concepts/correspondence-manifest-schema.md)
for the schema. Then:

```sh
uv run python -m scripts.ingest.mbox_split path/to/All.mbox \
  --out-dir evidence/emails/raw \
  --prefix claim \
  --filter-config search.yaml
```

### From .eml files

If you already have individual .eml files (exported from Mail.app,
saved from Outlook, etc.), skip `mbox_split` and go straight to:

```sh
uv run python -m scripts.ingest.email_eml_to_json \
  evidence/emails/raw \
  --out-dir evidence/emails/structured
```

One JSON per .eml, same stem. The JSON captures headers, addresses,
Message-ID, dates, both plain-text and HTML bodies, attachment
metadata (filename, content-type, size, SHA-256), and a SHA-256 of
the raw .eml bytes as `source_sha256`.

### Render the human-readable layer

```sh
uv run python -m scripts.ingest.email_json_to_txt \
  evidence/emails/structured \
  --out-dir evidence/emails/readable
```

One `.txt` per JSON. This is what gets concatenated into Exhibit B
(correspondence compilation) of the complaint packet.

### Build the correspondence manifest

A **correspondence manifest** is a declarative list of which messages
belong to this dispute, independent of where they live on disk. It's
the bridge between raw inbox and packet.

```sh
uv run python -m scripts.manifest.correspondence_manifest \
  --config search.yaml \
  --out correspondence-manifest.yaml \
  evidence/emails/raw
```

Or pass already-parsed JSON directly (faster, no re-parse):

```sh
uv run python -m scripts.manifest.correspondence_manifest \
  --config search.yaml \
  --out correspondence-manifest.yaml \
  evidence/emails/structured
```

<!-- TODO: verify after dogfood pass -->
(The script accepts .eml, .mbox, and .json inputs per its docstring;
confirm --config is required.)

## SMS / iMessage ingest (prototype)

`scripts/ingest/sms_export.py` currently prototypes Android "SMS
Backup & Restore" XML as the best-documented, most stable format.
iOS (chat.db), iMazing CSV, and Google Voice HTML are stubs mirroring
the same output shape.

<!-- TODO: verify after dogfood pass -->
Read the script docstring for current CLI surface before relying on a
specific invocation.

## Voicemail metadata ingest (prototype)

`scripts/ingest/voicemail_meta.py` ingests voicemail / call-log
metadata (not audio, unless your jurisdiction's one/two-party consent
rules allow). Format support and CLI surface are in the script's
module docstring.

<!-- TODO: verify after dogfood pass -->

## Web-page capture

For harassment, scam, and landlord-listing situations you often need
to preserve a web page before it changes:

```sh
uv run python -m scripts.ingest.screenshot_capture \
  "https://example.com/post/12345" \
  --out-dir evidence/screenshots
```

Produces a PDF + a DOM snapshot + a manifest entry with the retrieved
URL, timestamp, SHA-256, and backend used.

Best results require playwright:

```sh
uv pip install playwright
uv run playwright install chromium
```

Without playwright the tool falls back to headless Chrome if
available, or to a placeholder PDF flagged `NON-EVIDENCE-GRADE`.

## Medical EOB ingest (prototype)

`scripts/ingest/medical_eob.py` parses EOB PDFs (Anthem / UHC
formats) plus a generic CSV fallback. Produces the same three-layer
shape.

<!-- TODO: verify after dogfood pass -->

## PDF ingest (with optional OCR)

Adversaries sometimes deliver evidence as scanned, image-only PDFs
that defeat plain-text search. `scripts/ingest/pdf_to_text.py` runs
each PDF through pypdf for native text extraction first, and falls
back to `ocrmypdf` (an optional system binary, **not** a Python
dependency) if no text layer is present:

```sh
uv run python -m scripts.ingest.pdf_to_text \
  evidence/policy/auto-policy.pdf \
  --out-dir evidence/pdfs \
  --manifest evidence/pdfs/manifest.yaml
```

Output:

```
evidence/pdfs/
  raw/<source_id>.pdf            # byte-identical copy of the input
  structured/<source_id>.json    # provenance + extraction metadata
  human/<source_id>.txt          # plaintext transcript (grep-able)
  manifest.yaml                  # one entry per ingested PDF
```

The structured JSON records `ocr_applied` (true/false), `ocr_engine`
(e.g. `"ocrmypdf 16.10.0"`), `page_count`, and `text_chars` so a
reviewer can spot pages where extraction yielded nothing. Install
`ocrmypdf` via your package manager (`brew install ocrmypdf` on
macOS) when you need to OCR scanned exhibits; the tool emits a clear
warning and skips OCR otherwise.

`--force` overwrites an existing manifest entry with the same
`source_id`. Without it, re-runs on already-ingested files fail loud
to protect against accidental clobber.

## Standalone HTML ingest

Insurer portals and consumer-facing emails sometimes deliver content
as HTML where the visible text is nontrivial to recover (nested
tables, inline styles, no plaintext alternative). The email pipeline
above already handles HTML bodies inside MIME messages, but for
**standalone** `.html` / `.htm` files saved from a browser, use:

```sh
uv run python -m scripts.ingest.html_to_text \
  evidence/portal-pages/claim-status.html \
  --out-dir evidence/html \
  --manifest evidence/html/manifest.yaml
```

The renderer is stdlib-only (`html.parser.HTMLParser` plus
`html.unescape`); no third-party HTML library is added to the
project. It strips `<script>` / `<style>` content, preserves block
structure, renders links as `text (https://...)` so URLs stay
grep-able, and decodes character entities. The `<title>` element is
captured into the structured JSON.

You can also pass a directory; every `.html` and `.htm` file inside
(non-recursive) is processed.

## Hash and snapshot after every ingest

After any ingest run:

```sh
uv run python -m scripts.evidence_hash --root evidence --manifest .evidence-manifest.sha256
uv run python -m scripts.provenance_snapshot --root evidence
```

The manifest is regeneratable; just re-run it. The snapshot gets a
new timestamped JSON file; both should be committed.

## Validate the synthetic case end-to-end

For the Mustang example, all three layers are already laid out:

```sh
ls evidence/emails/raw/        # 20 .eml
ls evidence/emails/structured/ # 20 .json
ls evidence/emails/readable/   # 20 .txt
```

Re-hash and snapshot:

```sh
uv run python -m scripts.evidence_hash \
  --root evidence --manifest .evidence-manifest.sha256
uv run python -m scripts.provenance_snapshot --root evidence
```

You should see ~45 entries across the emails + policy + valuation +
photos placeholders.

## Where next

- [`03-understanding-the-situation.md`](03-understanding-the-situation.md)
  — now that evidence is ingested, classify the situation and look up
  authorities/deadlines.
- [`docs/concepts/evidence-integrity.md`](../concepts/evidence-integrity.md)
  — the full story on hashes, xattrs, and provenance joins.
- [`docs/concepts/chain-of-custody.md`](../concepts/chain-of-custody.md)
  — how the four sources compose into a single report.
