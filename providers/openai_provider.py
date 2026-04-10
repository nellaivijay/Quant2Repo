"""OpenAI provider implementation.

Requires the ``openai`` package::

    pip install openai

Set the ``OPENAI_API_KEY`` environment variable or pass *api_key* directly.
"""

from __future__ import annotations

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

_OPENAI_CAPABILITIES: frozenset[ModelCapability] = frozenset(
    {
        ModelCapability.STRUCTURED_OUTPUT,
        ModelCapability.VISION,
        ModelCapability.CODE_GENERATION,
        ModelCapability.TEXT_GENERATION,
        ModelCapability.STREAMING,
    }
)

_REASONING_CAPABILITIES: frozenset[ModelCapability] = frozenset(
    {
        ModelCapability.STRUCTURED_OUTPUT,
        ModelCapability.CODE_GENERATION,
        ModelCapability.TEXT_GENERATION,
        ModelCapability.LONG_CONTEXT,
    }
)

_MODELS: list[ModelInfo] = [
    ModelInfo(
        name="gpt-4o",
        provider="openai",
        max_context_tokens=128_000,
        max_output_tokens=16_384,
        capabilities=_OPENAI_CAPABILITIES,
        cost_per_1k_input=0.0025,
        cost_per_1k_output=0.01,
    ),
    ModelInfo(
        name="gpt-4-turbo",
        provider="openai",
        max_context_tokens=128_000,
        max_output_tokens=4_096,
        capabilities=_OPENAI_CAPABILITIES,
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.03,
    ),
    ModelInfo(
        name="o3",
        provider="openai",
        max_context_tokens=200_000,
        max_output_tokens=100_000,
        capabilities=_REASONING_CAPABILITIES,
        cost_per_1k_input=0.01,
        cost_per_1k_output=0.04,
    ),
    ModelInfo(
        name="o1",
        provider="openai",
        max_context_tokens=200_000,
        max_output_tokens=100_000,
        capabilities=_REASONING_CAPABILITIES,
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.06,
    ),
]

_MODEL_LOOKUP: dict[str, ModelInfo] = {m.name: m for m in _MODELS}

# Models that use the reasoning API (no system message, no temperature)
_REASONING_MODELS: set[str] = {"o3", "o1", "o1-preview", "o1-mini"}


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class OpenAIProvider(BaseProvider):
    """Provider for OpenAI's GPT and reasoning model families."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        try:
            import openai  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "The openai package is required for the OpenAI provider. "
                "Install it with:  pip install openai"
            ) from exc

        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "No OpenAI API key provided. Set OPENAI_API_KEY or pass api_key=."
            )

        self._client = openai.OpenAI(api_key=self._api_key)
        self._model_name = model_name or "gpt-4o"

    @property
    def _is_reasoning_model(self) -> bool:
        return self._model_name in _REASONING_MODELS

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
        messages: list[dict[str, Any]] = []

        # Reasoning models don't support a system message
        if system_prompt and not self._is_reasoning_model:
            messages.append({"role": "system", "content": system_prompt})
        elif system_prompt and self._is_reasoning_model:
            # Prepend system context to the user prompt for reasoning models
            prompt = f"{system_prompt}\n\n{prompt}"

        # Build user message content
        content: Any
        if images:
            parts: list[dict[str, Any]] = []
            for img in images:
                img_str = str(img)
                if img_str.startswith(("http://", "https://")):
                    parts.append(
                        {"type": "image_url", "image_url": {"url": img_str}}
                    )
                else:
                    import base64

                    with open(img_str, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    mime = "image/png"
                    if img_str.lower().endswith(".jpg") or img_str.lower().endswith(".jpeg"):
                        mime = "image/jpeg"
                    elif img_str.lower().endswith(".gif"):
                        mime = "image/gif"
                    elif img_str.lower().endswith(".webp"):
                        mime = "image/webp"
                    parts.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime};base64,{b64}"
                            },
                        }
                    )
            parts.append({"type": "text", "text": prompt})
            content = parts
        else:
            content = prompt

        messages.append({"role": "user", "content": content})

        # Build API kwargs
        kwargs: dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
        }

        if not self._is_reasoning_model:
            kwargs["temperature"] = cfg.temperature
            kwargs["top_p"] = cfg.top_p
            kwargs["max_tokens"] = cfg.max_output_tokens
            if cfg.stop_sequences:
                kwargs["stop"] = cfg.stop_sequences
        else:
            kwargs["max_completion_tokens"] = cfg.max_output_tokens

        response = self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        return GenerationResult(
            text=choice.message.content or "",
            model=response.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason=choice.finish_reason or "",
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
            "\n\nYou MUST respond with valid JSON matching this schema:\n"
            + json.dumps(schema, indent=2)
        )

        messages: list[dict[str, Any]] = []
        if not self._is_reasoning_model:
            messages.append({"role": "system", "content": system.strip()})
            messages.append({"role": "user", "content": prompt})
        else:
            messages.append(
                {"role": "user", "content": f"{system.strip()}\n\n{prompt}"}
            )

        kwargs: dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
        }

        if not self._is_reasoning_model:
            kwargs["temperature"] = cfg.temperature
            kwargs["top_p"] = cfg.top_p
            kwargs["max_tokens"] = cfg.max_output_tokens
            kwargs["response_format"] = {"type": "json_object"}
        else:
            kwargs["max_completion_tokens"] = cfg.max_output_tokens

        response = self._client.chat.completions.create(**kwargs)
        text = (response.choices[0].message.content or "").strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("OpenAI returned invalid JSON – attempting repair")
            if "```json" in text:
                text = text.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "```" in text:
                text = text.split("```", 1)[1].split("```", 1)[0].strip()
            return json.loads(text)
