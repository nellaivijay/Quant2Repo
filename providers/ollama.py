"""Ollama local-model provider implementation.

Ollama must be running locally (or at the host specified by ``OLLAMA_HOST``).
No SDK dependency is required – all communication uses the HTTP REST API.

Default endpoint: ``http://localhost:11434``
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
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
# Model catalogue (static defaults – actual availability depends on pulls)
# ---------------------------------------------------------------------------

_LOCAL_CAPABILITIES: frozenset[ModelCapability] = frozenset(
    {
        ModelCapability.TEXT_GENERATION,
        ModelCapability.CODE_GENERATION,
    }
)

_MODELS: list[ModelInfo] = [
    ModelInfo(
        name="deepseek-coder-v2",
        provider="ollama",
        max_context_tokens=128_000,
        max_output_tokens=8_192,
        capabilities=_LOCAL_CAPABILITIES,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
    ),
    ModelInfo(
        name="llama3.1",
        provider="ollama",
        max_context_tokens=128_000,
        max_output_tokens=8_192,
        capabilities=_LOCAL_CAPABILITIES,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
    ),
    ModelInfo(
        name="codellama",
        provider="ollama",
        max_context_tokens=16_000,
        max_output_tokens=4_096,
        capabilities=_LOCAL_CAPABILITIES,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
    ),
    ModelInfo(
        name="mistral",
        provider="ollama",
        max_context_tokens=32_000,
        max_output_tokens=4_096,
        capabilities=_LOCAL_CAPABILITIES,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
    ),
]

_MODEL_LOOKUP: dict[str, ModelInfo] = {m.name: m for m in _MODELS}


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class OllamaProvider(BaseProvider):
    """Provider for locally-hosted models via Ollama."""

    def __init__(
        self,
        host: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        self._host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        if not self._host.startswith("http"):
            self._host = f"http://{self._host}"
        # Strip trailing slash for consistency
        self._host = self._host.rstrip("/")
        self._model_name = model_name or "deepseek-coder-v2"

        if not self._check_connectivity():
            logger.warning(
                "Ollama is not reachable at %s. Requests will fail until it is started.",
                self._host,
            )

        self._models_cache: list | None = None
        self._models_cache_time: float = 0.0

    # ------------------------------------------------------------------
    # BaseProvider interface
    # ------------------------------------------------------------------

    @property
    def default_model(self) -> str:
        return self._model_name

    def available_models(self) -> list[ModelInfo]:
        import time as _t
        now = _t.monotonic()
        if self._models_cache is not None and (now - self._models_cache_time) < 60:
            return self._models_cache
        self._models_cache = list(_MODELS)
        self._models_cache_time = now
        return self._models_cache

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None,
        images: Optional[list[str | Path]] = None,
    ) -> GenerationResult:
        cfg = config or GenerationConfig()

        payload: dict[str, Any] = {
            "model": self._model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": cfg.temperature,
                "top_p": cfg.top_p,
                "num_predict": cfg.max_output_tokens,
            },
        }

        if system_prompt:
            payload["system"] = system_prompt

        if cfg.stop_sequences:
            payload["options"]["stop"] = cfg.stop_sequences

        data = self._post("/api/generate", payload)

        # Ollama returns token counts in some versions
        input_tokens = data.get("prompt_eval_count", 0)
        output_tokens = data.get("eval_count", 0)

        return GenerationResult(
            text=data.get("response", ""),
            model=data.get("model", self._model_name),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason="stop" if data.get("done") else "",
            raw_response=data,
        )

    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None,
    ) -> dict[str, Any]:
        system = system_prompt or ""
        system += (
            "\n\nYou MUST respond with ONLY valid JSON (no markdown fences, "
            "no explanation) matching this schema:\n"
            + json.dumps(schema, indent=2)
        )

        result = self.generate(
            prompt,
            system_prompt=system.strip(),
            config=config,
        )

        text = result.text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Ollama returned invalid JSON – attempting repair")
            # Strip markdown fences if present
            if "```json" in text:
                text = text.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "```" in text:
                text = text.split("```", 1)[1].split("```", 1)[0].strip()
            return json.loads(text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_connectivity(self) -> bool:
        """Return ``True`` if Ollama is reachable."""
        try:
            req = urllib.request.Request(f"{self._host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3):
                return True
        except Exception:  # noqa: BLE001
            return False

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON POST request to the Ollama API.

        Args:
            endpoint: API path (e.g. ``"/api/generate"``).
            payload: JSON-serialisable request body.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            ConnectionError: If Ollama is unreachable.
            RuntimeError: If the API returns an error status.
        """
        url = f"{self._host}{endpoint}"
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.URLError as exc:
            raise ConnectionError(
                f"Cannot reach Ollama at {self._host}. "
                f"Is the server running?  Error: {exc}"
            ) from exc
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode(errors="replace")
            raise RuntimeError(
                f"Ollama API error {exc.code}: {body_text}"
            ) from exc
