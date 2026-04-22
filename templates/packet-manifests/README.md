# Packet manifests

A **packet manifest** is a YAML file that specifies how to assemble a
complaint packet for a particular authority (regulator, AG consumer
protection office, court clerk, arbitration body, ombudsman, etc.).

Everything the packet-building tools need is declared here:

- which authority the packet is addressed to (for cover pages / filenames)
- which complaint document is the lead narrative
- which exhibits to include, in what order, and what each proves
- where the assembled output should land

The generic tools under `scripts/packet/` read one of these manifests
and emit a ready-to-file packet. They contain **no** case-specific or
authority-specific defaults — every value comes from the manifest.

## Files

- `schema.yaml` — commented prototype of the full schema with every
  supported field annotated. Treat as the specification.
- `example-generic-dispute.yaml` — a minimal, fictional worked example
  demonstrating the required fields.

## Minimum viable manifest

```yaml
packet:
  name: "short-packet-id"
  authority:
    name: "Authority Name"
    short_code: "AUTH"
  complaint:
    source: "path/to/complaint.pdf"
  output_dir: "path/to/output/"
  exhibits: []
```

Real manifests will populate `exhibits:` with entries; see
`schema.yaml` for every field.
