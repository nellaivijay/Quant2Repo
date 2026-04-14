# Provider System and Configuration

**Multi-model provider abstraction, auto-detection, capability-based routing, and pipeline configuration.**

Source: `providers/` package, `config.py` | Related: [Architecture Overview](Architecture-Overview), [Usage Guide](Usage-Guide), [Pipeline Stages Deep Dive](Pipeline-Stages-Deep-Dive)

---

## Table of Contents

1. [Provider Architecture](#1-provider-architecture)
2. [Available Providers](#2-available-providers)
3. [Provider Selection Logic](#3-provider-selection-logic)
4. [Cost Estimation](#4-cost-estimation)
5. [Configuration System](#5-configuration-system)
6. [Adding a Custom Provider](#6-adding-a-custom-provider)
7. [Temperature and Token Tuning](#7-temperature-and-token-tuning)

---

## 1. Provider Architecture

Quant2Repo uses a provider abstraction layer that decouples the pipeline from any specific LLM vendor. Every provider implements the same interface, making it possible to switch between Google Gemini, OpenAI, Anthropic, or a local Ollama instance with a single flag.

### Directory Structure

```
providers/
  __init__.py              # Package init, re-exports key symbols
  base.py                  # BaseProvider ABC, GenerationConfig, GenerationResult, ModelInfo, ModelCapability
  gemini.py                # Google Gemini (2.5 Pro, 2.0 Flash, 1.5 Pro)
  openai_provider.py       # OpenAI GPT (4o, 4-turbo, o3, o1)
  anthropic_provider.py    # Anthropic Claude (Sonnet 4, Opus 4, 3.5 Sonnet)
  ollama.py                # Local Ollama (DeepSeek, Llama 3.1, CodeLlama, Mistral)
  registry.py              # ProviderRegistry + get_provider() convenience function
```

### BaseProvider Abstract Class

Every provider must subclass `BaseProvider` (defined in `providers/base.py`) and implement all abstract methods. The class also exposes optional methods for providers that support file-based workflows.

```python
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
            config: Generation hyper-parameters. Uses sensible defaults when None.
            images: Optional list of image paths or URLs for vision models.

        Returns:
            A GenerationResult with the model's response.
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
    # Optional file-based interface (default raises NotImplementedError)
    # ------------------------------------------------------------------

    def upload_file(self, file_path: str | Path) -> object:
        """Upload a file to the provider for later reference."""
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
        """Generate text using a previously uploaded file as context."""
        raise NotImplementedError(
            f"{type(self).__name__} does not support file-based generation."
        )
```

### Abstract Methods

| Method | Purpose |
|--------|---------|
| `default_model` | Property returning the provider's recommended model name |
| `available_models()` | Returns list of `ModelInfo` for all supported models |
| `generate()` | Text generation from prompt, supports images for vision |
| `generate_structured()` | JSON generation conforming to a schema |

### Optional Methods

| Method | Purpose | Supported By |
|--------|---------|-------------|
| `upload_file()` | Upload file for later reference | Gemini |
| `generate_with_file()` | Generate using uploaded file as context | Gemini |

> **Note:** The default implementations of `upload_file()` and `generate_with_file()` raise `NotImplementedError`. Only providers with native file upload APIs (currently Gemini via the File API) override these methods.

---

### ModelCapability Enum

The `ModelCapability` enum (defined in `providers/base.py`) describes what a model can do. This is used by the registry for capability-based routing and by the pipeline to verify that a selected model meets the requirements of each stage.

```python
class ModelCapability(enum.Enum):
    """Capabilities that a model may support."""

    TEXT_GENERATION = "text_generation"
    VISION = "vision"
    LONG_CONTEXT = "long_context"
    STRUCTURED_OUTPUT = "structured_output"
    CODE_GENERATION = "code_generation"
    FILE_UPLOAD = "file_upload"
    STREAMING = "streaming"
```

| Capability | Value | Description |
|------------|-------|-------------|
| `TEXT_GENERATION` | `text_generation` | Basic text generation |
| `VISION` | `vision` | Image understanding and analysis |
| `LONG_CONTEXT` | `long_context` | 100K+ token context window |
| `STRUCTURED_OUTPUT` | `structured_output` | JSON-schema-constrained output |
| `CODE_GENERATION` | `code_generation` | Optimized for code generation tasks |
| `FILE_UPLOAD` | `file_upload` | Native file upload API (e.g. PDF ingestion) |
| `STREAMING` | `streaming` | Token-by-token streaming responses |

---

### ModelInfo Dataclass

Each model is described by a frozen `ModelInfo` dataclass that captures its technical specifications and pricing. The `supports()` convenience method checks for a specific capability.

```python
@dataclass(frozen=True)
class ModelInfo:
    """Metadata describing a single model offered by a provider."""

    name: str                                    # e.g. "gemini-2.5-pro"
    provider: str                                # e.g. "gemini"
    max_context_tokens: int                      # Maximum input context window
    max_output_tokens: int                       # Maximum generated tokens
    capabilities: frozenset[ModelCapability] = field(default_factory=frozenset)
    cost_per_1k_input: float = 0.0               # USD per 1K input tokens
    cost_per_1k_output: float = 0.0              # USD per 1K output tokens

    def supports(self, capability: ModelCapability) -> bool:
        """Return True if the model advertises *capability*."""
        return capability in self.capabilities
```

**Usage:**

```python
from providers.base import ModelInfo, ModelCapability

model = ModelInfo(
    name="gemini-2.5-pro",
    provider="gemini",
    max_context_tokens=1_048_576,
    max_output_tokens=65_536,
    capabilities=frozenset({ModelCapability.VISION, ModelCapability.LONG_CONTEXT}),
    cost_per_1k_input=0.00125,
    cost_per_1k_output=0.01,
)

assert model.supports(ModelCapability.VISION) is True
assert model.supports(ModelCapability.FILE_UPLOAD) is False  # not in this subset
```

---

### GenerationConfig Dataclass

Controls the hyper-parameters sent with every generation request. Pipeline stages override specific fields (e.g. `temperature=0.1` for strategy extraction, `max_output_tokens=16384` for code generation).

```python
@dataclass
class GenerationConfig:
    """Tunable parameters sent alongside a generation request."""

    temperature: float = 0.7           # Sampling temperature (0.0 - 2.0)
    top_p: float = 0.95                # Nucleus-sampling probability mass
    max_output_tokens: int = 4096      # Hard cap on generated tokens
    stop_sequences: list[str] | None = None        # Strings that halt generation
    response_format: dict | None = None            # Structured output control
```

**Example – precise code generation:**

```python
from providers.base import GenerationConfig

code_config = GenerationConfig(
    temperature=0.15,
    top_p=0.95,
    max_output_tokens=16384,
    stop_sequences=None,
    response_format=None,
)
```

---

### GenerationResult Dataclass

Every `generate()` call returns a `GenerationResult` that wraps the generated text alongside token-usage metadata and the raw SDK response for debugging.

```python
@dataclass
class GenerationResult:
    """Container for a single model response."""

    text: str                  # The generated text content
    model: str                 # Model identifier that produced the response
    input_tokens: int = 0      # Number of tokens in the prompt
    output_tokens: int = 0     # Number of tokens generated
    finish_reason: str = ""    # Why the model stopped (e.g. "stop", "length")
    raw_response: Any = None   # Unmodified SDK response object
```

**Token counts** are used by the cost estimator and for logging. The `finish_reason` helps detect truncated outputs (`"length"` indicates the model hit the token limit).

---

### The `retry_on_error` Decorator

All provider methods that call external APIs are wrapped with `retry_on_error`, which provides automatic retry with exponential backoff for transient failures.

```python
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
                    if ("rate" in msg or "429" in msg or "quota" in msg) \
                       and attempt < max_retries:
                        last_exc = exc
                        wait = backoff * (2 ** attempt)
                        print(f"  [Provider] Rate limited, retry "
                              f"{attempt + 1}/{max_retries} in {wait:.1f}s...")
                        _time.sleep(wait)
                    else:
                        raise
            raise last_exc
        return wrapper
    return decorator
```

**Retry behaviour summary:**

| Trigger | Condition |
|---------|-----------|
| Network errors | `ConnectionError`, `TimeoutError`, `OSError` |
| Rate limits | Exception message contains `"rate"`, `"429"`, or `"quota"` |
| Backoff schedule | Exponential: 1s, 2s, 4s, ... (`backoff * 2^attempt`) |
| Default retries | `max_retries=2` (3 total attempts) |
| Non-retryable errors | All other exceptions are re-raised immediately |

---

## 2. Available Providers

Quant2Repo ships with four provider implementations. Each can be used standalone or mixed within the same session via the registry.

---

### 2.1 Google Gemini (Recommended)

**Source:** `providers/gemini.py` | **Class:** `GeminiProvider`

Gemini is the recommended default for Quant2Repo due to its native PDF upload via the File API, 1M-2M token context window, competitive pricing, and support for all pipeline capabilities.

**Setup:**

```bash
# Install the SDK
pip install google-generativeai

# Set API key
export GEMINI_API_KEY="your_key_here"
```

**Models:**

| Model | Context | Max Output | Capabilities | Input Cost | Output Cost |
|-------|---------|-----------|--------------|------------|-------------|
| `gemini-2.5-pro` | 1,048,576 | 65,536 | ALL | $0.00125/1K | $0.01/1K |
| `gemini-2.0-flash` | 1,048,576 | 8,192 | ALL | $0.0001/1K | $0.0004/1K |
| `gemini-1.5-pro` | 2,097,152 | 8,192 | ALL | $0.00125/1K | $0.005/1K |

> **ALL** = TEXT_GENERATION, VISION, LONG_CONTEXT, STRUCTURED_OUTPUT, CODE_GENERATION, FILE_UPLOAD, STREAMING

**Unique features:**

- **Native PDF upload** via the Gemini File API — upload once, reference in multiple prompts:
  ```python
  provider = get_provider("gemini")
  uploaded = provider.upload_file("paper.pdf")
  result = provider.generate_with_file(uploaded, "Extract the trading strategy.")
  ```
- **2M token context** with `gemini-1.5-pro` — process entire papers in a single prompt
- **Vision** for page images — render PDF pages as images and pass to `generate()` via the `images` parameter
- **Structured JSON output** using `response_mime_type="application/json"` in generation config, providing more reliable JSON than prompt-based approaches

**Default model:** `gemini-2.5-pro`

---

### 2.2 OpenAI

**Source:** `providers/openai_provider.py` | **Class:** `OpenAIProvider`

OpenAI provides strong structured output (native `response_format={"type": "json_object"}`) and excellent code generation. The provider includes special handling for reasoning models (o3, o1) which do not support system messages or temperature.

**Setup:**

```bash
# Install the SDK
pip install openai

# Set API key
export OPENAI_API_KEY="your_key_here"
```

**Models:**

| Model | Context | Max Output | Capabilities | Input Cost | Output Cost |
|-------|---------|-----------|--------------|------------|-------------|
| `gpt-4o` | 128,000 | 16,384 | TEXT, VISION, CODE, STRUCTURED, STREAMING | $0.0025/1K | $0.01/1K |
| `gpt-4-turbo` | 128,000 | 4,096 | TEXT, VISION, CODE, STRUCTURED, STREAMING | $0.01/1K | $0.03/1K |
| `o3` | 200,000 | 100,000 | TEXT, CODE, STRUCTURED, LONG_CONTEXT | $0.01/1K | $0.04/1K |
| `o1` | 200,000 | 100,000 | TEXT, CODE, STRUCTURED, LONG_CONTEXT | $0.015/1K | $0.06/1K |

**Reasoning model handling:**

Models in the `_REASONING_MODELS` set (`o3`, `o1`, `o1-preview`, `o1-mini`) receive special treatment:
- System messages are prepended to the user prompt instead of sent as a separate role
- Temperature and top_p parameters are not sent (the API ignores them)
- `max_completion_tokens` is used instead of `max_tokens`

**Default model:** `gpt-4o`

---

### 2.3 Anthropic

**Source:** `providers/anthropic_provider.py` | **Class:** `AnthropicProvider`

Anthropic Claude excels at code reasoning and long-context understanding. All models support 200K context windows, making them suitable for processing full research papers.

**Setup:**

```bash
# Install the SDK
pip install anthropic

# Set API key
export ANTHROPIC_API_KEY="your_key_here"
```

**Models:**

| Model | Context | Max Output | Capabilities | Input Cost | Output Cost |
|-------|---------|-----------|--------------|------------|-------------|
| `claude-sonnet-4-20250514` | 200,000 | 16,384 | ALL (except FILE_UPLOAD) | $0.003/1K | $0.015/1K |
| `claude-opus-4-20250514` | 200,000 | 32,000 | ALL (except FILE_UPLOAD) | $0.015/1K | $0.075/1K |
| `claude-3-5-sonnet-20241022` | 200,000 | 8,192 | ALL (except FILE_UPLOAD) | $0.003/1K | $0.015/1K |

**Vision support:**

Claude handles images via URL or base64-encoded content blocks. The provider automatically detects image format from the file extension (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`).

**Default model:** `claude-sonnet-4-20250514`

---

### 2.4 Ollama (Local)

**Source:** `providers/ollama.py` | **Class:** `OllamaProvider`

Ollama runs models locally — no API key required, no data leaves your machine, and inference is completely free. Communication uses the Ollama HTTP REST API with no SDK dependency.

**Setup:**

```bash
# Install Ollama from https://ollama.ai
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a model
ollama pull deepseek-coder-v2

# Start the server (if not running as a service)
ollama serve
```

**Connectivity check:** The provider verifies Ollama is reachable via an HTTP GET to `http://localhost:11434/api/tags` with a 3-second timeout. If unreachable at instantiation, a warning is logged but the provider is still created (requests will fail until Ollama starts).

**Models:**

| Model | Context | Max Output | Capabilities | Cost |
|-------|---------|-----------|--------------|------|
| `deepseek-coder-v2` | 128,000 | 8,192 | TEXT, CODE | Free |
| `llama3.1` | 128,000 | 8,192 | TEXT, CODE | Free |
| `codellama` | 16,000 | 4,096 | TEXT, CODE | Free |
| `mistral` | 32,000 | 4,096 | TEXT, CODE | Free |

> **Note:** Ollama models only advertise `TEXT_GENERATION` and `CODE_GENERATION` capabilities. They do not support vision, structured output, file upload, or streaming through the Quant2Repo provider interface.

**Custom host:**

```bash
# Use a remote Ollama instance
export OLLAMA_HOST="http://gpu-server:11434"
```

**Default model:** `deepseek-coder-v2`

---

## 3. Provider Selection Logic

The `ProviderRegistry` and `get_provider()` function (both in `providers/registry.py`) handle automatic detection, capability-based routing, and explicit overrides.

### Auto-Detection

`ProviderRegistry.detect_available()` checks which providers have valid credentials or connectivity:

| Provider | Detection Method |
|----------|-----------------|
| **Gemini** | Checks if `GEMINI_API_KEY` environment variable is set |
| **OpenAI** | Checks if `OPENAI_API_KEY` environment variable is set |
| **Anthropic** | Checks if `ANTHROPIC_API_KEY` environment variable is set |
| **Ollama** | HTTP GET to `http://localhost:11434/api/tags` with 2s timeout |

**Caching:** Detection results are cached for **30 seconds** (`_CACHE_TTL = 30`) to avoid repeated network checks. The cache is a module-level dict (`_AVAILABLE_CACHE`) keyed by monotonic timestamp.

```python
_AVAILABLE_CACHE: dict = {"timestamp": 0.0, "providers": None}
_CACHE_TTL = 30  # seconds
```

---

### Default Preference Order

When no provider is specified (i.e. `default_provider = "auto"`), `get_provider()` tries providers in this order and selects the first one that is available:

```
openai -> anthropic -> gemini -> ollama
```

```python
# From providers/registry.py — get_provider() auto-detect path
available = ProviderRegistry.detect_available()
default_order = ["openai", "anthropic", "gemini", "ollama"]
for name in default_order:
    if name in available:
        logger.info("Auto-selected provider: %s", name)
        return ProviderRegistry.create(name, api_key=api_key, model_name=model_name)
```

If no provider is available, a `RuntimeError` is raised:

```
RuntimeError: No LLM provider available. Set one of OPENAI_API_KEY,
ANTHROPIC_API_KEY, or GEMINI_API_KEY, or start Ollama locally.
```

---

### Capability-Based Routing

`ProviderRegistry.best_for(capability)` returns the best *available* provider for a given capability, using hand-tuned preference orders:

| Capability | Preference Order |
|------------|-----------------|
| `LONG_CONTEXT` | gemini, anthropic, openai, ollama |
| `VISION` | gemini, openai, anthropic, ollama |
| `CODE_GENERATION` | anthropic, openai, gemini, ollama |
| `STRUCTURED_OUTPUT` | openai, gemini, anthropic, ollama |
| `TEXT_GENERATION` | openai, anthropic, gemini, ollama |
| `FILE_UPLOAD` | gemini |
| `STREAMING` | openai, anthropic, gemini, ollama |

Only providers that are currently detected as available are considered. If no available provider supports the requested capability, a `RuntimeError` is raised.

---

### Explicit Override

You can bypass auto-detection entirely by specifying the provider and model explicitly.

**CLI:**

```bash
# Use Gemini with a specific model
python main.py --provider gemini --model gemini-2.5-pro \
  --pdf_url "https://arxiv.org/pdf/YOUR_PAPER.pdf"

# Use OpenAI
python main.py --provider openai --model gpt-4o \
  --pdf_url "https://arxiv.org/pdf/YOUR_PAPER.pdf"

# Use local Ollama
python main.py --provider ollama --model deepseek-coder-v2 \
  --pdf_url "https://arxiv.org/pdf/YOUR_PAPER.pdf"
```

---

### Programmatic Selection

```python
from providers.registry import get_provider, ProviderRegistry
from providers.base import ModelCapability

# Auto-detect best available provider
provider = get_provider()

# Explicit provider
provider = get_provider("gemini", model_name="gemini-2.5-pro")

# Explicit provider with API key
provider = get_provider("openai", api_key="sk-...", model_name="gpt-4o")

# Capability-based selection
provider = get_provider(required_capability=ModelCapability.LONG_CONTEXT)

# Direct registry methods
best = ProviderRegistry.best_for(ModelCapability.VISION)  # returns provider name
provider = ProviderRegistry.create(best)                   # instantiates it

# List all registered providers
names = ProviderRegistry.list_providers()  # ["gemini", "openai", "anthropic", "ollama"]

# Check which are available right now
available = ProviderRegistry.detect_available()  # e.g. ["openai", "gemini"]
```

**Resolution order in `get_provider()`:**

1. If `provider_name` is given explicitly, use it directly
2. If `required_capability` is given, pick the best available provider for that capability
3. Otherwise, pick the first available provider from the default preference list

---

## 4. Cost Estimation

### Using the Cost Estimator

The `ProviderRegistry.estimate_cost()` method provides quick cost lookups without instantiating a provider. It uses each provider class's `_MODELS` list for O(1) model lookup.

```python
from providers.registry import ProviderRegistry

# Estimate cost for a typical paper processing run
cost = ProviderRegistry.estimate_cost(
    provider_name="gemini",
    model_name="gemini-2.5-pro",
    input_tokens=50_000,
    output_tokens=10_000,
)
print(f"Estimated cost: ${cost:.4f}")  # $0.1625
```

### Cost Formula

```
cost = (input_tokens / 1000 * cost_per_1k_input) + (output_tokens / 1000 * cost_per_1k_output)
```

The result is rounded to 6 decimal places. Returns `0.0` for local providers (Ollama) or unknown models.

### Worked Example

For `gemini-2.5-pro` with 50,000 input tokens and 10,000 output tokens:

```
input_cost  = 50,000 / 1,000 * $0.00125 = $0.0625
output_cost = 10,000 / 1,000 * $0.01    = $0.1000
total_cost  = $0.0625 + $0.1000          = $0.1625
```

### Typical Pipeline Costs

A single paper processing run involves multiple LLM calls across several pipeline stages. These estimates assume a ~20-page paper with typical complexity:

| Provider | Model | Estimated Cost (single paper) |
|----------|-------|------------------------------|
| Gemini | `gemini-2.5-pro` | $0.15 - $0.50 |
| Gemini | `gemini-2.0-flash` | $0.01 - $0.05 |
| OpenAI | `gpt-4o` | $0.50 - $2.00 |
| OpenAI | `o3` | $1.00 - $4.00 |
| Anthropic | `claude-sonnet-4-20250514` | $0.30 - $1.50 |
| Anthropic | `claude-opus-4-20250514` | $1.50 - $6.00 |
| Ollama | `deepseek-coder-v2` | Free |
| Ollama | `llama3.1` | Free |

### Cost-Saving Tips

- **Use `gemini-2.0-flash` for prototyping** — 25x cheaper input and 25x cheaper output than `gemini-2.5-pro`, suitable for iterating on prompts and pipeline logic
- **Use Ollama for local development** — completely free, no API calls, no data leaves your machine
- **Agent mode costs 3-5x more than classic** — the decomposed planning, self-refine, and execution stages generate significantly more LLM calls
- **CodeRAG adds additional API calls** — each reference repository lookup and code snippet analysis requires separate generation requests
- **Cache aggressively** — enable `enable_caching=True` (the default) to avoid re-processing unchanged inputs; cached results are stored in `cache_dir`
- **Monitor token usage** — check `GenerationResult.input_tokens` and `output_tokens` to identify unexpectedly expensive stages

---

## 5. Configuration System

All pipeline behaviour is controlled by the `Q2RConfig` dataclass defined in `config.py`. Configuration values can be set via environment variables, CLI arguments, or programmatically.

### Q2RConfig Dataclass

```python
@dataclass
class Q2RConfig:
    """Central configuration for the Quant2Repo pipeline."""

    # ── Provider defaults ─────────────────────────────────────────────
    default_provider: str = "auto"         # Provider slug or "auto" for detection
    default_model: str = ""                # Model name override (empty = provider default)

    # ── Pipeline toggles ──────────────────────────────────────────────
    enable_validation: bool = True         # Run validation stage
    enable_test_generation: bool = True    # Generate test files
    enable_backtest_validation: bool = True # Validate backtest correctness
    enable_caching: bool = True            # Cache intermediate results
    max_fix_iterations: int = 2            # Max auto-debug retry cycles

    # ── Download settings ─────────────────────────────────────────────
    pdf_timeout: int = 120                 # PDF download timeout (seconds)
    pdf_max_size_mb: int = 100             # Maximum PDF size (MB)

    # ── Generation settings ───────────────────────────────────────────
    code_temperature: float = 0.15         # Temperature for code generation
    analysis_temperature: float = 0.1      # Temperature for analysis/extraction
    max_code_tokens: int = 16384           # Max tokens for code generation
    max_analysis_tokens: int = 8192        # Max tokens for analysis/extraction

    # ── Timeout settings (seconds) ────────────────────────────────────
    llm_generation_timeout: int = 600      # LLM API call timeout
    validation_timeout: int = 300          # Validation stage timeout
    execution_timeout: int = 900           # Code execution timeout

    # ── Vision settings ───────────────────────────────────────────────
    max_diagram_pages: int = 30            # Max pages to render as images
    diagram_dpi: int = 150                 # DPI for page rendering
    vision_batch_size: int = 4             # Images per vision API call

    # ── CodeRAG settings ──────────────────────────────────────────────
    enable_code_rag: bool = False          # Enable code retrieval augmentation
    code_rag_max_repos: int = 3            # Max reference repos to search
    code_rag_max_files: int = 20           # Max files to retrieve per repo

    # ── Document segmentation ─────────────────────────────────────────
    enable_segmentation: bool = True       # Segment long documents
    segmentation_max_chars: int = 12000    # Max chars per segment
    segmentation_overlap: int = 500        # Overlap between segments

    # ── Context management ────────────────────────────────────────────
    enable_context_manager: bool = True    # Enable rolling context manager
    context_max_chars: int = 80000         # Max context window chars
    context_use_llm_summaries: bool = True # Use LLM to summarize prior outputs

    # ── Backtest-specific settings ────────────────────────────────────
    default_start_date: str = "2000-01-01"
    default_end_date: str = "2023-12-31"
    default_initial_capital: float = 1_000_000.0
    default_transaction_cost_bps: float = 10.0
    default_data_source: str = "yfinance"
    backtest_metrics: list = field(default_factory=lambda: [
        "annual_return", "annual_volatility", "sharpe_ratio",
        "max_drawdown", "calmar_ratio", "sortino_ratio",
        "turnover", "hit_rate", "profit_factor",
        "var_95", "cvar_95", "information_ratio",
    ])

    # ── Cache settings ────────────────────────────────────────────────
    cache_dir: str = ".q2r_cache"          # Directory for cached results

    # ── Output settings ───────────────────────────────────────────────
    verbose: bool = False                  # Enable verbose logging
```

### Backtest Metrics

The `backtest_metrics` field defines which performance metrics are computed and validated during the backtest validation stage:

| Metric | Description |
|--------|-------------|
| `annual_return` | Annualised portfolio return |
| `annual_volatility` | Annualised return standard deviation |
| `sharpe_ratio` | Risk-adjusted return (excess return / volatility) |
| `max_drawdown` | Largest peak-to-trough decline |
| `calmar_ratio` | Annual return / max drawdown |
| `sortino_ratio` | Downside-risk-adjusted return |
| `turnover` | Portfolio turnover rate |
| `hit_rate` | Fraction of profitable trades |
| `profit_factor` | Gross profits / gross losses |
| `var_95` | Value at Risk at the 95th percentile |
| `cvar_95` | Conditional VaR (expected shortfall) at 95th percentile |
| `information_ratio` | Excess return relative to benchmark / tracking error |

---

### Adaptive Token Allocation

The `max_tokens_for_file()` method returns a file-type-specific token limit, ensuring that complex files (models, backtests) get more generation budget while simple files (configs, READMEs) use less.

```python
def max_tokens_for_file(self, file_path: str) -> int:
    """Return adaptive token limit based on file type."""
    if file_path.endswith((".yaml", ".yml", ".toml", ".cfg", ".txt")):
        return 2048
    if file_path.endswith(".md"):
        return 2048
    lower = file_path.lower()
    if "model" in lower or "network" in lower or "signal" in lower:
        return 12288
    if "backtest" in lower or "portfolio" in lower:
        return 10240
    if "test" in lower:
        return 6144
    if "config" in lower or "utils" in lower or "__init__" in lower:
        return 4096
    return 8192
```

| File Pattern | Token Limit | Rationale |
|-------------|-------------|-----------|
| `.yaml`, `.yml`, `.toml`, `.cfg`, `.txt` | 2,048 | Simple configuration / data files |
| `.md` | 2,048 | Documentation, READMEs |
| `model`, `network`, `signal` in path | 12,288 | Core strategy logic, complex implementations |
| `backtest`, `portfolio` in path | 10,240 | Backtesting engine, portfolio construction |
| `test` in path | 6,144 | Test suites with assertions |
| `config`, `utils`, `__init__` in path | 4,096 | Utility / configuration modules |
| Everything else | 8,192 | Default for general Python files |

---

### Environment Variable Mapping

`Q2RConfig.from_env()` reads configuration from environment variables, providing a way to configure the pipeline without code changes:

```python
@classmethod
def from_env(cls) -> "Q2RConfig":
    """Create config from environment variables."""
    config = cls()
    if os.environ.get("Q2R_PROVIDER"):
        config.default_provider = os.environ["Q2R_PROVIDER"]
    if os.environ.get("Q2R_MODEL"):
        config.default_model = os.environ["Q2R_MODEL"]
    if os.environ.get("Q2R_CACHE_DIR"):
        config.cache_dir = os.environ["Q2R_CACHE_DIR"]
    if os.environ.get("Q2R_VERBOSE"):
        config.verbose = os.environ["Q2R_VERBOSE"].lower() in ("1", "true", "yes")
    if os.environ.get("Q2R_DATA_SOURCE"):
        config.default_data_source = os.environ["Q2R_DATA_SOURCE"]
    return config
```

| Env Var | Config Field | Default | Notes |
|---------|-------------|---------|-------|
| `Q2R_PROVIDER` | `default_provider` | `"auto"` | Provider slug: `gemini`, `openai`, `anthropic`, `ollama` |
| `Q2R_MODEL` | `default_model` | `""` | Model name override (empty = use provider default) |
| `Q2R_CACHE_DIR` | `cache_dir` | `".q2r_cache"` | Path to cache directory |
| `Q2R_VERBOSE` | `verbose` | `False` | Accepts `"1"`, `"true"`, `"yes"` (case-insensitive) |
| `Q2R_DATA_SOURCE` | `default_data_source` | `"yfinance"` | Data source for backtest data retrieval |

**Example:**

```bash
export Q2R_PROVIDER="gemini"
export Q2R_MODEL="gemini-2.0-flash"
export Q2R_VERBOSE="true"
export Q2R_DATA_SOURCE="yfinance"

python main.py --pdf_url "https://arxiv.org/pdf/YOUR_PAPER.pdf"
```

---

### Configuration Precedence

Configuration values are resolved in the following order (highest priority first):

```
1. CLI arguments           (highest priority)
2. Environment variables
3. Q2RConfig defaults      (lowest priority)
```

**Example:** If `Q2RConfig.default_provider = "auto"` and `Q2R_PROVIDER=gemini` is set, but the user passes `--provider openai` on the CLI, OpenAI will be used.

---

## 6. Adding a Custom Provider

You can extend Quant2Repo with additional LLM backends by implementing the `BaseProvider` interface and registering with the `ProviderRegistry`.

### Step 1: Create the Provider Module

Create a new file `providers/my_provider.py`:

```python
"""Custom provider implementation.

Set the ``MY_API_KEY`` environment variable or pass *api_key* directly.
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

_MY_CAPABILITIES: frozenset[ModelCapability] = frozenset(
    {
        ModelCapability.TEXT_GENERATION,
        ModelCapability.CODE_GENERATION,
        ModelCapability.STRUCTURED_OUTPUT,
    }
)

_MODELS: list[ModelInfo] = [
    ModelInfo(
        name="my-model-large",
        provider="my_provider",
        max_context_tokens=128_000,
        max_output_tokens=8_192,
        capabilities=_MY_CAPABILITIES,
        cost_per_1k_input=0.005,
        cost_per_1k_output=0.015,
    ),
]


class MyProvider(BaseProvider):
    """Provider for MyLLM API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("MY_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "No API key provided. Set MY_API_KEY or pass api_key=."
            )
        self._model_name = model_name or "my-model-large"
        # Initialize your SDK client here

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
        # Call your API here
        response_text = self._call_api(prompt, system_prompt, cfg)
        return GenerationResult(
            text=response_text,
            model=self._model_name,
            input_tokens=0,    # populate from API response
            output_tokens=0,   # populate from API response
            finish_reason="stop",
        )

    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system_prompt: Optional[str] = None,
        config: Optional[GenerationConfig] = None,
    ) -> dict[str, Any]:
        system = (system_prompt or "") + (
            "\n\nRespond with valid JSON matching this schema:\n"
            + json.dumps(schema, indent=2)
        )
        result = self.generate(prompt, system_prompt=system.strip(), config=config)
        return json.loads(result.text)

    def _call_api(self, prompt, system_prompt, config):
        """Replace with actual API call."""
        raise NotImplementedError("Implement your API call here")
```

### Step 2: Register the Provider

Register your provider so the registry can discover and create it:

```python
from providers.registry import ProviderRegistry

ProviderRegistry.register(
    name="my_provider",
    module_path="providers.my_provider",
    class_name="MyProvider",
    env_key="MY_API_KEY",
)
```

### Step 3: Use It

```python
from providers.registry import get_provider

# Explicit selection
provider = get_provider("my_provider", model_name="my-model-large")

# It will also appear in auto-detection if MY_API_KEY is set
available = ProviderRegistry.detect_available()
```

### Registration Details

The `ProviderRegistry.register()` method accepts four arguments:

| Argument | Description | Example |
|----------|-------------|---------|
| `name` | Short identifier for the provider | `"my_provider"` |
| `module_path` | Dot-separated Python module path | `"providers.my_provider"` |
| `class_name` | Name of the `BaseProvider` subclass | `"MyProvider"` |
| `env_key` | Environment variable for authentication | `"MY_API_KEY"` |

Internally, the registry stores this as a tuple in `_PROVIDERS`:

```python
_PROVIDERS["my_provider"] = ("providers.my_provider", "MyProvider", "MY_API_KEY")
```

The provider module is imported lazily (only when `ProviderRegistry.create()` is called), so registration does not require the provider's SDK to be installed at import time.

---

## 7. Temperature and Token Tuning

Different pipeline stages have different requirements for creativity vs. precision. The pipeline uses stage-specific temperature and token limits to optimise output quality.

### Pipeline Stage Settings

| Stage | Temperature | Max Tokens | Rationale |
|-------|------------|------------|-----------|
| Strategy extraction | 0.1 | 8,192 | Precise factual extraction from paper |
| Planning (all stages) | 0.1 | 4,096 - 6,144 | Deterministic structure and file layout |
| Code generation | 0.15 | 16,384 | Slight creativity for implementation, mostly precise |
| Validation | 0.1 | 6,144 | Accurate issue detection, no hallucination |
| Config generation | 0.15 | 4,096 | Precise parameter extraction from paper |
| Self-refine verify | 0.1 | 4,096 | Accurate critique of generated code |
| Self-refine refine | 0.15 | 8,192 | Targeted improvements based on critique |
| Auto-debug | 0.15 | 16,384 | Precise error fixing with enough space for full files |

**Key observations:**

- **Analysis stages** (extraction, validation, verification) use `temperature=0.1` for maximum precision and reproducibility
- **Generation stages** (code, config, refinement) use `temperature=0.15` for a small amount of creativity while remaining deterministic
- **Code generation** gets the largest token budget (`16,384`) because generated files can be long
- **Planning stages** need less output (`4,096-6,144`) since they produce structured file specifications

These values correspond to the `Q2RConfig` fields:
- `analysis_temperature = 0.1` — used by extraction, validation, and verification stages
- `code_temperature = 0.15` — used by code generation, config generation, refinement, and auto-debug
- `max_analysis_tokens = 8192` — base token limit for analysis stages
- `max_code_tokens = 16384` — base token limit for code generation stages

---

### Signal Type Constants

The pipeline recognises ten signal types, defined as module-level constants in `config.py`:

| Constant | Value |
|----------|-------|
| `SIGNAL_MOMENTUM` | `momentum` |
| `SIGNAL_VALUE` | `value` |
| `SIGNAL_CARRY` | `carry` |
| `SIGNAL_MEAN_REVERSION` | `mean_reversion` |
| `SIGNAL_VOLATILITY` | `volatility` |
| `SIGNAL_QUALITY` | `quality` |
| `SIGNAL_SENTIMENT` | `sentiment` |
| `SIGNAL_SEASONAL` | `seasonal` |
| `SIGNAL_TREND` | `trend_following` |
| `SIGNAL_STATISTICAL_ARBITRAGE` | `statistical_arbitrage` |

All signal types are collected in the `SIGNAL_TYPES` list for iteration.

---

### Asset Class Constants

Seven asset classes are supported, also defined as module-level constants in `config.py`:

| Constant | Value |
|----------|-------|
| `ASSET_EQUITIES` | `equities` |
| `ASSET_BONDS` | `bonds` |
| `ASSET_COMMODITIES` | `commodities` |
| `ASSET_CURRENCIES` | `currencies` |
| `ASSET_CRYPTO` | `crypto` |
| `ASSET_REITS` | `reits` |
| `ASSET_MULTI` | `multi_asset` |

All asset classes are collected in the `ASSET_CLASSES` list for iteration.

---

### Rebalancing Frequency Constants

The pipeline recognises seven rebalancing frequencies:

| Constant | Value |
|----------|-------|
| `REBAL_DAILY` | `daily` |
| `REBAL_WEEKLY` | `weekly` |
| `REBAL_MONTHLY` | `monthly` |
| `REBAL_QUARTERLY` | `quarterly` |
| `REBAL_SEMI_ANNUAL` | `semi_annual` |
| `REBAL_ANNUAL` | `annual` |
| `REBAL_INTRADAY` | `intraday` |

---

## Quick Reference

### Provider Comparison Matrix

| Feature | Gemini | OpenAI | Anthropic | Ollama |
|---------|--------|--------|-----------|--------|
| **Default model** | `gemini-2.5-pro` | `gpt-4o` | `claude-sonnet-4-20250514` | `deepseek-coder-v2` |
| **Max context** | 2M tokens | 200K tokens | 200K tokens | 128K tokens |
| **Vision** | Yes | Yes | Yes | No |
| **File upload** | Yes | No | No | No |
| **Structured output** | Yes | Yes | Yes | No |
| **Streaming** | Yes | Yes | Yes | No |
| **Long context** | Yes | Yes (o3, o1) | Yes | No |
| **Cost range** | $0.0001-$0.01/1K | $0.0025-$0.06/1K | $0.003-$0.075/1K | Free |
| **API key env var** | `GEMINI_API_KEY` | `OPENAI_API_KEY` | `ANTHROPIC_API_KEY` | — |
| **SDK package** | `google-generativeai` | `openai` | `anthropic` | None (HTTP) |

### Common Configurations

**Budget-conscious development:**

```bash
export GEMINI_API_KEY="..."
export Q2R_MODEL="gemini-2.0-flash"
python main.py --provider gemini --mode classic --pdf_url "..."
```

**Maximum quality:**

```bash
export GEMINI_API_KEY="..."
python main.py --provider gemini --model gemini-2.5-pro \
  --mode agent --refine --execute --pdf_url "..."
```

**Fully local (air-gapped):**

```bash
ollama pull deepseek-coder-v2
python main.py --provider ollama --model deepseek-coder-v2 \
  --mode classic --pdf_url "..."
```

**Multi-provider (different keys for different capabilities):**

```bash
export GEMINI_API_KEY="..."    # Used for file upload + long context
export OPENAI_API_KEY="..."    # Available as fallback

# Auto-detection will prefer OpenAI (first in default order),
# but capability routing will pick Gemini for FILE_UPLOAD
python main.py --pdf_url "..."
```

---

*Source files: `providers/base.py`, `providers/gemini.py`, `providers/openai_provider.py`, `providers/anthropic_provider.py`, `providers/ollama.py`, `providers/registry.py`, `config.py`*
