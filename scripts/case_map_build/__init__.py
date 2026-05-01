"""Precompute the case-map dashboard payload from case files on disk.

Two-stage architecture:
    1. `python -m scripts.case_map_build --case-dir <case>` reads
       entities.yaml, case-facts.yaml, events.yaml, the references
       manifest, and authorities-research notes; computes per-widget
       JSON; and writes everything to <case>/.case-map/.
    2. `python -m scripts.app --case-dir <case>` reads only the cache.
       It is fully offline and never writes to <case>.

The cache is hash-based: `<case>/.case-map/manifest.json` records a
sha256 of every input file. A widget regenerates only when one of its
declared inputs changes. Pass --force to invalidate everything.

LLM enrichment is opt-in (`--llm`) and gated on ANTHROPIC_API_KEY. With
--no-llm (the default) the build is deterministic and fully offline:
synopses come from manifest fields and first-paragraph extracts.
"""

__all__: list[str] = []
