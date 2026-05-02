"""Generic HTTP VLM provider — for self-hosted endpoints.

POST a multipart payload of (page-image, prompt) to a user-specified
endpoint and return the transcribed text. Useful for self-hosted
Mistral OCR, vLLM serving Qwen2-VL, or any other in-house service
that speaks a small JSON contract.

The endpoint is expected to accept JSON of the form::

    {"image_b64": "...", "prompt": "..."}

and reply with::

    {"text": "..."}

If the user's endpoint speaks a different shape, subclass this
provider and override ``transcribe_page``.

Whether or not this counts as "leaving the machine" depends entirely
on what the user's endpoint is. The privacy gate is conservative —
``requires_network=True`` — and the consent prompt records the URL.
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any

from .base import VLMProvider, VLMProviderError


_DEFAULT_PROMPT = (
    "You are an OCR transcriber. Transcribe ALL visible text in this page "
    "image into clean Markdown. Preserve headings, lists, and tables; do "
    "NOT hallucinate text that isn't visible; do NOT summarize."
)


class HTTPProvider(VLMProvider):
    name = "http"
    requires_network = True
    requires_consent = True

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        prompt: str = _DEFAULT_PROMPT,
        timeout_s: float = 60.0,
        bearer_token: str | None = None,
    ) -> None:
        self.endpoint = endpoint or os.environ.get("PAT_VLM_HTTP_ENDPOINT")
        self.prompt = prompt
        self.timeout_s = timeout_s
        self.bearer_token = bearer_token or os.environ.get("PAT_VLM_HTTP_TOKEN")

    def transcribe_page(self, png_bytes: bytes, *, hints: dict[str, Any]) -> str:
        if not self.endpoint:
            raise VLMProviderError(
                "http provider requires endpoint=... or PAT_VLM_HTTP_ENDPOINT env var."
            )

        # stdlib http.client + urllib so we don't pull a third-party
        # HTTP library in for this provider.
        import urllib.error
        import urllib.request

        body = json.dumps(
            {
                "image_b64": base64.standard_b64encode(png_bytes).decode("ascii"),
                "prompt": self.prompt,
                "hints": hints,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        if self.bearer_token:
            req.add_header("Authorization", f"Bearer {self.bearer_token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise VLMProviderError(f"http provider request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise VLMProviderError(
                f"http provider returned non-JSON response: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise VLMProviderError(
                f"http provider response not an object: {type(payload).__name__}"
            )
        text = payload.get("text") or payload.get("markdown")
        if not isinstance(text, str):
            raise VLMProviderError(
                "http provider response missing 'text' / 'markdown' string"
            )
        return text

    def describe(self) -> dict[str, Any]:
        return {
            **super().describe(),
            "endpoint": self.endpoint,
            # Don't echo the bearer token into the recipe — leak risk.
            "bearer_token_set": bool(self.bearer_token),
        }
