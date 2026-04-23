# Tutorial 06: The case-map app

> Reference material, not legal advice.

You've run the ingest pipeline, computed deadlines, and built a
complaint packet. The case-map app is the last piece: a local browser
view that lets you *see* who the parties are, how they relate, and
what happened in what order — all driven by files already on disk,
with no outbound network calls.

Expected time: 10-15 minutes.

## 0. Prerequisites

- You completed the [Mustang-in-Maryland walkthrough](../../examples/mustang-in-maryland/WALKTHROUGH.md) at least once (so the synthetic artifacts are on disk). Not strictly required — the app will still run — but the drilldown panel is richer with real files behind the refs.
- `uv sync` has been run from the repo root.

## 1. Launch the app against the synthetic case

```sh
uv run python -m scripts.app --case-dir examples/mustang-in-maryland
```

Expected output:

```
case-map app serving at http://127.0.0.1:8765/ (case: examples/mustang-in-maryland)
This is reference information, not legal advice.
```

The browser opens automatically. If you run in an environment where
that's undesirable, pass `--no-browser`.

### What you should see

- **Three columns** in the graph: self + allies on the left,
  neutrals in the centre, adversaries on the right. For the Mustang
  case that's Delia Vance + her specialist shop + her agent on the
  left; the Maryland Insurance Administration + the first shop + the
  at-fault driver in the middle; Chesapeake Indemnity Mutual + their
  adjuster + their appraiser on the right.
- **A horizontal timeline** underneath, with three lanes: events
  (circles), correspondence (squares), deadlines (diamonds).
  For the synthetic case you'll see 15 event circles and a few
  deadline diamonds (computed automatically from the `loss.date` +
  jurisdiction in `case-facts.yaml`).
- **A drilldown panel** on the right, empty until you click
  something.

## 2. Inspect an entity

Click on **Delia Vance** (the self node). The drilldown panel now
shows:

- the role chip (`self`),
- the labels from `entities.yaml` (`policyholder`,
  `classic-car-owner`),
- a **From case-facts.yaml** block with the fields that `ref:
  claimant` resolved to — name, address, email, phone,
- outbound and inbound **Relationships** — she's adverse to CIM,
  has retained the specialist shop, and is allied with Meritor,
- every **Event** she's tagged in, which for the self entity is
  currently all 15.

At the same time, the timeline recolours: markers that touch Delia
are drawn in the palette colour assigned to her id; markers that
don't are dimmed to a faint grey.

Click Delia again to deselect, or click a different node.

## 3. Inspect a relationship

Relationships are the lines between nodes, each carrying a `kind`
and an optional `summary`. Hover over any line to see the native
browser tooltip.

Click **CIM** (the insurer node on the right). You should see
`← self (adverse_to)` under **Relationships (inbound)** and, under
outbound, `→ adjuster_whitlock (retained_by)` and
`→ appraiser_mava (retained_by)`. Those three lines translate
directly from the `relationships:` block of
[`entities.yaml`](../../examples/mustang-in-maryland/entities.yaml).

## 4. Explore the timeline

Each marker on the timeline carries a native SVG tooltip on hover —
no JavaScript libraries, works the same in every browser.

Click a **deadline diamond**. The drilldown panel replaces its
contents with that deadline's details: the `deadline_kind`, the
`clock_starts` field (which input date the clock was measured from),
the `clock_date`, and the authority reference if one is in the
deadlines table. Every deadline also carries an explicit
`VERIFY WITH COUNSEL` tag.

Click an **event circle**. The panel shows the event's entities as
clickable buttons — click one to jump back to that entity's
drilldown.

If you seeded `events.yaml` with `refs:` pointing at files on disk,
those appear as links that open the file inline in a new tab (the
extensions `.pdf`, `.txt`, `.md`, `.yaml`, `.eml`, `.json`, `.png`,
`.jpg`, `.jpeg`, `.docx` are allowed).

## 5. Adding the correspondence manifest

If you've run the correspondence ingest pipeline from
[Tutorial 02](02-ingesting-evidence.md), you'll have a
`correspondence-manifest.yaml` under the case dir. Restart the
server with:

```sh
uv run python -m scripts.app \
  --case-dir examples/mustang-in-maryland \
  --correspondence-manifest examples/mustang-in-maryland/correspondence-manifest.yaml
```

The timeline now adds a square marker per email, tagged to the
entities whose `match.emails` / `match.names` rules fit the `from` /
`to` / `subject` of that email. (In the synthetic case the manifest
isn't committed, but the path is the one the ingest tools produce.)

## 6. Adding a note to an entity

The app itself is **read-only** — it does not write to the
filesystem. Notes are added by editing files under
`notes/entities/` in the case directory, typically by asking
Claude Code (or another AI / agent) to draft them. Each entity can
declare a `notes_file` path in its record:

```yaml
# entities.yaml
entities:
  - id: cim
    role: adversary
    ref: parties.insurer
    notes_file: notes/entities/cim.md
```

Then ask your AI assistant to write `notes/entities/cim.md` against
whatever grounded facts it has from the rest of the case materials.
Restart the server and the drilldown panel for CIM now renders
those notes as sanitized HTML (see
[the case-map-app concept doc](../concepts/case-map-app.md) for
what the renderer supports — it is deliberately minimal).

## 7. Validate before running

When you edit `entities.yaml` or `events.yaml` by hand, validate
before restarting:

```sh
uv run python -m scripts.app.validate --case-dir examples/mustang-in-maryland
```

A clean pass prints:

```
OK  examples/mustang-in-maryland: 9 entities, 6 relationships, 15 events, 15 timeline markers.
This is reference information, not legal advice.
```

An error is printed with the exact field that needs fixing. CI runs
this against the synthetic case on every push so the Mustang seed
data never drifts out of schema.

## 8. Airgap note

The server binds `127.0.0.1` only; the browser's Content-Security
policy blocks any outbound fetch; CI fails the build if an external
URL is introduced into `scripts/app/static/`. These protections are
**policy + convention + CI grep**, not OS-level isolation.

If you need true isolation for sensitive materials:

```sh
# Linux
firejail --net=none uv run python -m scripts.app \
  --case-dir path/to/case --no-browser
# Then open http://127.0.0.1:8765/ in a browser inside the same sandbox.

# Any host with Docker
docker run --rm -it --network=none \
  -v "$PWD":/work -w /work \
  python:3.11 \
  bash -c "pip install uv && uv sync && uv run python -m scripts.app --case-dir path/to/case --no-browser"
```

See [`docs/concepts/case-map-app.md`](../concepts/case-map-app.md)
for the full airgap rationale.

## Where next

- [`docs/concepts/case-map-app.md`](../concepts/case-map-app.md) —
  schemas, airgap policy, paranoid mode.
- [`templates/entities.schema.yaml`](../../templates/entities.schema.yaml)
  and [`templates/events.schema.yaml`](../../templates/events.schema.yaml)
  — human-readable field reference.
- Exit the server with Ctrl-C when you're done.
