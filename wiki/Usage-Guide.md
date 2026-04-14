# Usage Guide

Comprehensive guide to installing, configuring, and running Quant2Repo — the multi-model agentic framework that converts quantitative finance research papers into production-ready backtesting repositories.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Installation](#2-installation)
3. [Quick Start](#3-quick-start)
4. [CLI Reference](#4-cli-reference)
5. [Usage Examples](#5-usage-examples)
6. [Understanding Output](#6-understanding-output)
7. [Environment Variables](#7-environment-variables)
8. [Programmatic Usage](#8-programmatic-usage)
9. [Choosing Between Classic and Agent Modes](#9-choosing-between-classic-and-agent-modes)

---

## 1. Prerequisites

### Required

| Requirement | Minimum Version | Notes |
|-------------|----------------|-------|
| **Python** | 3.10+ | 3.11 and 3.12 also supported |
| **pip** | 21.0+ | For dependency installation |
| **LLM Provider** | — | At least one: Gemini API key, OpenAI API key, Anthropic API key, or a running Ollama instance |

> **Note:** Quant2Repo uses long-context LLMs to process full research papers (often 30–60 pages). Providers with larger context windows (Gemini at 2M tokens, Anthropic at 200K) will produce better results on longer papers.

### Optional Dependencies

These are not required for basic operation but unlock enhanced capabilities:

| Dependency | Package | Purpose |
|------------|---------|---------|
| **PyMuPDF** | `fitz` / `PyMuPDF` | Rich PDF parsing with font size, weight, and structural awareness. Extracts headings, tables, and figure captions with higher fidelity than plain-text extraction. |
| **GROBID** | Docker service | High-quality TEI XML paper parsing. Produces structured sections, equations, and reference lists from academic PDFs. Best results for well-formatted papers. |
| **Docker** | `docker` | Isolated execution sandbox for running generated backtests safely. Required for `--execute` in agent mode. |
| **lxml** | `lxml` | TEI XML parsing for GROBID output. Only needed when GROBID is used as the parsing backend. |
| **Pillow** | `PIL` / `Pillow` | Vision-based page analysis. Enables diagram extraction and visual layout understanding when the provider supports vision (Gemini, GPT-4o, Claude). |

### System Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| **RAM** | 4 GB | 8 GB+ (for local Ollama models) |
| **Disk** | 500 MB | 2 GB+ (with Ollama models cached) |
| **Network** | Required | For API providers and paper downloads |
| **OS** | Linux, macOS, Windows (WSL) | Linux or macOS for Docker sandbox |

---

## 2. Installation

### Clone and Install

```bash
# Clone the repository
git clone https://github.com/nellaivijay/Quant2Repo.git
cd Quant2Repo

# Install core dependencies
pip install -r requirements.txt
```

### Provider Setup

You need at least **one** LLM provider configured. Set up whichever provider(s) you plan to use:

#### Google Gemini (Recommended)

Gemini offers a 2M-token context window, native vision support, and file upload — making it the best default for processing long research papers.

```bash
# Get your API key from https://aistudio.google.com/apikey
export GEMINI_API_KEY="your_gemini_api_key_here"
```

```bash
# Install the Gemini SDK (included in requirements.txt)
pip install google-generativeai
```

#### OpenAI

```bash
# Get your API key from https://platform.openai.com/api-keys
export OPENAI_API_KEY="your_openai_api_key_here"
```

```bash
# Install the OpenAI SDK
pip install openai
```

#### Anthropic (Claude)

```bash
# Get your API key from https://console.anthropic.com/
export ANTHROPIC_API_KEY="your_anthropic_api_key_here"
```

```bash
# Install the Anthropic SDK
pip install anthropic
```

#### Ollama (Local / Free)

```bash
# Install Ollama from https://ollama.ai
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.ai/install.sh | sh
```

```bash
# Start the Ollama server
ollama serve
```

```bash
# Pull a recommended model for code generation
ollama pull deepseek-coder-v2

# Or pull a larger general-purpose model
ollama pull llama3.1:70b
```

> **Tip:** Ollama models run entirely on your machine — no API key needed, no usage costs. However, code quality depends heavily on model size. For best results with Ollama, use at least a 13B-parameter model.

### Install All Optional Dependencies

```bash
# Install with all optional extras (PyMuPDF, lxml, Pillow, etc.)
pip install -e ".[all]"
```

### Verify Installation

```bash
# Check that your provider is detected
python main.py --list-providers

# Expected output (example with Gemini configured):
# Available LLM Providers:
# ======================================================================
#   [+] gemini          (available)
#       gemini-2.5-pro (default)
#         Context: 1,048,576 tokens | long_context, vision, code_generation
#   [-] openai          (not configured)
#   [-] anthropic       (not configured)
#   [-] ollama          (not configured)
#
# Configured: 1/4 providers
```

---

## 3. Quick Start

### Example 1: Generate from a Paper URL

```bash
# Convert an SSRN paper into a backtesting repository
python main.py --pdf_url "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975"
```

This downloads the paper, parses it, extracts the trading strategy, plans the code architecture, generates a full backtesting repository, and validates the output — all in a single command.

### Example 2: Generate from a Local PDF

```bash
# Use a paper you've already downloaded
python main.py --pdf_path ./papers/time_series_momentum.pdf
```

### Example 3: Generate from the Built-in Catalog

```bash
# Use one of the 47 pre-cataloged strategies
python main.py --catalog time-series-momentum
```

The catalog resolves the strategy to its source paper URL and feeds it into the pipeline automatically.

### What Happens Step by Step

When you run Quant2Repo in **agent mode** (`--mode agent`), the pipeline executes the following stages:

1. **Paper downloaded and parsed** — The PDF is fetched (if URL) and processed through a multi-backend parser. GROBID is tried first for structured TEI XML extraction; if unavailable, PyMuPDF provides font-aware parsing; PyPDF2 serves as the final fallback for plain text.

2. **Strategy extracted** — An LLM analyzes the full paper text to identify trading signals, portfolio construction rules, asset universe definitions, rebalancing frequencies, key equations, and reported performance metrics.

3. **4-stage decomposed planning** — The architecture is planned in four sequential passes:
   - **Overall plan** — High-level module decomposition and data flow
   - **Architecture plan** — File-by-file specifications with interfaces
   - **Signal logic plan** — Detailed signal computation logic and edge cases
   - **Configuration plan** — Hyperparameters, date ranges, data sources

4. **Per-file analysis with accumulated context** — Each file specification is analyzed in depth before code generation, building up a shared context of interfaces, data schemas, and dependencies.

5. **CodeRAG mines GitHub for reference backtests** (if `--code-rag`) — The system searches GitHub for existing implementations of similar strategies, extracts relevant patterns, and provides them as reference context during code generation.

6. **File-by-file code generation with dependency ordering and context management** — Files are generated in topological order (config → data → signals → portfolio → analysis → main). Each file receives the accumulated context from previously generated files via a sliding context window.

7. **Test suite auto-generated** — Unit tests are created for each module: signal computation tests, portfolio construction tests, data loading tests, and integration tests for the full pipeline.

8. **Code validated** — The generated code is checked against the paper methodology for signal fidelity (are all signals implemented?), look-ahead bias (does the code peek at future data?), and data handling correctness (proper NaN handling, timezone awareness).

9. **Backtest validated** — Finance-specific bias checks are run: survivorship bias, data snooping, rebalancing timing, transaction cost modeling, capacity constraints, and out-of-sample methodology.

10. **Execution in sandbox + auto-debug** (if `--execute`) — The generated code is run inside a Docker container (or local subprocess). If execution fails, the auto-debugger analyzes the error, patches the code, and retries up to `--max-debug-iterations` times.

11. **DevOps files generated** — Production scaffolding is added: `Dockerfile`, `Makefile`, CI/CD workflow (`.github/workflows/ci.yml`), and `setup.py` for packaging.

12. **Reference evaluation against paper results** (if `--evaluate`) — The generated backtest's outputs are compared against the paper's reported results (Sharpe ratio, annual return, drawdown). A 1–5 score is assigned based on methodology coverage and numerical agreement.

> **Classic mode** (`--mode classic`) runs a streamlined 6-stage subset: Parse → Extract → Plan → Generate → Validate → Save.

---

## 4. CLI Reference

```
python main.py [OPTIONS]
```

### Input Sources

These arguments are **mutually exclusive** — provide exactly one:

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--pdf_url` | `str` | — | URL of the research paper PDF. Supports SSRN, arXiv, NBER, and direct PDF links. SSRN abstract pages are auto-resolved to the PDF download URL. |
| `--pdf_path` | `str` | — | Path to a local PDF file on disk. |
| `--catalog` | `str` | — | Strategy ID from the built-in catalog (47 strategies). Use `--list-catalog` to see all available IDs. The catalog entry's paper URL is used automatically. |

### Mode Selection

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--mode` | `choice` | `classic` | Pipeline mode. `classic`: linear 6-stage pipeline, fast and simple. `agent`: enhanced 11-stage pipeline with decomposed planning, self-refine loops, execution sandbox, and bias validation. |

### Provider Selection

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--provider` | `str` | `auto` | LLM provider to use: `gemini`, `openai`, `anthropic`, or `ollama`. When set to `auto` (default), the system detects which providers have valid API keys and selects the best one based on capability preferences. |
| `--model` | `str` | provider default | Specific model name to use, e.g. `gemini-2.5-pro`, `gpt-4o`, `claude-sonnet-4-20250514`, `deepseek-coder-v2`. Overrides the provider's default model. |

### Output

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--output_dir` | `str` | `./generated_repo` | Output directory where the generated backtesting repository will be saved. Created automatically if it does not exist. |

### Classic Pipeline Options

These options apply to `--mode classic` (the default):

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--skip-validation` | flag | — | Skip the validation pass entirely. Useful for quick iteration when you plan to review the code manually. |
| `--skip-tests` | flag | — | Skip automatic test generation. Reduces LLM calls and generation time. |
| `--max-fix-iterations` | `int` | `2` | Maximum number of auto-fix attempts when validation fails. Each iteration re-validates and attempts to fix remaining issues. Set to `0` to disable auto-fix. |

### Agent Pipeline Options

These options apply only when `--mode agent` is set:

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--refine` | flag | — | Enable self-refine verify/refine loops at each pipeline stage. After each stage completes, a verification pass checks for issues and a refinement pass addresses them. Controlled by `--max-refine-iterations`. |
| `--execute` | flag | — | Enable execution sandbox. The generated code is run inside a Docker container (or local subprocess) after generation. Failures trigger auto-debug cycles controlled by `--max-debug-iterations`. |
| `--evaluate` | flag | — | Enable reference-based evaluation. Compares the generated backtest against the paper's reported results and assigns a 1–5 score with letter grade (A–F). |
| `--interactive` | flag | — | Pause after the planning stage for user review. Prints the proposed file structure and waits for confirmation before proceeding to code generation. Useful for reviewing/modifying the plan. |
| `--no-tests` | flag | — | Disable automatic test suite generation. Skips the test generation stage entirely. |
| `--no-devops` | flag | — | Disable DevOps file generation. Skips creation of `Dockerfile`, `Makefile`, CI workflows, and `setup.py`. |
| `--code-rag` | flag | — | Enable CodeRAG: mine GitHub for reference backtest implementations of similar strategies. Found code snippets are provided as additional context during code generation. |
| `--no-context-manager` | flag | — | Disable the clean-slate context management system. By default, each file generation call receives a curated context window of previously generated files. This flag makes each call independent. |
| `--reference-dir` | `str` | — | Path to a reference implementation directory for evaluation. When provided, the evaluator compares the generated code against this reference in addition to the paper text. |
| `--max-refine-iterations` | `int` | `2` | Maximum number of self-refine iterations per pipeline stage. Only effective when `--refine` is enabled. Higher values improve quality but increase LLM calls and cost. |
| `--max-debug-iterations` | `int` | `3` | Maximum number of auto-debug iterations when execution fails. Only effective when `--execute` is enabled. Each iteration analyzes the error, patches the code, and re-runs. |

### Catalog Commands

These are standalone utility commands that print information and exit:

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--list-catalog` | flag | — | List all 47 strategies in the built-in catalog, grouped by asset class, with Sharpe ratios, volatilities, and rebalancing frequencies. |
| `--search-catalog` | `str` | — | Search the strategy catalog by keyword. Matches against strategy ID, title, description, signal type, and asset class. Returns results ranked by relevance. |

### Miscellaneous

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--list-providers` | flag | — | Show all known LLM providers, their configuration status, available models, context windows, and capabilities. Useful for debugging provider setup. |
| `--verbose` / `-v` | flag | — | Enable verbose output. Sets logging level to `DEBUG` and prints detailed information about each pipeline stage, LLM calls, token counts, and timing. |

---

## 5. Usage Examples

### Basic Usage

```bash
# Generate from an SSRN paper (classic mode, auto-detected provider)
python main.py --pdf_url "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975"
```

```bash
# Generate from an arXiv paper
python main.py --pdf_url "https://arxiv.org/pdf/2104.13868.pdf"
```

```bash
# Generate from a local PDF file
python main.py --pdf_path ./papers/momentum_strategy.pdf --output_dir ./momentum_backtest
```

```bash
# Use a specific provider and model
python main.py --pdf_url "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2379636" \
  --provider openai --model gpt-4o
```

### Agent Mode

```bash
# Basic agent mode (decomposed planning + per-file analysis + bias validation)
python main.py --pdf_url "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975" \
  --mode agent
```

```bash
# Agent mode with self-refine loops for higher quality
python main.py --pdf_url "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975" \
  --mode agent --refine --max-refine-iterations 3
```

```bash
# Agent mode with execution sandbox and auto-debug
python main.py --pdf_url "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975" \
  --mode agent --execute --max-debug-iterations 5
```

```bash
# Full agent pipeline: refine + execute + evaluate + code-rag
python main.py --pdf_url "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975" \
  --mode agent \
  --refine \
  --execute \
  --evaluate \
  --code-rag \
  --output_dir ./production_backtest \
  --verbose
```

### Strategy Catalog

```bash
# List all 47 strategies grouped by asset class
python main.py --list-catalog

# Example output:
# Quant2Repo Strategy Catalog (47 strategies)
# ==========================================================================================
#
# --- EQUITIES ---
#   time-series-momentum                                   SR=+0.640  Vol=12.3%  monthly
#   cross-sectional-momentum                               SR=+0.450  Vol=15.1%  monthly
#   value-factor-hml                                       SR=+0.380  Vol=11.8%  monthly
#   ...
```

```bash
# Search strategies by keyword
python main.py --search-catalog "momentum"

# Example output:
# Search results for 'momentum' (5 matches):
# ------------------------------------------------------------------------------------------
#   time-series-momentum                                   SR=+0.640  [equities]
#     Time-series momentum strategy based on past 12-month returns
#     Paper: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975
#
#   cross-sectional-momentum                               SR=+0.450  [equities]
#     Cross-sectional momentum with industry-neutral portfolios
#     Paper: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=...
```

```bash
# Generate a backtest from a catalog strategy (classic mode)
python main.py --catalog time-series-momentum --output_dir ./tsm_backtest
```

```bash
# Catalog strategy with agent mode and full pipeline
python main.py --catalog time-series-momentum \
  --mode agent --refine --execute --evaluate
```

### Advanced Patterns

```bash
# Enable CodeRAG to mine GitHub for reference implementations
# The system searches for existing backtests of similar strategies
# and uses them as additional context during code generation
python main.py --pdf_url "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975" \
  --mode agent \
  --code-rag \
  --refine
```

```bash
# Interactive mode: pause after planning for review
# You can inspect the proposed file structure before generation begins
python main.py --pdf_url "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975" \
  --mode agent \
  --interactive \
  --refine

# The pipeline will print the plan and pause:
# Proposed files:
#   config.py          — Strategy hyperparameters and date ranges
#   data_loader.py     — Yahoo Finance data fetching with caching
#   signals.py         — Time-series momentum signal computation
#   portfolio.py       — Portfolio construction and rebalancing
#   analysis.py        — Performance metrics (Sharpe, drawdown, etc.)
#   visualization.py   — Equity curves and tear sheets
#   main.py            — Entry point and CLI
#
# Press Enter to continue or Ctrl+C to abort...
```

```bash
# Reference evaluation against a known-good implementation
# Compares generated code structure and logic against a reference directory
python main.py --pdf_url "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975" \
  --mode agent \
  --evaluate \
  --reference-dir ./reference_implementations/tsm/ \
  --output_dir ./tsm_evaluated
```

---

## 6. Understanding Output

### Generated Repository Structure

After a successful run, the output directory contains a complete, self-contained backtesting repository:

```
generated_repo/
├── config.py                  # Strategy hyperparameters, date ranges, data sources
├── data_loader.py             # Data fetching (yfinance, FRED) with caching
├── signals.py                 # Signal computation (momentum, value, etc.)
├── portfolio.py               # Portfolio construction, weighting, rebalancing
├── analysis.py                # Performance metrics: Sharpe, drawdown, turnover
├── visualization.py           # Equity curves, rolling metrics, tear sheets
├── main.py                    # Entry point — runs the full backtest
├── requirements.txt           # Python dependencies
├── README.md                  # Auto-generated documentation
├── tests/                     # Auto-generated test suite
│   ├── __init__.py
│   ├── test_signals.py        # Signal computation unit tests
│   ├── test_portfolio.py      # Portfolio construction tests
│   ├── test_data_loader.py    # Data loading and caching tests
│   └── test_integration.py    # End-to-end pipeline test
├── Dockerfile                 # Container for reproducible execution
├── Makefile                   # Common tasks: run, test, lint, clean
├── .github/
│   └── workflows/
│       └── ci.yml             # GitHub Actions CI pipeline
├── setup.py                   # Package installation script
└── q2r_metadata.json          # Quant2Repo generation metadata
```

> **Note:** The exact set of files depends on the strategy complexity and pipeline options. `tests/`, `Dockerfile`, `Makefile`, `.github/`, and `setup.py` are only generated in agent mode with the corresponding options enabled (they are on by default unless `--no-tests` or `--no-devops` is used).

### Metadata File: `q2r_metadata.json`

Every generated repository includes a `q2r_metadata.json` file with provenance and generation metadata:

```json
{
  "quant2repo_version": "1.0",
  "start_time": "2024-12-15T14:23:01Z",
  "end_time": "2024-12-15T14:26:45Z",
  "elapsed_seconds": 224.3,
  "strategy_name": "Time-Series Momentum",
  "paper_url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975",
  "provider": "gemini",
  "model": "gemini-2.5-pro",
  "mode": "agent",
  "files_generated": [
    "config.py",
    "data_loader.py",
    "signals.py",
    "portfolio.py",
    "analysis.py",
    "visualization.py",
    "main.py",
    "requirements.txt",
    "README.md",
    "tests/test_signals.py",
    "tests/test_portfolio.py",
    "tests/test_data_loader.py",
    "tests/test_integration.py",
    "Dockerfile",
    "Makefile",
    ".github/workflows/ci.yml",
    "setup.py"
  ],
  "config": {
    "enable_refine": true,
    "enable_execution": true,
    "enable_evaluation": false,
    "enable_code_rag": false,
    "max_refine_iterations": 2,
    "max_debug_iterations": 3
  },
  "catalog": {
    "id": "time-series-momentum",
    "asset_classes": ["equities"],
    "signal_type": "momentum",
    "sharpe_ratio": 0.64
  },
  "validation": {
    "score": 87,
    "signal_coverage": 0.95,
    "data_coverage": 1.0,
    "passed": true
  }
}
```

### Validation Report

The code validation stage produces a `ValidationReport` with the following fields:

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `score` | `int` | 0–100 | Overall quality score. 80+ is considered passing. Computed from signal coverage, data handling, code structure, and issue severity. |
| `signal_coverage` | `float` | 0.0–1.0 | Fraction of signals described in the paper that are implemented in the generated code. 1.0 means every signal is present. |
| `data_coverage` | `float` | 0.0–1.0 | Fraction of required data sources that are handled. Checks for price data, fundamental data, macro data, etc. as specified in the paper. |
| `critical_count` | `int` | 0+ | Number of critical-severity issues found. Critical issues include look-ahead bias, missing core signals, and broken data pipelines. |
| `warning_count` | `int` | 0+ | Number of warning-severity issues found. Warnings include missing error handling, hardcoded values, and incomplete edge case handling. |
| `passed` | `bool` | — | `True` when `score >= 80` **and** `critical_count == 0`. The pipeline attempts auto-fix when this is `False`. |

**Issue categories:**

| Category | Description | Severity |
|----------|-------------|----------|
| `signal_fidelity` | Signal computation does not match paper methodology | Critical |
| `look_ahead_bias` | Code uses future data in signal/portfolio computations | Critical |
| `data_handling` | Missing NaN handling, incorrect join logic, timezone issues | Warning–Critical |
| `config` | Hardcoded hyperparameters that should be configurable | Warning |
| `rebalancing` | Rebalancing frequency or timing does not match paper | Warning |
| `transaction_costs` | Transaction costs not modeled or incorrectly modeled | Info–Warning |

### Backtest Validation Report

The backtest validation stage (agent mode) checks for finance-specific anti-patterns:

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `bias_risk_score` | `int` | 0–100 | Overall bias risk score. 0 = no detected risks, 100 = severe bias risks across multiple dimensions. Lower is better. |
| `passed` | `bool` | — | `True` when there are no failed critical checks. |
| `critical_count` | `int` | 0+ | Number of critical bias checks that failed. |
| `warning_count` | `int` | 0+ | Number of warning-level bias checks that failed. |
| `recommendations` | `list[str]` | — | Ordered list of actionable recommendations to improve the backtest. |

**Critical checks performed:**

| Check | What It Detects | Severity |
|-------|-----------------|----------|
| **Look-ahead bias** | Signals or portfolio weights computed using future data (e.g., `shift(-1)` instead of `shift(1)`) | Critical |
| **Survivorship bias** | Using current index constituents for historical backtests without adjusting for delisted securities | Critical |
| **Rebalancing timing** | Trades executed at prices not available at the decision point (e.g., using close price when signal is computed at close) | Critical |
| **Data snooping** | Hyperparameters suspiciously tuned to the sample period without out-of-sample validation | Warning |
| **Transaction costs** | Unrealistic or missing transaction cost assumptions | Warning |
| **Capacity constraints** | Strategy trades illiquid assets or requires unrealistic position sizes | Warning |
| **Out-of-sample** | No train/test split or walk-forward methodology | Info |
| **Benchmark comparison** | Missing or incorrect benchmark for risk-adjusted performance | Info |

### Evaluation Scoring

When `--evaluate` is enabled, the generated backtest receives a reference-based evaluation score:

| Score | Grade | Meaning |
|-------|-------|---------|
| **4.5–5.0** | **A** | Excellent. All core signals implemented correctly. Performance metrics closely match paper results. Production-ready with minor adjustments. |
| **3.5–4.4** | **B** | Good. Most signals implemented. Minor deviations from paper methodology. Suitable for research use. |
| **2.5–3.4** | **C** | Acceptable. Core signals present but implementation has gaps. Some methodology differences. Needs manual review. |
| **1.5–2.4** | **D** | Below average. Significant methodology gaps. Multiple signals missing or incorrectly implemented. Requires substantial rework. |
| **1.0–1.4** | **F** | Failing. Major structural issues. Core strategy logic missing or fundamentally wrong. |

**Component scores** are provided for individual aspects:

| Component | What Is Evaluated |
|-----------|-------------------|
| `signals` | Signal computation fidelity vs. paper equations |
| `portfolio` | Portfolio construction, weighting, rebalancing logic |
| `data` | Data sourcing, cleaning, alignment |
| `metrics` | Performance metric calculations (Sharpe, drawdown, etc.) |
| `structure` | Code organization, modularity, documentation |

---

## 7. Environment Variables

### Provider API Keys

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `GEMINI_API_KEY` | Google Gemini API key. Obtain from [AI Studio](https://aistudio.google.com/apikey). | — | Yes, for Gemini provider |
| `OPENAI_API_KEY` | OpenAI API key. Obtain from [OpenAI Platform](https://platform.openai.com/api-keys). | — | Yes, for OpenAI provider |
| `ANTHROPIC_API_KEY` | Anthropic API key. Obtain from [Anthropic Console](https://console.anthropic.com/). | — | Yes, for Anthropic provider |
| `OLLAMA_HOST` | Ollama server URL. Change this if Ollama is running on a remote machine or non-default port. | `http://localhost:11434` | No, for Ollama provider |

### Quant2Repo Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `Q2R_PROVIDER` | Default provider override. Set to `gemini`, `openai`, `anthropic`, or `ollama` to skip auto-detection. Equivalent to `--provider` CLI flag. | `auto` | No |
| `Q2R_MODEL` | Default model override. Set to a specific model name (e.g. `gpt-4o`) to use that model by default. Equivalent to `--model` CLI flag. | — | No |
| `Q2R_DATA_SOURCE` | Default data source for generated backtests. Controls which data provider the generated `data_loader.py` will use. Options: `yfinance`, `fred`, `quandl`. | `yfinance` | No |
| `Q2R_CACHE_DIR` | Custom cache directory for downloaded PDFs, parsed papers, and intermediate artifacts. Useful for shared environments or CI/CD. | `.q2r_cache` | No |
| `Q2R_VERBOSE` | Enable verbose mode globally. Set to `true`, `1`, or `yes` to enable. Equivalent to `--verbose` CLI flag. | `false` | No |

### Example: Full Environment Setup

```bash
# ~/.bashrc or ~/.zshrc

# Provider keys (set whichever you use)
export GEMINI_API_KEY="AIza..."
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."

# Quant2Repo defaults
export Q2R_PROVIDER="gemini"          # Prefer Gemini when available
export Q2R_DATA_SOURCE="yfinance"     # Use Yahoo Finance for market data
export Q2R_CACHE_DIR="$HOME/.q2r_cache"  # Shared cache directory
export Q2R_VERBOSE="false"            # Quiet mode by default

# Ollama (if running on a remote server)
# export OLLAMA_HOST="http://192.168.1.100:11434"
```

---

## 8. Programmatic Usage

Quant2Repo can be used as a Python library in addition to the CLI. This is useful for integrating paper-to-backtest generation into larger systems, notebooks, or automation scripts.

### Agent Pipeline (Full)

```python
from providers.registry import get_provider
from agents.orchestrator import AgentOrchestrator

# Initialize provider (auto-detects from environment, or specify explicitly)
provider = get_provider("gemini")

# Configure the pipeline
orchestrator = AgentOrchestrator(provider=provider, config={
    "enable_refine": True,
    "enable_execution": True,
    "enable_tests": True,
    "enable_devops": True,
    "enable_backtest_validation": True,
    "enable_code_rag": False,
    "enable_context_manager": True,
    "max_refine_iterations": 2,
    "max_debug_iterations": 3,
    "verbose": False,
})

# Run the pipeline
result = orchestrator.run(
    pdf_url="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975",
    output_dir="./my_strategy",
)

# Inspect results
print(f"Files generated: {len(result.files)}")
print(f"Strategy: {result.extraction.strategy_name}")
print(f"Validation score: {result.validation_report.score}/100")
print(f"Validation passed: {result.validation_report.passed}")

if result.backtest_validation:
    print(f"Bias risk score: {result.backtest_validation.bias_risk_score}/100")

if result.evaluation_score:
    print(f"Evaluation: {result.evaluation_score.overall_score}/5 "
          f"(Grade: {result.evaluation_score.grade})")
```

### Classic Pipeline

```python
from config import Q2RConfig
from providers.registry import get_provider
from core.paper_parser import PaperParser, download_pdf
from core.strategy_extractor import StrategyExtractor
from core.planner import DecomposedPlanner
from core.coder import CodeSynthesizer
from core.validator import CodeValidator

config = Q2RConfig.from_env()
provider = get_provider("gemini")

# Step 1: Parse paper
pdf_path = download_pdf("https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975")
parser = PaperParser()
parsed = parser.parse(pdf_path)
paper_text = parsed.get_text_for_analysis()

# Step 2: Extract strategy
extractor = StrategyExtractor(provider, config)
extraction = extractor.extract(paper_text)
print(f"Strategy: {extraction.strategy_name}")
print(f"Signals: {[s.signal_type for s in extraction.signals]}")

# Step 3: Plan architecture
planner = DecomposedPlanner(provider, config)
planning = planner.plan(paper_text, extraction.to_dict())
print(f"Planned files: {len(planning.combined_plan.files)}")

# Step 4: Generate code
coder = CodeSynthesizer(provider, config)
files = coder.generate_codebase(planning.combined_plan, paper_text, extraction.to_dict())
print(f"Generated: {len(files)} files")

# Step 5: Validate
validator = CodeValidator(provider, config)
report = validator.validate(files, paper_text, extraction.to_dict())
print(f"Validation: {report.score}/100 ({'PASS' if report.passed else 'FAIL'})")
```

### Strategy Catalog

```python
from quant.catalog import list_strategies, get_strategy, search
from quant.catalog import by_asset_class, by_signal_type, by_sharpe_range

# List all strategies
strategies = list_strategies()
print(f"Total strategies: {len(strategies)}")

# Look up a specific strategy by ID
entry = get_strategy("time-series-momentum")
if entry:
    print(f"Title: {entry.title}")
    print(f"Asset classes: {entry.asset_classes}")
    print(f"Sharpe ratio: {entry.sharpe_ratio}")
    print(f"Paper URL: {entry.paper_url}")

# Search by keyword (returns list of (score, StrategyEntry) tuples)
results = search("momentum")
for score, strategy in results:
    print(f"  {strategy.id}: {strategy.title} (SR={strategy.sharpe_ratio:+.3f})")

# Filter by asset class
equity_strategies = by_asset_class("equities")
print(f"Equity strategies: {len(equity_strategies)}")

# Filter by signal type
momentum_strategies = by_signal_type("momentum")
print(f"Momentum strategies: {len(momentum_strategies)}")

# Filter by Sharpe ratio range
high_sharpe = by_sharpe_range(low=0.5, high=2.0)
print(f"High-Sharpe strategies: {len(high_sharpe)}")
```

### Provider Registry

```python
from providers.registry import ProviderRegistry, get_provider

# Auto-detect the best available provider
provider = get_provider()
print(f"Provider: {provider.__class__.__name__}")
print(f"Model: {provider.default_model}")

# List all available providers
registry = ProviderRegistry()
available = registry.detect_available()
print(f"Available providers: {available}")

# List all models for a provider
provider = get_provider("gemini")
for model in provider.available_models():
    caps = [c.value for c in model.capabilities]
    print(f"  {model.name}: {model.max_context_tokens:,} tokens, caps={caps}")

# Get the best provider for a specific capability
from providers.base import ModelCapability
best_for_vision = registry.best_for(ModelCapability.VISION)
print(f"Best for vision: {best_for_vision}")
```

### Integration with Jupyter Notebooks

```python
# In a Jupyter notebook cell:
import sys
sys.path.insert(0, "/path/to/Quant2Repo")

from providers.registry import get_provider
from agents.orchestrator import AgentOrchestrator

provider = get_provider()
orchestrator = AgentOrchestrator(provider=provider, config={
    "enable_refine": True,
    "enable_execution": False,   # Skip Docker in notebook
    "enable_devops": False,      # Skip DevOps files
    "verbose": True,
})

result = orchestrator.run(
    pdf_url="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975",
    output_dir="./notebook_output",
)

# Display generated files
for filename, content in sorted(result.files.items()):
    print(f"\n{'='*60}")
    print(f"  {filename}")
    print(f"{'='*60}")
    print(content[:500])  # First 500 chars of each file
```

---

## 9. Choosing Between Classic and Agent Modes

Quant2Repo offers two pipeline modes. Choose based on your use case:

### Feature Comparison

| Aspect | Classic (`--mode classic`) | Agent (`--mode agent`) |
|--------|---------------------------|------------------------|
| **Pipeline stages** | 6 | 11 |
| **Planning** | Basic single-pass plan | 4-stage decomposed planning (overall → architecture → signal logic → config) |
| **Self-refine** | None | Optional verify/refine loops at each stage (`--refine`) |
| **File analysis** | None | Per-file deep analysis with accumulated context before generation |
| **Code generation** | All files generated in a single pass | Dependency-ordered generation with sliding context management |
| **Context management** | Minimal | Clean-slate context manager with LLM-generated summaries of prior files |
| **Validation** | Code validation only (signal fidelity, data handling) | Code validation + backtest bias checks (look-ahead, survivorship, data snooping) |
| **Execution** | None | Docker/local sandbox + auto-debug (`--execute`) |
| **Test generation** | Basic (optional, `--skip-tests` to disable) | Comprehensive per-module tests (optional, `--no-tests` to disable) |
| **DevOps** | None | Dockerfile, Makefile, CI/CD workflow, setup.py (`--no-devops` to disable) |
| **Evaluation** | None | Reference-based 1–5 scoring with component breakdown (`--evaluate`) |
| **CodeRAG** | None | GitHub mining for reference implementations (`--code-rag`) |
| **Interactive mode** | None | Pause after planning for user review (`--interactive`) |
| **Speed** | Fast (2–5 minutes typical) | Slower (5–15 minutes typical, more LLM calls) |
| **LLM calls** | ~4–6 calls | ~15–30+ calls (varies with options) |
| **Cost** | Lower | Higher (roughly 3–5x classic) |
| **Best for** | Quick prototyping, simple strategies, exploration | Production-quality backtests, complex multi-signal strategies, publishable research |

### When to Use Classic Mode

- **Quick prototyping** — You want a fast first draft to understand a paper's strategy
- **Simple strategies** — Single-signal strategies with straightforward portfolio rules
- **Cost-sensitive** — You want to minimize API usage and costs
- **Iterating rapidly** — You plan to run the pipeline multiple times with different papers
- **Manual review** — You intend to heavily modify the generated code anyway

```bash
# Classic mode: fast, cheap, good enough for exploration
python main.py --pdf_url "https://papers.ssrn.com/..." --mode classic
```

### When to Use Agent Mode

- **Complex strategies** — Multi-signal strategies with conditional logic, regime switching, or cross-asset rules
- **Production quality** — You want code that is well-tested, validated, and ready to run
- **Bias awareness** — You need confidence that the backtest is free of look-ahead and survivorship bias
- **Reproducibility** — You want Docker containers and CI/CD for reproducible execution
- **Evaluation** — You want to compare the output against a reference implementation or the paper's reported results

```bash
# Agent mode: thorough, validated, production-ready
python main.py --pdf_url "https://papers.ssrn.com/..." \
  --mode agent --refine --execute --evaluate
```

### Decision Flowchart

```
Start
  │
  ├─ Need it fast / exploring?
  │   └─ YES → Classic mode
  │
  ├─ Complex multi-signal strategy?
  │   └─ YES → Agent mode + --refine
  │
  ├─ Need to actually run the backtest?
  │   └─ YES → Agent mode + --execute
  │
  ├─ Publishing results or sharing code?
  │   └─ YES → Agent mode + --refine + --execute + --evaluate
  │
  └─ Want maximum quality, cost is not a concern?
      └─ YES → Agent mode + --refine + --execute + --evaluate + --code-rag
```

### Cost Estimates

Approximate costs per paper (varies with paper length and provider pricing):

| Mode | Gemini 2.5 Pro | GPT-4o | Claude Sonnet 4 |
|------|---------------|--------|-----------------|
| **Classic** | $0.05–$0.15 | $0.20–$0.60 | $0.15–$0.45 |
| **Agent** (basic) | $0.15–$0.40 | $0.60–$1.50 | $0.45–$1.20 |
| **Agent** (full) | $0.30–$0.80 | $1.20–$3.00 | $0.90–$2.40 |

> **Note:** Costs depend heavily on paper length, number of signals, and retry/refine iterations. The estimates above assume a typical 30-page paper with 2–3 signals.

---

## Next Steps

- **[Architecture Overview](Architecture-Overview)** — Understand the system design, component interactions, and data flow
- **[Pipeline Stages Deep Dive](Pipeline-Stages-Deep-Dive)** — Detailed walkthrough of all 11 pipeline stages
- **[Provider System & Configuration](Provider-System-and-Configuration)** — Advanced provider setup, capability routing, and model selection
- **[Gateway Integration](Gateway-Integration)** — Connect Quant2Repo to the Any2Repo-Gateway for managed execution
- **[Deployment & DevOps](Deployment-and-DevOps)** — Docker deployment, CI/CD, and production considerations
