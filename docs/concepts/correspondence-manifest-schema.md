# Correspondence manifest schema

A *correspondence manifest* is a YAML (or TOML / JSON) file that lists
which messages in your raw inbox belong to a particular dispute. It's the
bridge between a dump of `.eml` / `.mbox` files and the downstream packet
tools.

Two files are involved:

1. **Search config** — you write this. It tells
   `scripts/manifest/correspondence_manifest.py` which messages to pick.
2. **Generated manifest** — the tool writes this. Each entry is a pointer
   (path, `Message-ID`, date, subject, from, to) back to the source.

Keeping the search criteria in a file — not in code — means the same
tool works for any dispute without patching the script.

## Search config — top-level keys

All keys are optional. Criteria at the top level are **AND**-combined;
multiple values inside one key are **OR**-combined. An empty config
matches everything.

| Key               | Type                                 | Notes                                                         |
|-------------------|--------------------------------------|---------------------------------------------------------------|
| `parties`         | list of strings                      | Address equality (case-insensitive) or `@domain.tld` suffix.  |
| `subject_regex`   | list of Python regex strings         | Any pattern matching `Subject` counts.                        |
| `body_regex`      | list of Python regex strings         | Matched against the plain-text body.                          |
| `header_contains` | map of header name -> list of subs   | Substring match on any named header.                          |
| `identifiers`     | list of strings                      | Substring search across subject + body + all headers.         |
| `date_range`      | object with `start` and/or `end`     | ISO-8601 dates, inclusive.                                    |

## Example: insurance claim correspondence

```yaml
# scripts/manifest/example-correspondence.yaml
parties:
  - "@insco.example"          # anyone at this domain
  - "adjuster@insco.example"  # exact match (also covered by the domain rule)

subject_regex:
  - "(?i)\\bclaim\\b"
  - "(?i)policy\\s*#?\\s*\\d+"

header_contains:
  X-Claim-Number:
    - "ACR61-3"

date_range:
  start: "2024-01-01"
  end:   "2024-12-31"

identifiers:
  - "ACR61-3"
```

Run:

```bash
python -m scripts.manifest.correspondence_manifest \
    --config scripts/manifest/example-correspondence.yaml \
    --out   data/correspondence/manifest.yaml \
    data/correspondence/raw/
```

The output `manifest.yaml` looks like:

```yaml
generated_at: "2026-04-22T15:00:00+00:00"
criteria: { ... the config you passed ... }
count: 17
entries:
  - source: "data/correspondence/raw/msg_0003_20240115T094500_Re-Claim-status.eml"
    message_id: "<abc@insco.example>"
    date: "2024-01-15"
    subject: "Re: Claim status"
    from: "Adjuster Adamson <adjuster@insco.example>"
    to:   "Alice Example <alice@example.com>"
  - ...
```

## Worked tiny example (also used in tests)

```yaml
parties:
  - "alice@example.com"
subject_regex:
  - "(?i)invoice"
```

Matches any message where `alice@example.com` appears on any address
line **and** the subject contains "invoice" (case-insensitive).
