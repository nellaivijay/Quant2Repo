"""Provider registry – discover, create, and manage LLM providers.

The registry acts as a single entry-point for the rest of the system:
it knows which provider back-ends exist, can auto-detect which ones
have valid credentials, and can recommend providers for specific
capabilities.
"""

from __future__ import annotations

import importlib
import logging
import os
from typing import Any, Optional

from .base import BaseProvider, ModelCapability

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Capability → provider preference orders
# ---------------------------------------------------------------------------

_CAPABILITY_PREFERENCES: dict[ModelCapability, list[str]] = {
    ModelCapability.LONG_CONTEXT: ["gemini", "anthropic", "openai", "ollama"],
    ModelCapability.VISION: ["gemini", "openai", "anthropic", "ollama"],
    ModelCapability.CODE_GENERATION: ["anthropic", "openai", "gemini", "ollama"],
    ModelCapability.STRUCTURED_OUTPUT: ["openai", "gemini", "anthropic", "ollama"],
    ModelCapability.TEXT_GENERATION: ["openai", "anthropic", "gemini", "ollama"],
    ModelCapability.FILE_UPLOAD: ["gemini"],
    ModelCapability.STREAMING: ["openai", "anthropic", "gemini", "ollama"],
}


class ProviderRegistry:
    """Central catalogue of known LLM providers.

    Each entry maps a short name (e.g. ``"gemini"``) to the module path,
    class name, and environment-variable key used for authentication.
    """

    _PROVIDERS: dict[str, tuple[str, str, str]] = {
        # name -> (module_path, class_name, env_key)
        "gemini": (
            "providers.gemini",
            "GeminiProvider",
            "GEMINI_API_KEY",
        ),
        "openai": (
            "providers.openai_provider",
            "OpenAIProvider",
            "OPENAI_API_KEY",
        ),
        "anthropic": (
            "providers.anthropic_provider",
            "AnthropicProvider",
            "ANTHROPIC_API_KEY",
        ),
        "ollama": (
            "providers.ollama",
            "OllamaProvider",
            "OLLAMA_HOST",  # presence is optional; connectivity is checked instead
        ),
    }

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @classmethod
    def list_providers(cls) -> list[str]:
        """Return the names of all registered providers."""
        return list(cls._PROVIDERS.keys())

    @classmethod
    def create(
        cls,
        provider_name: str,
        *,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> BaseProvider:
        """Instantiate a provider by name.

        Args:
            provider_name: Registered short name (e.g. ``"gemini"``).
            api_key: Explicit API key.  When *None* the provider will
                fall back to its environment variable.
            model_name: Override the provider's default model.

        Returns:
            A ready-to-use :class:`BaseProvider` instance.

        Raises:
            KeyError: If *provider_name* is not registered.
            ImportError: If the provider's SDK is not installed.
        """
        if provider_name not in cls._PROVIDERS:
            raise KeyError(
                f"Unknown provider {provider_name!r}. "
                f"Available: {', '.join(cls._PROVIDERS)}"
            )

        module_path, class_name, _env_key = cls._PROVIDERS[provider_name]
        module = importlib.import_module(module_path)
        provider_cls = getattr(module, class_name)

        kwargs: dict[str, Any] = {}
        if api_key is not None:
            # Ollama uses 'host' instead of 'api_key'
            if provider_name == "ollama":
                kwargs["host"] = api_key
            else:
                kwargs["api_key"] = api_key
        if model_name is not None:
            kwargs["model_name"] = model_name

        return provider_cls(**kwargs)

    @classmethod
    def detect_available(cls) -> list[str]:
        """Return providers whose credentials / connectivity are present.

        * For cloud providers the corresponding env-var must be set.
        * For Ollama, a quick HTTP health-check is performed.
        """
        available: list[str] = []
        for name, (_mod, _cls, env_key) in cls._PROVIDERS.items():
            if name == "ollama":
                if cls._check_ollama():
                    available.append(name)
            elif os.environ.get(env_key):
                available.append(name)
        return available

    @classmethod
    def best_for(cls, capability: ModelCapability) -> str:
        """Return the best *available* provider for *capability*.

        Providers are tried in a hand-tuned preference order.  Only those
        that are currently available (API key set / connectivity) are
        considered.

        Raises:
            RuntimeError: If no available provider supports the capability.
        """
        available = set(cls.detect_available())
        preferences = _CAPABILITY_PREFERENCES.get(
            capability,
            ["openai", "anthropic", "gemini", "ollama"],
        )
        for name in preferences:
            if name in available:
                return name
        raise RuntimeError(
            f"No available provider supports {capability.value!r}. "
            f"Available providers: {available or 'none'}"
        )

    @classmethod
    def estimate_cost(
        cls,
        provider_name: str,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Estimate the USD cost for a generation request.

        The provider is instantiated transiently to look up model metadata.
        Returns ``0.0`` for local providers or unknown models.
        """
        try:
            provider = cls.create(provider_name)
            for m in provider.available_models():
                if m.name == model_name:
                    cost = (
                        m.cost_per_1k_input * (input_tokens / 1000)
                        + m.cost_per_1k_output * (output_tokens / 1000)
                    )
                    return round(cost, 6)
        except Exception:  # noqa: BLE001
            logger.debug(
                "Could not estimate cost for %s/%s", provider_name, model_name
            )
        return 0.0

    @classmethod
    def register(
        cls,
        name: str,
        module_path: str,
        class_name: str,
        env_key: str,
    ) -> None:
        """Register a custom / third-party provider.

        Args:
            name: Short identifier (e.g. ``"my_provider"``).
            module_path: Dot-separated Python module path.
            class_name: Name of the :class:`BaseProvider` subclass.
            env_key: Environment variable used for authentication.
        """
        cls._PROVIDERS[name] = (module_path, class_name, env_key)
        logger.info("Registered custom provider %r", name)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_ollama() -> bool:
        """Return ``True`` if Ollama is reachable."""
        import urllib.request
        import urllib.error

        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        if not host.startswith("http"):
            host = f"http://{host}"
        try:
            req = urllib.request.Request(f"{host}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2):
                return True
        except Exception:  # noqa: BLE001
            return False


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def get_provider(
    provider_name: Optional[str] = None,
    *,
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    required_capability: Optional[ModelCapability] = None,
) -> BaseProvider:
    """High-level helper to obtain a ready-to-use provider.

    Resolution order:

    1. If *provider_name* is given explicitly, use it directly.
    2. If *required_capability* is given, pick the best available provider
       for that capability.
    3. Otherwise, pick the first available provider from the default
       preference list: ``openai → anthropic → gemini → ollama``.

    Args:
        provider_name: Explicit provider slug.
        model_name: Override the provider's default model.
        api_key: Explicit API key / host.
        required_capability: Capability the provider **must** support.

    Returns:
        An initialised :class:`BaseProvider`.

    Raises:
        RuntimeError: If no suitable provider is available.
    """
    if provider_name is not None:
        return ProviderRegistry.create(
            provider_name, api_key=api_key, model_name=model_name
        )

    if required_capability is not None:
        best = ProviderRegistry.best_for(required_capability)
        return ProviderRegistry.create(
            best, api_key=api_key, model_name=model_name
        )

    # Auto-detect: try default preference order
    available = ProviderRegistry.detect_available()
    default_order = ["openai", "anthropic", "gemini", "ollama"]
    for name in default_order:
        if name in available:
            logger.info("Auto-selected provider: %s", name)
            return ProviderRegistry.create(
                name, api_key=api_key, model_name=model_name
            )

    raise RuntimeError(
        "No LLM provider available. Set one of OPENAI_API_KEY, "
        "ANTHROPIC_API_KEY, or GEMINI_API_KEY, or start Ollama locally."
    )
