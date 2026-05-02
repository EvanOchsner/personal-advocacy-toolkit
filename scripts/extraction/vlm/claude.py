"""Cloud VLM provider: Anthropic Claude vision.

**Privacy**: this provider sends raw page images to Anthropic's API.
The cascade gates first use behind a per-case consent prompt
recorded in ``<case>/extraction/vlm-consent.yaml``.

Reuses the existing ``[llm]`` extra (``anthropic>=0.40``) — no new
dependency.
"""
from __future__ import annotations

import base64
import os
from typing import Any

from .base import VLMProvider, VLMProviderError


_PROMPT = (
    "You are an OCR transcriber. Transcribe ALL visible text in this page "
    "image into clean Markdown. Preserve headings, lists, and tables; do "
    "NOT hallucinate text that isn't visible; do NOT summarize. Reply with "
    "only the transcribed Markdown."
)


class ClaudeProvider(VLMProvider):
    name = "claude"
    requires_network = True
    requires_consent = True

    def __init__(
        self,
        *,
        model: str = "claude-sonnet-4-6",
        api_key: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.max_tokens = max_tokens

    def transcribe_page(self, png_bytes: bytes, *, hints: dict[str, Any]) -> str:
        try:
            import anthropic  # type: ignore[import-untyped]
        except ModuleNotFoundError as exc:
            raise VLMProviderError(
                "claude provider requires the [llm] extra. "
                "Run: uv sync --extra llm --extra extraction"
            ) from exc
        if not self.api_key:
            raise VLMProviderError(
                "ANTHROPIC_API_KEY not set. Export it before using the "
                "claude VLM provider."
            )

        client = anthropic.Anthropic(api_key=self.api_key)
        b64 = base64.standard_b64encode(png_bytes).decode("ascii")
        try:
            resp = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": b64,
                                },
                            },
                            {"type": "text", "text": _PROMPT},
                        ],
                    }
                ],
            )
        except Exception as exc:
            raise VLMProviderError(f"claude provider failed: {exc}") from exc

        # Concatenate any text blocks in the response.
        chunks: list[str] = []
        for block in getattr(resp, "content", []) or []:
            t = getattr(block, "text", None)
            if t:
                chunks.append(t)
        return "\n".join(chunks)

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "model": self.model, "max_tokens": self.max_tokens}
