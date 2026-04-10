"""Google Gemini provider implementation.

Requires the ``google-generativeai`` package::

    pip install google-generativeai

Set the ``GEMINI_API_KEY`` environment variable or pass *api_key* directly.
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

_GEMINI_CAPABILITIES: frozenset[ModelCapability] = frozenset(
    {
        ModelCapability.LONG_CONTEXT,
        ModelCapability.VISION,
        ModelCapability.FILE_UPLOAD,
        ModelCapability.STRUCTURED_OUTPUT,
        ModelCapability.CODE_GENERATION,
        ModelCapability.TEXT_GENERATION,
        ModelCapability.STREAMING,
    }
)

_MODELS: list[ModelInfo] = [
    ModelInfo(
        name="gemini-2.5-pro",
        provider="gemini",
        max_context_tokens=1_048_576,
        max_output_tokens=65_536,
        capabilities=_GEMINI_CAPABILITIES,
        cost_per_1k_input=0.00125,
        cost_per_1k_output=0.01,
    ),
    ModelInfo(
        name="gemini-2.0-flash",
        provider="gemini",
        max_context_tokens=1_048_576,
        max_output_tokens=8_192,
        capabilities=_GEMINI_CAPABILITIES,
        cost_per_1k_input=0.0001,
        cost_per_1k_output=0.0004,
    ),
    ModelInfo(
        name="gemini-1.5-pro",
        provider="gemini",
        max_context_tokens=2_097_152,
        max_output_tokens=8_192,
        capabilities=_GEMINI_CAPABILITIES,
        cost_per_1k_input=0.00125,
        cost_per_1k_output=0.005,
    ),
]

_MODEL_LOOKUP: dict[str, ModelInfo] = {m.name: m for m in _MODELS}


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class GeminiProvider(BaseProvider):
    """Provider for Google's Gemini family of models."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        try:
            import google.generativeai as genai  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "The google-generativeai package is required for the Gemini "
                "provider. Install it with:  pip install google-generativeai"
            ) from exc

        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "No Gemini API key provided. Set GEMINI_API_KEY or pass api_key=."
            )

        genai.configure(api_key=self._api_key)
        self._genai = genai
        self._model_name = model_name or "gemini-2.5-pro"

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
        model = self._genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system_prompt,
        )

        gen_config = self._genai.GenerationConfig(
            temperature=cfg.temperature,
            top_p=cfg.top_p,
            max_output_tokens=cfg.max_output_tokens,
            stop_sequences=cfg.stop_sequences,
        )

        # Build content parts
        parts: list[Any] = []
        if images:
            import PIL.Image  # type: ignore[import-untyped]

            for img in images:
                img_path = Path(img) if isinstance(img, str) else img
                if img_path.exists():
                    parts.append(PIL.Image.open(img_path))
                else:
                    # Assume URL string – let the SDK handle it
                    parts.append(str(img))
        parts.append(prompt)

        response = model.generate_content(parts, generation_config=gen_config)

        # Extract usage metadata
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0)
            output_tokens = getattr(
                response.usage_metadata, "candidates_token_count", 0
            )

        finish_reason = ""
        if response.candidates:
            finish_reason = str(response.candidates[0].finish_reason)

        return GenerationResult(
            text=response.text,
            model=self._model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason=finish_reason,
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

        model = self._genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system.strip(),
        )

        gen_config = self._genai.GenerationConfig(
            temperature=cfg.temperature,
            top_p=cfg.top_p,
            max_output_tokens=cfg.max_output_tokens,
            stop_sequences=cfg.stop_sequences,
            response_mime_type="application/json",
        )

        response = model.generate_content(prompt, generation_config=gen_config)
        text = response.text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Gemini returned invalid JSON – attempting repair")
            # Attempt to extract JSON from markdown fenced block
            if "```json" in text:
                text = text.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "```" in text:
                text = text.split("```", 1)[1].split("```", 1)[0].strip()
            return json.loads(text)

    # ------------------------------------------------------------------
    # File-based interface
    # ------------------------------------------------------------------

    def upload_file(self, file_path: str | Path) -> object:
        """Upload a file via the Gemini File API."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        uploaded = self._genai.upload_file(str(path))
        logger.info("Uploaded %s → %s", path.name, uploaded.name)
        return uploaded

    def generate_with_file(
        self,
        uploaded_file: object,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None,
    ) -> GenerationResult:
        cfg = config or GenerationConfig()
        model = self._genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system_prompt,
        )

        gen_config = self._genai.GenerationConfig(
            temperature=cfg.temperature,
            top_p=cfg.top_p,
            max_output_tokens=cfg.max_output_tokens,
            stop_sequences=cfg.stop_sequences,
        )

        response = model.generate_content(
            [uploaded_file, prompt],
            generation_config=gen_config,
        )

        input_tokens = 0
        output_tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0)
            output_tokens = getattr(
                response.usage_metadata, "candidates_token_count", 0
            )

        finish_reason = ""
        if response.candidates:
            finish_reason = str(response.candidates[0].finish_reason)

        return GenerationResult(
            text=response.text,
            model=self._model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason=finish_reason,
            raw_response=response,
        )
