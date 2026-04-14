# Deployment & DevOps

**Operations guide for running, containerising, and deploying Quant2Repo — from local development through gateway-managed cloud execution.**

Version 1.0 | Quant2Repo | Apache 2.0 License

---

## Table of Contents

1. [Local Development Setup](#1-local-development-setup)
2. [Docker Deployment](#2-docker-deployment)
3. [Generated Repository DevOps](#3-generated-repository-devops)
4. [Execution Sandbox Architecture](#4-execution-sandbox-architecture)
5. [Gateway-Managed Deployment](#5-gateway-managed-deployment)
6. [Caching Strategy](#6-caching-strategy)
7. [Monitoring and Observability](#7-monitoring-and-observability)

---

## 1. Local Development Setup

### Prerequisites

Before starting, ensure you have the following installed:

- **Python 3.10+** — required for all modern type-hint features used by Q2R
- **pip / virtualenv** — for isolated dependency management
- **At least one LLM provider API key** — Gemini, OpenAI, Anthropic, or local Ollama
- **Optional: Docker** — for sandboxed backtest execution and container builds
- **Optional: GROBID** — for enhanced academic PDF parsing (headers, references, equations)

### Setting Up Virtual Environment

Create and activate an isolated Python environment:

```bash
# Create the virtual environment
python -m venv .venv

# Activate — Linux / macOS
source .venv/bin/activate

# Activate — Windows
# .venv\Scripts\activate
```

> **Tip:** If you manage multiple Python versions, use `python3.10 -m venv .venv`
> to ensure the correct interpreter is used.

### Installing Dependencies

Install core dependencies, then optionally add provider SDKs:

```bash
# Core dependencies (requests, PyPDF2, pandas, numpy, etc.)
pip install -r requirements.txt

# Individual provider SDKs — install what you need
pip install google-generativeai>=0.5.0   # Gemini
pip install openai>=1.12.0               # OpenAI
pip install anthropic>=0.25.0            # Anthropic

# Or install everything at once via extras
pip install -e ".[all]"
```

The core `requirements.txt` includes:

```
requests>=2.31.0
PyPDF2>=3.0.0
Pillow>=10.2.0
pyyaml>=6.0
numpy>=1.24.0
pandas>=2.0.0
pytest>=8.0
pytest-cov>=4.0
ruff>=0.3.0
```

### Configuring Provider API Keys

Set environment variables for each provider you plan to use:

```bash
# ── Google Gemini (recommended — 2M token context, cost-effective) ──
export GEMINI_API_KEY="your_key_here"

# ── OpenAI ──
export OPENAI_API_KEY="your_key_here"

# ── Anthropic ──
export ANTHROPIC_API_KEY="your_key_here"

# ── Ollama (local, free — install from https://ollama.ai) ──
ollama pull deepseek-coder-v2
# No API key needed; Ollama runs on localhost:11434
```

Provider auto-detection order (when `--provider auto`):

```
1. Check GEMINI_API_KEY   → GeminiProvider
2. Check OPENAI_API_KEY   → OpenAIProvider
3. Check ANTHROPIC_API_KEY → AnthropicProvider
4. Check localhost:11434   → OllamaProvider
5. Raise error — no provider available
```

### Running Tests

```bash
# Run the full test suite
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=. --cov-report=term-missing

# Run a specific test module
pytest tests/test_providers.py -v

# Lint with ruff
ruff check .
```

### Verifying Setup

After installation, confirm everything works:

```bash
# List available providers (checks API keys and connectivity)
python main.py --list-providers

# List the built-in strategy catalog (47 strategies)
python main.py --list-catalog

# Search the catalog
python main.py --search-catalog "momentum"

# Quick smoke test — classic mode with a catalog strategy
python main.py --catalog time-series-momentum --mode classic
```

Expected output from `--list-providers`:

```
Available providers:
  ✓ GeminiProvider    (gemini-2.5-pro)       — API key set
  ✓ OpenAIProvider    (gpt-4o)               — API key set
  ✗ AnthropicProvider (claude-sonnet-4-...)   — no API key
  ✓ OllamaProvider   (deepseek-coder-v2)     — local server running
```

---

## 2. Docker Deployment

### Dockerfile for Quant2Repo

Build and run Quant2Repo itself as a container:

```dockerfile
FROM python:3.10-slim

LABEL maintainer="Vijayakumar Ramdoss"
LABEL description="Quant2Repo - Paper to Backtest Pipeline"

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install provider SDKs
RUN pip install --no-cache-dir \
    google-generativeai>=0.5.0 \
    openai>=1.12.0 \
    anthropic>=0.25.0

# Copy application
COPY . .

ENTRYPOINT ["python", "main.py"]
```

### Building and Running

```bash
# ── Build the image ──
docker build -t quant2repo .

# ── Run with Gemini — paper URL ──
docker run --rm \
  -e GEMINI_API_KEY="$GEMINI_API_KEY" \
  -v $(pwd)/output:/app/generated_repo \
  quant2repo \
  --pdf_url "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975" \
  --mode agent --refine

# ── Run from catalog ──
docker run --rm \
  -e GEMINI_API_KEY="$GEMINI_API_KEY" \
  -v $(pwd)/output:/app/generated_repo \
  quant2repo \
  --catalog time-series-momentum --mode agent

# ── Run with OpenAI + execution ──
docker run --rm \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -v $(pwd)/output:/app/generated_repo \
  -v /var/run/docker.sock:/var/run/docker.sock \
  quant2repo \
  --pdf_url "https://arxiv.org/pdf/2104.13868" \
  --mode agent --refine --execute \
  --provider openai --model gpt-4o

# ── Run with local PDF ──
docker run --rm \
  -e GEMINI_API_KEY="$GEMINI_API_KEY" \
  -v $(pwd)/output:/app/generated_repo \
  -v $(pwd)/papers:/app/papers \
  quant2repo \
  --pdf_path /app/papers/momentum.pdf --mode classic
```

> **Note:** When using `--execute`, the container needs access to the Docker
> socket (`-v /var/run/docker.sock:/var/run/docker.sock`) so the execution
> sandbox can build and run the generated backtest in a nested container.

### docker-compose.yml

For reproducible multi-service setups (e.g. Q2R + GROBID for enhanced parsing):

```yaml
version: '3.8'

services:
  quant2repo:
    build: .
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
    volumes:
      - ./output:/app/generated_repo
      - ./papers:/app/papers
    command: [
      "--pdf_url", "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975",
      "--mode", "agent",
      "--refine"
    ]
    depends_on:
      - grobid

  grobid:
    image: lfoppiano/grobid:0.7.3
    ports:
      - "8070:8070"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8070/api/isalive"]
      interval: 10s
      timeout: 5s
      retries: 5
```

Run with:

```bash
# Start GROBID first, then run Q2R
docker compose up grobid -d
docker compose run quant2repo

# Or run everything
docker compose up
```

### Environment File

Create a `.env` file for Docker Compose:

```bash
# .env — loaded automatically by docker compose
GEMINI_API_KEY=your_gemini_key
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key
```

---

## 3. Generated Repository DevOps

When Quant2Repo runs in agent mode, the `DevOpsGenerator` (`advanced/devops.py`) produces
a complete set of infrastructure files for the generated backtest repository. These files
make every generated repo immediately buildable, testable, and deployable.

### Generated Files Overview

```
generated_repo/
├── main.py                         ← backtest entry point
├── config.py                       ← strategy parameters
├── data_loader.py                  ← market data acquisition
├── strategy.py                     ← signal generation
├── portfolio.py                    ← portfolio construction
├── backtest_engine.py              ← backtesting framework
├── performance.py                  ← performance analytics
├── requirements.txt                ← Python dependencies
├── tests/
│   └── test_strategy.py            ← generated unit tests
├── Dockerfile                      ← container build
├── docker-compose.yml              ← multi-service compose
├── Makefile                        ← build/run/test targets
├── setup.py                        ← packaging
├── .github/
│   └── workflows/
│       └── ci.yml                  ← GitHub Actions CI
└── q2r_metadata.json               ← generation metadata
```

### Dockerfile (Generated Backtest)

Each generated repo includes a production-ready Dockerfile:

```dockerfile
# ── Backtest Dockerfile ──────────────────────────────────────────
FROM python:3.11-slim

# System deps for numpy/scipy wheel builds
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ gfortran libopenblas-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cache-friendly: copy requirements first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default command
CMD ["python", "main.py"]
```

### Makefile (Generated Backtest)

Standard targets for build, run, test, and clean:

```makefile
.PHONY: install run test lint clean docker-build docker-run

install:
	pip install -r requirements.txt

run:
	python main.py

test:
	pytest tests/ -v

lint:
	flake8 *.py --max-line-length=120

clean:
	rm -rf __pycache__ .pytest_cache *.pyc

docker-build:
	docker build -t backtest .

docker-run:
	docker run --rm backtest
```

### GitHub Actions CI (Generated Backtest)

Every generated repo includes a CI workflow:

```yaml
name: Backtest CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Lint
        run: |
          pip install flake8
          flake8 *.py --max-line-length=120 --count --show-source

      - name: Run tests
        run: pytest tests/ -v

      - name: Run backtest
        run: python main.py
```

### docker-compose.yml (Generated Backtest)

Generated repos include a Compose file with backtest and report services:

```yaml
version: '3.8'

services:
  backtest:
    build: .
    volumes:
      - ./output:/app/output
    command: ["python", "main.py"]

  report:
    build: .
    volumes:
      - ./output:/app/output
    command: ["python", "performance.py"]
    depends_on:
      - backtest
```

---

## 4. Execution Sandbox Architecture

The execution sandbox (`advanced/executor.py`) provides isolated execution of
generated backtests with automatic error classification and timeout handling.

### Docker Mode (Preferred)

When Docker is available, the sandbox builds and runs the generated code inside
a container for full process isolation:

```
main.py --execute
  │
  ▼
ExecutionSandbox.execute(output_dir)
  │
  ├── Check Docker availability (docker info)
  │
  ├── Build image from output_dir/Dockerfile
  │     docker build -t q2r-backtest-{hash} output_dir/
  │
  ├── Run container with timeout (execution_timeout=900s)
  │     docker run --rm --network=host
  │       --memory=4g --cpus=2
  │       q2r-backtest-{hash}
  │
  ├── Capture stdout / stderr
  │
  ├── Classify error type (if exit_code != 0)
  │
  ▼
ExecutionResult(
    success=True/False,
    stdout="...",
    stderr="...",
    exit_code=0,
    duration_seconds=42.3,
    error_type="",
    modified_files=[...]
)
```

### Local Mode (Fallback)

When Docker is unavailable, execution falls back to a local subprocess:

```
ExecutionSandbox.execute(output_dir)
  │
  ├── subprocess.run(
  │     ["python", "main.py"],
  │     cwd=output_dir,
  │     timeout=execution_timeout
  │   )
  │
  ├── Set PYTHONPATH to include output_dir
  │
  ├── Apply execution_timeout (default 900s)
  │
  ├── Capture stdout / stderr
  │
  ▼
ExecutionResult
```

### Sandbox Configuration

Relevant `Q2RConfig` fields:

| Field | Default | Description |
|-------|---------|-------------|
| `execution_timeout` | `900` | Max execution time in seconds |
| `llm_generation_timeout` | `600` | Max time for LLM calls during debug |
| `validation_timeout` | `300` | Max time for validation stage |

### Integration with AutoDebugger

When execution fails, the `AutoDebugger` (`advanced/debugger.py`) kicks in for
iterative fix-and-retry cycles:

```
Execution failed (exit_code != 0)
  │
  ▼
AutoDebugger.debug(output_dir, exec_result, files)
  │
  ├── Iteration 1
  │   ├── Analyse error (classify type, extract traceback)
  │   ├── Match error type → hint from _ERROR_HINTS
  │   ├── Generate fix via LLM (targeted to affected file)
  │   ├── Apply fix to source files on disk
  │   ├── Re-execute in sandbox
  │   └── Check: resolved?
  │         ├── Yes → return DebugReport(resolved=True)
  │         └── No  → continue
  │
  ├── Iteration 2
  │   └── (same cycle with updated context)
  │
  ├── Iteration 3 (max_debug_iterations default)
  │   └── (final attempt)
  │
  ▼
DebugReport(
    iteration=3,
    error_type="ImportError",
    fixes=[DebugFix(file_path="...", fix_description="...")],
    resolved=True/False
)
```

### Error Types and Fix Strategies

The AutoDebugger classifies 19+ error types and provides targeted hints to the
LLM for each:

| Error Type | Example | Fix Strategy |
|------------|---------|--------------|
| `ImportError` | Missing module `yfinance` | Add to `requirements.txt`, fix import path |
| `ModuleNotFoundError` | `No module named 'talib'` | Add package to `requirements.txt` |
| `SyntaxError` | Invalid Python syntax | Re-generate affected file section |
| `TypeError` | Wrong argument types/count | Fix function signatures, add type coercion |
| `KeyError` | Missing dict key or DataFrame column | Add default handling, verify column names |
| `IndexError` | List/array index out of range | Add bounds checking, validate array shapes |
| `FileNotFoundError` | Missing data file or path | Fix file paths, adjust working directory |
| `ValueError` | Invalid conversion or array shape | Add input validation, check data formats |
| `AttributeError` | Missing attribute or method | Fix class definitions, check API version |
| `NameError` | Undefined variable or function | Add missing imports or definitions |
| `ZeroDivisionError` | Division by zero in metrics | Add zero-check guards before division |
| `OverflowError` | Numeric overflow in calculations | Add value clamping, use `np.clip()` |
| `RuntimeError` | Generic runtime failure | Analyse traceback, apply targeted fix |
| `StopIteration` | Iterator exhausted prematurely | Add length checks, use `next(iter, default)` |
| `ConnectionError` | Network request failed | Add retry logic, check URL validity |
| `TimeoutError` | Execution exceeded time limit | Optimise computation, reduce data range |
| `PermissionError` | File system access denied | Fix file paths, check container permissions |
| `JSONDecodeError` | Malformed JSON in config | Fix JSON syntax, validate before parsing |
| `UnicodeDecodeError` | Encoding mismatch in data | Specify encoding, add error handling |

### Debug Iteration Example

A typical debug session for a generated momentum strategy:

```
[Execute] Running main.py in Docker sandbox...
[Execute] ✗ Failed (exit_code=1, 2.3s)
          Error: ModuleNotFoundError: No module named 'statsmodels'

[Debug] Iteration 1/3
  → Error type: ModuleNotFoundError
  → Hint: A required package is missing. Add it to requirements.txt
  → Fix: Added 'statsmodels>=0.14' to requirements.txt
  → Re-executing...

[Execute] Running main.py in Docker sandbox...
[Execute] ✗ Failed (exit_code=1, 15.7s)
          Error: KeyError: 'Adj Close'

[Debug] Iteration 2/3
  → Error type: KeyError
  → Hint: A DataFrame is missing an expected column. Verify column names.
  → Fix: Changed 'Adj Close' to 'Close' in data_loader.py (yfinance v0.2+ schema)
  → Re-executing...

[Execute] Running main.py in Docker sandbox...
[Execute] ✓ Success (exit_code=0, 48.2s)

[Debug] Resolved after 2 iterations
```

---

## 5. Gateway-Managed Deployment

When deployed behind [Any2Repo-Gateway](https://github.com/nellaivijay/Any2Repo-Gateway),
Quant2Repo runs as a managed engine container. The `gateway_adapter.py` module
automatically detects gateway mode and adapts the pipeline accordingly.

### How It Works

```
Any2Repo-Gateway (orchestrator)
  │
  ├── Receives POST /jobs with engine_id="quant2repo"
  │     {
  │       "pdf_url": "https://...",
  │       "options": {"mode": "agent", "refine": true}
  │     }
  │
  ├── Launches container with env vars:
  │     JOB_ID=abc-123
  │     TENANT_ID=tenant-456
  │     PDF_URL=https://papers.ssrn.com/...
  │     OUTPUT_DIR=/output/abc-123
  │     ENGINE_OPTIONS={"mode":"agent","refine":true}
  │     CALLBACK_URL=https://gateway.example.com/callback
  │
  ▼
quant2repo container starts
  │
  ├── gateway_adapter.py detects JOB_ID env var
  │     is_gateway_mode() → True
  │
  ├── Runs pipeline in gateway mode:
  │   │
  │   ├── 1. Read parameters from environment variables
  │   ├── 2. Resolve catalog entries (if CATALOG_ID set)
  │   ├── 3. Run pipeline (classic or agent mode)
  │   ├── 4. Write .any2repo_status.json to OUTPUT_DIR
  │   ├── 5. POST results to CALLBACK_URL (optional)
  │   └── 6. Exit with code 0 (success) or 1 (failure)
  │
  ▼
Output in OUTPUT_DIR:
  /output/abc-123/
    ├── main.py
    ├── config.py
    ├── strategy.py
    ├── ...
    ├── q2r_metadata.json
    └── .any2repo_status.json
```

### Gateway Environment Variables

The gateway injects these environment variables into the engine container:

| Variable | Required | Description |
|----------|----------|-------------|
| `JOB_ID` | **Yes** | Unique job identifier — triggers gateway mode |
| `TENANT_ID` | No | Tenant/user who submitted the job |
| `PDF_URL` | One of these | URL of the research paper (SSRN, arXiv, direct PDF) |
| `PDF_BASE64` | ↑ | Base64-encoded PDF content |
| `PAPER_TEXT` | ↑ | Raw extracted paper text |
| `CATALOG_ID` | or this | Strategy ID from the built-in catalog |
| `OUTPUT_DIR` | No | Output directory (default: `/tmp/q2r-{JOB_ID}`) |
| `ENGINE_OPTIONS` | No | JSON string of pipeline options (see below) |
| `CALLBACK_URL` | No | URL to POST results on completion |
| `Q2R_PROVIDER` | No | Override LLM provider (`gemini`, `openai`, `anthropic`, `ollama`) |
| `Q2R_MODEL` | No | Override specific model name |

### ENGINE_OPTIONS Schema

The `ENGINE_OPTIONS` JSON string supports all pipeline configuration:

```json
{
  "mode": "agent",
  "refine": true,
  "execute": false,
  "skip_validation": false,
  "skip_tests": false,
  "max_fix_iterations": 2,
  "provider": "gemini",
  "model": "gemini-2.5-pro"
}
```

### Status File Format

On completion, `gateway_adapter.py` writes `.any2repo_status.json`:

```json
{
  "job_id": "abc-123",
  "status": "completed",
  "engine_id": "quant2repo",
  "output_url": "",
  "error": "",
  "files_generated": 12,
  "elapsed_seconds": 145.32,
  "completed_at": "2024-06-15T10:23:45.123456+00:00",
  "metadata": {
    "strategy_name": "Time-Series Momentum",
    "mode": "agent",
    "provider": "gemini",
    "model": "gemini-2.5-pro"
  }
}
```

On failure, `status` is `"failed"` and the `error` field contains the error message.

### Supported Backends

The gateway can launch Q2R containers on multiple cloud and on-premise backends:

| Backend | Service | How It Works |
|---------|---------|--------------|
| **GCP Vertex AI** | Google Cloud | Container runs as a Vertex AI Custom Job with GPU/CPU selection |
| **AWS Bedrock** | Amazon Web Services | Container runs on ECS/Fargate with task definitions |
| **Azure ML** | Microsoft Azure | Container runs on AzureML Compute with managed endpoints |
| **On-Premise** | Docker / Kubernetes | Container runs on local Docker daemon or K8s cluster |

### Engine Manifest

Register Quant2Repo with the gateway using the engine manifest
(`examples/quant2repo-manifest.json`):

```json
{
  "engine_id": "quant2repo",
  "version": "2.0.0",
  "display_name": "Quant2Repo",
  "description": "Convert quant finance papers into backtesting repos",
  "protocol_version": "1.0",
  "image": "ghcr.io/nellaivijay/quant2repo:latest",
  "supported_inputs": [
    "pdf_url",
    "pdf_base64",
    "paper_text",
    "catalog_id"
  ],
  "options_schema": {
    "mode": {
      "type": "string",
      "enum": ["classic", "agent"],
      "default": "classic",
      "description": "Pipeline mode"
    },
    "refine": {
      "type": "boolean",
      "default": false,
      "description": "Enable self-refinement pass"
    },
    "execute": {
      "type": "boolean",
      "default": false,
      "description": "Execute generated code in sandbox"
    },
    "max_fix_iterations": {
      "type": "integer",
      "default": 2,
      "description": "Max auto-debug iterations"
    }
  },
  "resource_requirements": {
    "min_memory_gb": 2,
    "min_cpu": 1,
    "gpu_required": false,
    "estimated_duration_minutes": 5
  }
}
```

> See the full [Gateway Integration](Gateway-Integration) documentation for
> protocol details, worked examples, and multi-engine orchestration.

---

## 6. Caching Strategy

The `PipelineCache` (`advanced/cache.py`) implements content-addressed caching
for all pipeline stages, dramatically speeding up re-runs on the same paper.

### How Caching Works

```
Input PDF
  │
  ├── SHA-256 hash (first 16 hex chars) → pdf_hash
  │
  ▼
.q2r_cache/
  └── {pdf_hash}/
        ├── extraction.pkl      ← pickled strategy extraction
        ├── plan.pkl            ← pickled architecture plan
        ├── metadata.json       ← JSON metadata (provider, timestamps)
        └── files/              ← generated source tree snapshot
              ├── config.py
              ├── data_loader.py
              ├── strategy.py
              └── ...
```

### Cache Key Generation

Cache keys are content-addressed using SHA-256:

```python
# File-based key (for PDF inputs)
PipelineCache.hash_file("paper.pdf")   # → "a3f7b2c1e9d04f8a"

# Text-based key (for extracted text, prompts)
PipelineCache.hash_text(paper_text)     # → "7c2e1a9b3f0d5e8c"
```

### Cache Behaviour by Stage

| Stage | Cached Artifact | Cache Hit Action |
|-------|----------------|-----------------|
| PDF Parsing | Raw extracted text | Skip re-parsing |
| Strategy Extraction | Structured extraction dict | Skip LLM call |
| Architecture Planning | Plan object | Skip LLM call |
| Code Generation | Generated source files | Skip LLM call per file |
| Validation | Validation results | Skip re-validation |

### Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `enable_caching` | `True` | Master toggle for pipeline caching |
| `cache_dir` | `".q2r_cache"` | Root directory for cache data |

Override via environment or `Q2RConfig`:

```bash
# Disable caching
python main.py --pdf_url "..." --no-cache

# Custom cache directory
export Q2R_CACHE_DIR="/tmp/q2r-cache"
```

### Cache Management

```bash
# View cache contents
ls -la .q2r_cache/

# Check cache size
du -sh .q2r_cache/

# Clear cache for a specific paper
rm -rf .q2r_cache/a3f7b2c1e9d04f8a/

# Clear entire cache
rm -rf .q2r_cache/
```

### When Caching Helps Most

- **Iterating on a paper:** Re-running with different modes (`classic` → `agent`) on
  the same paper reuses the extraction and planning stages.
- **Debugging generated code:** Re-runs after manual edits skip all LLM stages.
- **Provider comparison:** Switching providers still benefits from cached PDF parsing.
- **CI/CD pipelines:** Pre-warm cache in CI for faster test runs.

---

## 7. Monitoring and Observability

### Logging

Quant2Repo uses Python's standard `logging` module with per-module loggers for
fine-grained control:

```
Log format: "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
Date format: "%H:%M:%S"
```

Example output:

```
10:23:45 [quant2repo] INFO: Using provider: GeminiProvider (gemini-2.5-pro)
10:23:46 [core.paper_parser] INFO: Parsing paper from URL...
10:23:52 [core.strategy_extractor] INFO: Extracting strategy...
10:24:15 [core.planner] INFO: Planning architecture (7 files)...
10:24:38 [core.coder] INFO: Generating config.py (1/7)...
10:25:02 [advanced.backtest_validator] INFO: Running bias checks...
10:25:10 [advanced.executor] INFO: Executing in Docker sandbox...
10:25:58 [quant2repo] INFO: Done — 12 files generated in 133.2s
```

#### Enabling Verbose / Debug Logging

```bash
# Enable DEBUG level output for all loggers
python main.py --pdf_url "..." --verbose
```

#### Key Logger Names

| Logger | Module | What It Logs |
|--------|--------|-------------|
| `quant2repo` | `main.py` | Top-level pipeline flow |
| `quant2repo.gateway` | `gateway_adapter.py` | Gateway mode detection, status writes |
| `core.paper_parser` | `core/paper_parser.py` | PDF download, text extraction |
| `core.strategy_extractor` | `core/strategy_extractor.py` | Strategy extraction prompts/results |
| `core.planner` | `core/planner.py` | Architecture planning |
| `core.coder` | `core/coder.py` | File-by-file code generation |
| `core.validator` | `core/validator.py` | Code validation and fixes |
| `agents.orchestrator` | `agents/orchestrator.py` | Agent mode pipeline coordination |
| `advanced.executor` | `advanced/executor.py` | Sandbox execution, Docker builds |
| `advanced.debugger` | `advanced/debugger.py` | Auto-debug iterations, fix application |
| `advanced.backtest_validator` | `advanced/backtest_validator.py` | Bias checks, metric validation |
| `advanced.cache` | `advanced/cache.py` | Cache hits/misses |
| `advanced.devops` | `advanced/devops.py` | DevOps file generation |
| `providers.*` | `providers/*.py` | LLM API calls, token usage, retries |

### Metadata Output

Every pipeline run produces `q2r_metadata.json` in the output directory:

```json
{
  "start_time": "2024-06-15T10:23:45",
  "elapsed_seconds": 133.2,
  "strategy_name": "Time-Series Momentum",
  "paper_title": "Time Series Momentum",
  "paper_source": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975",
  "files_generated": 12,
  "mode": "agent",
  "config": {
    "provider": "gemini",
    "model": "gemini-2.5-pro",
    "enable_validation": true,
    "enable_test_generation": true,
    "enable_backtest_validation": true,
    "max_fix_iterations": 2,
    "code_temperature": 0.15,
    "execution_timeout": 900
  },
  "catalog": {
    "id": "time-series-momentum",
    "asset_class": "Equities",
    "paper_url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975"
  },
  "pipeline_stages": {
    "paper_parsing": {"elapsed_seconds": 6.1, "status": "success"},
    "strategy_extraction": {"elapsed_seconds": 22.4, "status": "success"},
    "architecture_planning": {"elapsed_seconds": 18.7, "status": "success"},
    "code_generation": {"elapsed_seconds": 64.2, "status": "success", "files": 7},
    "validation": {"elapsed_seconds": 12.3, "status": "success", "issues": 0},
    "test_generation": {"elapsed_seconds": 8.5, "status": "success"},
    "execution": {"elapsed_seconds": 48.2, "status": "success", "debug_iterations": 2}
  },
  "provider_stats": {
    "total_tokens": 142350,
    "prompt_tokens": 98200,
    "completion_tokens": 44150,
    "api_calls": 14,
    "estimated_cost_usd": 0.043
  }
}
```

### Health Checks

For long-running or gateway deployments, verify system health:

```bash
# Check provider connectivity
python main.py --list-providers

# Check catalog integrity
python main.py --list-catalog | wc -l

# Check Docker availability (for execution sandbox)
docker info > /dev/null 2>&1 && echo "Docker: OK" || echo "Docker: unavailable"

# Check GROBID (if using enhanced parsing)
curl -s http://localhost:8070/api/isalive && echo "GROBID: OK"
```

### Troubleshooting Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `No provider available` | No API keys set | Export at least one `*_API_KEY` env var |
| `PDF download timeout` | Network issue or SSRN rate limit | Retry, use `--pdf_path` with local file |
| `Token limit exceeded` | Paper too long for provider context | Use Gemini (2M tokens) or enable segmentation |
| `Docker build failed` | Missing system deps in Dockerfile | Check generated `requirements.txt` |
| `Execution timeout` | Backtest runs too long | Reduce date range, increase `execution_timeout` |
| `Cache permission error` | Read-only filesystem | Set `Q2R_CACHE_DIR` to writable path |
| `Gateway status: failed` | Pipeline error in gateway mode | Check `.any2repo_status.json` error field |
| `OOM in container` | Large dataset in memory | Increase Docker memory limit (`--memory=8g`) |

---

*See also: [Architecture Overview](Architecture-Overview) · [Usage Guide](Usage-Guide) · [Gateway Integration](Gateway-Integration) · [Pipeline Stages Deep Dive](Pipeline-Stages-Deep-Dive)*
