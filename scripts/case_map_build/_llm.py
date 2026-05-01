"""Optional Claude-API enrichment of widget summaries.

Imported lazily inside __main__.py only when --llm is passed and
ANTHROPIC_API_KEY is set. The viewer (scripts.app) never imports this
module, so the runtime stays fully offline.

Each summarize_* method:
    - Returns a str on success.
    - Returns None on benign skip (empty input).
    - Raises on hard failure (caller catches and falls back to the
      deterministic blurb).
"""
from __future__ import annotations

import os
from typing import Any


_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 400


class LLMSummarizer:
    """Thin wrapper over the Anthropic SDK with a one-shot per-widget call.

    Prompt-cache hit rate is fine here: each call is independent and the
    prompts are small. The optional dep `anthropic` ships under
    [project.optional-dependencies].llm and is only imported here.
    """

    def __init__(self) -> None:
        try:
            import anthropic  # type: ignore
        except ImportError as exc:  # pragma: no cover — exercised only with --llm
            raise RuntimeError(
                "the `anthropic` package is required for --llm enrichment. "
                "Install with: uv sync --extra llm"
            ) from exc
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set; --llm requires a valid API key."
            )
        self._client = anthropic.Anthropic(api_key=api_key)

    def summarize_central_issue(
        self, case_facts: dict[str, Any], deterministic: str
    ) -> str | None:
        cf_excerpt = {
            k: case_facts.get(k)
            for k in ("case_name", "situation_type", "subtype", "loss", "disputed_amounts", "relief_sought")
            if case_facts.get(k) is not None
        }
        prompt = (
            "You are summarizing a personal advocacy case for a dashboard "
            "header. Write 2-3 sentences in plain English describing the "
            "central issue and what the claimant is asking for. Do NOT "
            "give legal advice. Do NOT speculate beyond the supplied facts.\n\n"
            f"Deterministic summary (baseline):\n{deterministic}\n\n"
            f"Case facts (excerpt):\n{cf_excerpt}\n"
        )
        return self._call(prompt)

    def summarize_party(
        self, entity: Any, resolved: dict[str, Any], deterministic: str
    ) -> str | None:
        prompt = (
            "Write a 1-2 sentence card blurb for this party in a case-map "
            "dashboard. Plain English; no legal advice; no speculation.\n\n"
            f"Deterministic blurb (baseline):\n{deterministic}\n\n"
            f"Party id: {entity.id}\n"
            f"Role in case: {entity.role}\n"
            f"Labels: {entity.labels}\n"
            f"Resolved facts: {resolved}\n"
        )
        return self._call(prompt)

    def summarize_reference(self, citation: str, title: str, extract: str) -> str | None:
        if not extract and not title:
            return None
        prompt = (
            "Write a 2-3 sentence plain-English synopsis of this governing "
            "document for a case-map dashboard card. Do not give legal "
            "advice. Stick to what the supplied excerpt actually says.\n\n"
            f"Citation: {citation}\n"
            f"Title: {title}\n"
            f"Excerpt:\n{extract}\n"
        )
        return self._call(prompt)

    def _call(self, prompt: str) -> str | None:
        try:
            msg = self._client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception:  # noqa: BLE001 — caller decides what to do
            raise
        chunks: list[str] = []
        for block in getattr(msg, "content", []) or []:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                chunks.append(text)
        out = "\n".join(chunks).strip()
        return out or None
