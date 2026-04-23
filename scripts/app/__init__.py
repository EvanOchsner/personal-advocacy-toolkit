"""Case-map app — interactive graph + timeline for a single case.

The app renders a three-column entity graph (self/allies, neutrals,
adversaries) and a horizontal timeline, driven entirely by files on
disk under a case directory: `entities.yaml`, `events.yaml`,
`case-facts.yaml`, the correspondence manifest, and the deadline
calculator's output. No LLM inference, no web lookups, no training-
memory recall — everything displayed is traceable to a file.

AIRGAP CAVEAT (PR 1 scaffolding — UI lands in PR 2):
    The forthcoming HTTP server will bind to 127.0.0.1 only, serve a
    strict Content-Security-Policy, and a CI grep will reject external
    URLs in scripts/app/static/. Those are policy-and-convention
    enforcement, NOT OS-level network isolation. Any change touching
    this package must preserve that posture. For true network
    isolation, run the server under `unshare -n`, `firejail --net=none`,
    or inside a container with `--network=none`.
"""

__all__: list[str] = []
