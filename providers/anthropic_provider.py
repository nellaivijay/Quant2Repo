"""Anthropic Claude provider implementation.

Requires the ``anthropic`` package::

    pip install anthropic

Set the ``ANTHROPIC_API_KEY`` environment variable or pass *api_key* directly.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from .base import (
    BaseProvider,
    GenerationConfig,
    GenerationResult,
    ModelCapability,
    ModelInfo,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model catalogue
# ---------------------------------------------------------------------------

_CLAUDE_CAPABILITIES: frozenset[ModelCapability] = frozenset(
    {
        ModelCapability.LONG_CONTEXT,
        ModelCapability.CODE_GENERATION,
        ModelCapability.VISION,
        ModelCapability.TEXT_GENERATION,
        ModelCapability.STRUCTURED_OUTPUT,
        ModelCapability.STREAMING,
    }
)

_MODELS: list[ModelInfo] = [
    ModelInfo(
        name="claude-sonnet-4-20250514",
        provider="anthropic",
        max_context_tokens=200_000,
        max_output_tokens=16_384,
        capabilities=_CLAUDE_CAPABILITIES,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
    ),
    ModelInfo(
        name="claude-opus-4-20250514",
        provider="anthropic",
        max_context_tokens=200_000,
        max_output_tokens=32_000,
        capabilities=_CLAUDE_CAPABILITIES,
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
    ),
    ModelInfo(
        name="claude-3-5-sonnet-20241022",
        provider="anthropic",
        max_context_tokens=200_000,
        max_output_tokens=8_192,
        capabilities=_CLAUDE_CAPABILITIES,
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
    ),
]

_MODEL_LOOKUP: dict[str, ModelInfo] = {m.name: m for m in _MODELS}

_MIME_MAP: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class AnthropicProvider(BaseProvider):
    """Provider for Anthropic's Claude model family."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        try:
            import anthropic  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "The anthropic package is required for the Anthropic provider. "
                "Install it with:  pip install anthropic"
            ) from exc

        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "No Anthropic API key provided. Set ANTHROPIC_API_KEY or pass api_key=."
            )

        self._client = anthropic.Anthropic(api_key=self._api_key)
        self._model_name = model_name or "claude-sonnet-4-20250514"

    # ------------------------------------------------------------------
    # BaseProvider interface
    # ------------------------------------------------------------------

    @property
    def default_model(self) -> str:
        return self._model_name

    def available_models(self) -> list[ModelInfo]:
        return list(_MODELS)

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None,
        images: Optional[list[str | Path]] = None,
    ) -> GenerationResult:
        cfg = config or GenerationConfig()

        # Build content blocks
        content: list[dict[str, Any]] = []
        if images:
            for img in images:
                img_str = str(img)
                if img_str.startswith(("http://", "https://")):
                    content.append(
                        {
                            "type": "image",
                            "source": {"type": "url", "url": img_str},
                        }
                    )
                else:
                    path = Path(img_str)
                    suffix = path.suffix.lower()
                    mime = _MIME_MAP.get(suffix, "image/png")
                    with open(path, "rb") as f:
                        b64_data = base64.standard_b64encode(f.read()).decode()
                    content.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime,
                                "data": b64_data,
                            },
                        }
                    )
        content.append({"type": "text", "text": prompt})

        kwargs: dict[str, Any] = {
            "model": self._model_name,
            "max_tokens": cfg.max_output_tokens,
            "messages": [{"role": "user", "content": content}],
            "temperature": cfg.temperature,
            "top_p": cfg.top_p,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if cfg.stop_sequences:
            kwargs["stop_sequences"] = cfg.stop_sequences

        response = self._client.messages.create(**kwargs)

        text_parts = [
            block.text for block in response.content if block.type == "text"
        ]
        text = "\n".join(text_parts)

        return GenerationResult(
            text=text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            finish_reason=response.stop_reason or "",
            raw_response=response,
        )

    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None,
    ) -> dict[str, Any]:
        cfg = config or GenerationConfig()

        system = system_prompt or ""
        system += (
            "\n\nYou MUST respond with ONLY valid JSON (no markdown fences, "
            "no explanation) matching this schema:\n"
            + json.dumps(schema, indent=2)
        )

        kwargs: dict[str, Any] = {
            "model": self._model_name,
            "max_tokens": cfg.max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "system": system.strip(),
            "temperature": cfg.temperature,
            "top_p": cfg.top_p,
        }
        if cfg.stop_sequences:
            kwargs["stop_sequences"] = cfg.stop_sequences

        response = self._client.messages.create(**kwargs)

        text_parts = [
            block.text for block in response.content if block.type == "text"
        ]
        text = "\n".join(text_parts).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Anthropic returned invalid JSON – attempting repair")
            # Strip markdown fences if present
            if "```json" in text:
                text = text.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "```" in text:
                text = text.split("```", 1)[1].split("```", 1)[0].strip()
            return json.loads(text)
