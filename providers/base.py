"""Abstract base classes and data structures for LLM providers.

Defines the contract that all provider implementations must follow,
along with shared configuration and result types.
"""

from __future__ import annotations

import enum
import functools
import time as _time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


def retry_on_error(max_retries: int = 2, backoff: float = 1.0):
    """Decorator that retries LLM API calls on transient failures."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (ConnectionError, TimeoutError, OSError) as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        wait = backoff * (2 ** attempt)
                        print(f"  [Provider] Retry {attempt + 1}/{max_retries} "
                              f"after {type(exc).__name__}, waiting {wait:.1f}s...")
                        _time.sleep(wait)
                except Exception as exc:
                    msg = str(exc).lower()
                    if ("rate" in msg or "429" in msg or "quota" in msg) and attempt < max_retries:
                        last_exc = exc
                        wait = backoff * (2 ** attempt)
                        print(f"  [Provider] Rate limited, retry {attempt + 1}/{max_retries} "
                              f"in {wait:.1f}s...")
                        _time.sleep(wait)
                    else:
                        raise
            raise last_exc  # type: ignore[misc]
        return wrapper
    return decorator


class ModelCapability(enum.Enum):
    """Capabilities that a model may support."""

    TEXT_GENERATION = "text_generation"
    VISION = "vision"
    LONG_CONTEXT = "long_context"
    STRUCTURED_OUTPUT = "structured_output"
    CODE_GENERATION = "code_generation"
    FILE_UPLOAD = "file_upload"
    STREAMING = "streaming"


@dataclass(frozen=True)
class ModelInfo:
    """Metadata describing a single model offered by a provider.

    Attributes:
        name: Canonical model identifier (e.g. ``"gemini-2.5-pro"``).
        provider: Provider slug that owns this model (e.g. ``"gemini"``).
        max_context_tokens: Maximum input context window in tokens.
        max_output_tokens: Maximum tokens the model can generate.
        capabilities: Set of :class:`ModelCapability` flags.
        cost_per_1k_input: USD cost per 1 000 input tokens (0 for local).
        cost_per_1k_output: USD cost per 1 000 output tokens (0 for local).
    """

    name: str
    provider: str
    max_context_tokens: int
    max_output_tokens: int
    capabilities: frozenset[ModelCapability] = field(default_factory=frozenset)
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0

    def supports(self, capability: ModelCapability) -> bool:
        """Return ``True`` if the model advertises *capability*."""
        return capability in self.capabilities


@dataclass
class GenerationConfig:
    """Tunable parameters sent alongside a generation request.

    Attributes:
        temperature: Sampling temperature (0.0 – 2.0).
        top_p: Nucleus-sampling probability mass.
        max_output_tokens: Hard cap on generated tokens.
        stop_sequences: Optional list of strings that halt generation.
        response_format: Optional dict for structured output control
            (e.g. ``{"type": "json_object"}``).
    """

    temperature: float = 0.7
    top_p: float = 0.95
    max_output_tokens: int = 4096
    stop_sequences: Optional[list[str]] = None
    response_format: Optional[dict[str, Any]] = None


@dataclass
class GenerationResult:
    """Container for a single model response.

    Attributes:
        text: The generated text content.
        model: Model identifier that produced the response.
        input_tokens: Number of tokens in the prompt.
        output_tokens: Number of tokens generated.
        finish_reason: Why the model stopped (e.g. ``"stop"``, ``"length"``).
        raw_response: Unmodified response object from the SDK, useful for
            debugging or extracting provider-specific metadata.
    """

    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = ""
    raw_response: Any = None


class BaseProvider(ABC):
    """Abstract base class that every LLM provider must implement.

    Sub-classes are responsible for authenticating with their backend,
    enumerating available models, and executing generation requests.
    """

    # ------------------------------------------------------------------
    # Required interface
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Return the provider's recommended default model name."""
        ...

    @abstractmethod
    def available_models(self) -> list[ModelInfo]:
        """Return metadata for every model this provider exposes."""
        ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None,
        images: Optional[list[str | Path]] = None,
    ) -> GenerationResult:
        """Generate text from *prompt*.

        Args:
            prompt: The user message / main prompt text.
            system_prompt: Optional system-level instruction.
            config: Generation hyper-parameters.  Uses sensible defaults
                when ``None``.
            images: Optional list of image paths or URLs for vision models.

        Returns:
            A :class:`GenerationResult` with the model's response.
        """
        ...

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None,
    ) -> dict[str, Any]:
        """Generate a JSON object conforming to *schema*.

        Args:
            prompt: The user message describing the desired output.
            schema: A JSON-Schema-like dict that the output must match.
            system_prompt: Optional system-level instruction.
            config: Generation hyper-parameters.

        Returns:
            A parsed Python dict matching the requested schema.
        """
        ...

    # ------------------------------------------------------------------
    # Optional file-based interface (default raises)
    # ------------------------------------------------------------------

    def upload_file(self, file_path: str | Path) -> object:
        """Upload a file to the provider for later reference.

        Not all providers support this.  The default implementation raises
        :class:`NotImplementedError`.

        Returns:
            A provider-specific file handle / reference object.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support file uploads."
        )

    def generate_with_file(
        self,
        uploaded_file: object,
        prompt: str,
        *,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None,
    ) -> GenerationResult:
        """Generate text using a previously uploaded file as context.

        Args:
            uploaded_file: Handle returned by :meth:`upload_file`.
            prompt: The user message / question about the file.
            system_prompt: Optional system-level instruction.
            config: Generation hyper-parameters.

        Returns:
            A :class:`GenerationResult` with the model's response.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support file-based generation."
        )
