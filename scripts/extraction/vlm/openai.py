"""Cloud VLM provider: OpenAI vision (gpt-4o family).

**Privacy**: sends raw page images to the OpenAI API. Per-case
consent gate identical to the Claude provider.

Requires the ``[extraction-cloud-openai]`` extra.
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


class OpenAIProvider(VLMProvider):
    name = "openai"
    requires_network = True
    requires_consent = True

    def __init__(
        self,
        *,
        model: str = "gpt-4o",
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")

    def transcribe_page(self, png_bytes: bytes, *, hints: dict[str, Any]) -> str:
        try:
            from openai import OpenAI  # type: ignore[import-untyped]
        except ModuleNotFoundError as exc:
            raise VLMProviderError(
                "openai provider requires the [extraction-cloud-openai] extra. "
                "Run: uv sync --extra extraction-cloud-openai"
            ) from exc
        if not self.api_key:
            raise VLMProviderError(
                "OPENAI_API_KEY not set. Export it before using the "
                "openai VLM provider."
            )

        client = OpenAI(api_key=self.api_key)
        b64 = base64.standard_b64encode(png_bytes).decode("ascii")
        try:
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": _PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{b64}",
                                },
                            },
                        ],
                    }
                ],
            )
        except Exception as exc:
            raise VLMProviderError(f"openai provider failed: {exc}") from exc
        try:
            return resp.choices[0].message.content or ""
        except (AttributeError, IndexError) as exc:
            raise VLMProviderError(
                f"openai response missing content: {exc}"
            ) from exc

    def describe(self) -> dict[str, Any]:
        return {**super().describe(), "model": self.model}
