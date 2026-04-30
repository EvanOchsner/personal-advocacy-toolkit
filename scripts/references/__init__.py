"""Trusted reference-document acquisition pipeline.

Handles statutes, regulations, official policies, terms of service, and
related authoritative texts. Lands raw bytes, plaintext, and structured
sidecar metadata into ``<case>/references/`` with provenance.

This package is a peer to ``scripts.ingest`` (which handles evidence) but
is intentionally separate: ``evidence/`` is append-only because
mutating private case material destroys chain of custody, while
``references/`` is reproducible from the source — a stale or wrong copy
can be re-fetched from the original publisher.

See ``.claude/skills/trusted-sources/SKILL.md`` for the agent-side
workflow and ``docs/concepts/trusted-sources.md`` for the design
rationale.
"""
