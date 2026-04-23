# Case-map app

> Reference material, not legal advice.

The case-map app (`scripts/app/`) renders an interactive view of a
single case — who the parties are, how they relate, and what happened
when — in a local browser. Everything it displays is loaded from files
on disk under the case directory. It does not call the network, it
does not infer from training memory, and it does not render LLM output.

## Launch

```sh
uv run python -m scripts.app --case-dir path/to/case
```

Binds `127.0.0.1:8765` by default. The browser opens automatically.
Pass `--port` to change the port, `--no-browser` to skip the auto-open.

Exit with Ctrl-C.

## Data sources

In order of priority when two sources disagree:

1. **`entities.yaml`** (required, at case root) — the parties:
   self, allies, neutrals, adversaries. Each entity has a stable `id`,
   a `role` that determines its column, an optional `ref:` into
   `case-facts.yaml` so names / contact details aren't duplicated,
   and optional `match:` rules used to tag correspondence.
2. **`events.yaml`** (optional, at case root) — timeline events
   tagged by entity id.
3. **`case-facts.yaml`** (optional, at case root) — the facts that
   `entities[*].ref` resolves into. This is the same file used by
   `scripts/intake/` and the dashboard.
4. **Correspondence manifest** — if present, each entry contributes a
   timeline marker tagged to the matching entities.
5. **`deadline_calc` output** — future deadline markers when the
   intake carries `situation_type` + `jurisdiction.state` + `loss.date`.

The authoritative schemas are in `scripts/app/_schema.py` and
documented under `templates/entities.schema.yaml` and
`templates/events.schema.yaml`. Validate with:

```sh
uv run python -m scripts.app.validate --case-dir path/to/case
```

**Evidence manifest entries are intentionally excluded from the
timeline.** The manifest carries SHA-256 hashes + paths, not dates;
joining evidence reliably to a wall-clock timeline is a separate
problem and out of scope for v1.

## Entities: ref resolution + notes

```yaml
# entities.yaml
entities:
  - id: self
    role: self
    ref: claimant                  # -> case_facts["claimant"]
    labels: [policyholder]
    notes_file: notes/entities/self.md
```

The server walks the dotted path into `case-facts.yaml`. Whatever that
resolves to is rendered in the drilldown panel under "From
case-facts.yaml". The `notes_file`, if declared, is read at request
time and rendered via a deliberately minimal markdown subset (see
*Airgap posture* below).

Notes are intended to be **edited by a human or by an AI/agent** in
the user's normal workflow — the app itself is read-only. Asking
Claude Code to append a note is the expected update path.

## Airgap posture

This is a **policy-level** airgap, not an OS-level one.

- The server binds `127.0.0.1` only — it is a module-level constant
  in `scripts/app/server.py` with no CLI override.
- Every HTTP response carries a restrictive
  `Content-Security-Policy: default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`.
- The markdown renderer for entity notes does **not** emit anchor
  tags for URLs carrying a scheme. `[text](https://example.com)`
  renders as literal text — no clickable outbound link.
- CI greps `scripts/app/static/` and `scripts/app/templates/` for
  `http://` / `https://` / `//cdn.` / `//fonts.`; any match fails
  the build. (XML namespace URIs like the SVG namespace are
  allowlisted — they are identifiers, not fetch targets.)
- The test suite mirrors the CI grep locally so a developer catches
  violations before pushing.

What this does **not** guarantee:
- OS-level network isolation. A compromised Python dependency, a
  future contributor who introduces a new outbound call outside
  `scripts/app/`, or a malicious payload in case materials could in
  principle still reach the network.
- Protection from the user: if the user writes an external URL into
  `entities.yaml` or into a notes file, the renderer escapes and
  displays it, but does not fetch it.

### Paranoid mode — true network isolation

When working on materials sensitive enough that policy-level
enforcement is not enough, run the server under an OS-level network
sandbox:

```sh
# Linux: no network namespace at all
unshare -n uv run python -m scripts.app --case-dir path/to/case --no-browser
# Then open http://127.0.0.1:8765/ from a browser inside the same namespace.

# Linux with firejail:
firejail --net=none uv run python -m scripts.app --case-dir path/to/case

# Docker (any host):
docker run --rm -it --network=none \
  -v "$PWD":/work -w /work \
  python:3.11 \
  bash -c "pip install uv && uv sync && uv run python -m scripts.app --case-dir path/to/case --no-browser"
```

On macOS there is no direct equivalent to Linux's `unshare -n`;
running the server inside a `--network=none` container is the
recommended equivalent.

## Adding an entity

1. Pick a stable `id` (lowercase letters, digits, `-`, `_`).
2. Decide the `role` (self / ally / neutral / adversary — this
   controls which column it appears in).
3. If the entity already has a record in `case-facts.yaml`, add
   `ref: dotted.path.here`. Otherwise give it a `display_name`.
4. Optionally add `match.emails` / `match.names` so the timeline
   aggregator can link correspondence to this entity.
5. Run `uv run python -m scripts.app.validate --case-dir .` and fix
   any errors before restarting the server.

## Adding a relationship

```yaml
relationships:
  - from: self
    to: cim
    kind: adverse_to
    summary: "Agreed-value policy dispute."
```

`kind` must be one of:
`adverse_to | represented_by | retained_by | witness_to | venue_for | regulates | allied_with | other`.

Relationships are directional. They show as lines in the graph and
as in/out lists in the drilldown panel.

## Adding an event

```yaml
events:
  - id: cim_position_letter
    date: 2025-05-09
    kind: filing
    title: "CIM formal position letter"
    entities: [self, cim, adjuster_whitlock]
    summary: "Declines storage fees as 'non-customary'."
```

`kind` must be one of:
`incident | filing | hearing | call | meeting | other`.
Every id in `entities:` must correspond to a declared entity.

## Troubleshooting

- **Validator passes but the server 500s on boot** — almost always a
  `notes_file` pointing outside the case directory, or a `ref:` that
  was added after the facts it depends on were removed. Re-run the
  validator.
- **An entity doesn't get matched to a correspondence entry** — check
  `match.emails` (case-insensitive exact address) and `match.names`
  (case-insensitive substring) against the raw `from`/`to` headers
  in the correspondence manifest entry.
- **Edits to `entities.yaml` don't show up** — the server loads the
  case once at boot. Restart the process.
