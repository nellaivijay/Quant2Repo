# Architecture Overview

> Comprehensive architecture documentation for **Quant2Repo** (Q2R) — the
> multi-model agentic framework that converts quantitative-finance research
> papers into production-ready backtesting repositories.

---

## Table of Contents

1. [System Context](#1-system-context)
2. [Architecture Philosophy](#2-architecture-philosophy)
3. [High-Level Component Diagram](#3-high-level-component-diagram)
4. [Module Dependency Graph](#4-module-dependency-graph)
5. [Data Flow](#5-data-flow)
6. [Key Design Patterns](#6-key-design-patterns)
7. [Cross-Cutting Concerns](#7-cross-cutting-concerns)
8. [Technology Stack](#8-technology-stack)

---

## 1. System Context

Quant2Repo is a CLI-driven pipeline that ingests a quantitative-finance
research paper (PDF or catalog entry) and produces a fully self-contained
backtesting repository — complete with data loaders, signal generators,
portfolio constructors, performance analytics, visualization, tests,
DevOps files, and documentation.

### 1.1 Input / Output Summary

| Input                                                       | Output                                                         |
|-------------------------------------------------------------|----------------------------------------------------------------|
| PDF URL (SSRN, arXiv, NBER, or direct link)                 | `config.py` — strategy parameters and hyperparameters          |
| Local PDF file path (`--pdf_path`)                          | `data_loader.py` — market data acquisition and preprocessing   |
| Catalog strategy ID (`--catalog <id>`)                      | `signals.py` — signal construction from paper methodology      |
| Provider / model selection (`--provider`, `--model`)        | `portfolio.py` — portfolio formation and rebalancing logic     |
| Mode selection (`--mode classic` or `--mode agent`)         | `analysis.py` — performance metrics and risk analytics         |
| Feature flags (`--refine`, `--execute`, `--evaluate`)       | `visualization.py` — equity curves, drawdown, factor plots     |
|                                                             | `main.py` — CLI entry point that orchestrates the backtest     |
|                                                             | `Dockerfile`, `Makefile`, CI workflow (`.github/`)             |
|                                                             | `README.md` — strategy documentation with usage instructions   |
|                                                             | `requirements.txt` — pinned Python dependencies                |
|                                                             | `tests/` — pytest suite (signals, portfolio, metrics, config)  |
|                                                             | `q2r_metadata.json` — run provenance and pipeline metadata     |

### 1.2 External Dependencies

```
+-------------------+       +-------------------+       +-------------------+
|   LLM APIs        |       |   PDF Tools       |       |  Execution Env    |
|                   |       |                   |       |                   |
|  Gemini API  -----+--+    |  GROBID (TEI/XML) |       |  Docker Engine    |
|  OpenAI API  -----+  |    |  PyMuPDF (fitz)   |       |  subprocess       |
|  Anthropic API ---+  |    |  PyPDF2           |       |  Local Python     |
|  Ollama (local) --+  |    |  lxml             |       |                   |
+-------------------+  |    +--------+----------+       +--------+----------+
                       |             |                            |
                       v             v                            v
                 +-----+-------------+----------------------------+------+
                 |                                                       |
                 |            Quant2Repo Pipeline Engine                  |
                 |                                                       |
                 |  main.py -> providers/ -> core/ -> advanced/ -> save  |
                 |                                                       |
                 +--+--------------------------------------------+------+
                    |                                            |
                    v                                            v
          +---------+----------+                  +--------------+---------+
          |  Strategy Catalog  |                  |  Generated Repository  |
          |  catalog/          |                  |  ./generated_repo/     |
          |  strategies.json   |                  |                        |
          |  (47 strategies)   |                  |  config.py             |
          +--------------------+                  |  data_loader.py        |
                                                  |  signals.py            |
                                                  |  portfolio.py          |
                                                  |  analysis.py           |
                                                  |  visualization.py      |
                                                  |  main.py               |
                                                  |  tests/                |
                                                  |  Dockerfile            |
                                                  |  README.md             |
                                                  +-----------------------+
```

### 1.3 External Dependency Table

| Dependency           | Purpose                                    | Required | Import Guard        |
|----------------------|--------------------------------------------|----------|---------------------|
| `requests`           | PDF download from SSRN / arXiv / NBER      | Yes      | Top-level           |
| `PyPDF2`             | Fallback PDF text extraction               | Yes      | Top-level           |
| `PyMuPDF` (`fitz`)   | Primary PDF parsing + page image export    | No       | `try/except Import` |
| `lxml`               | GROBID TEI-XML parsing                     | No       | `try/except Import` |
| `pyyaml`             | Strategy config serialization              | No       | `try/except Import` |
| `google-generativeai`| Gemini provider SDK                        | No       | Lazy in provider    |
| `openai`             | OpenAI provider SDK                        | No       | Lazy in provider    |
| `anthropic`          | Anthropic provider SDK                     | No       | Lazy in provider    |
| `Docker`             | Sandboxed backtest execution               | No       | Runtime check       |
| `subprocess`         | Local fallback execution                   | Yes      | stdlib              |
| `pandas`             | Used in generated code (data manipulation) | No*      | In generated repo   |
| `numpy`              | Used in generated code (numerical ops)     | No*      | In generated repo   |
| `yfinance`           | Used in generated code (market data)       | No*      | In generated repo   |

> \* These are dependencies of the *generated* backtest repository, not of
> the Q2R engine itself.

---

## 2. Architecture Philosophy

### 2.1 Zero-RAG (Full-Context)

Quant2Repo follows the same full-context approach as Research2Repo: the
**entire paper** is sent to the LLM in a single context window rather than
using retrieval-augmented generation (RAG) over chunked embeddings.

```
+---------------------------+       +---------------------------+
|     Traditional RAG       |       |   Q2R Full-Context        |
|                           |       |                           |
|  PDF -> Chunk -> Embed    |       |  PDF -> Full Text         |
|  Query -> Retrieve Top-K  |       |       (up to 500K chars)  |
|  LLM sees ~5 chunks       |       |  LLM sees entire paper   |
|                           |       |                           |
|  - Loses global context   |       |  + Preserves equations    |
|  - May miss equations     |       |  + Cross-section refs     |
|  - Chunk boundary issues  |       |  + Table/figure context   |
+---------------------------+       +---------------------------+
```

**Rationale:** Quant papers are dense with cross-referenced equations,
tables, and methodology sections.  Signal construction in Section 3 may
reference variable definitions in Section 2 and robustness tests in
Section 5.  Chunking loses these connections.

**Gemini advantage:** The Gemini provider supports native PDF file upload
via `upload_file()` + `generate_with_file()`, preserving layout, tables,
and mathematical notation without any text extraction loss.

### 2.2 Multi-Model Abstraction

All LLM interactions flow through a provider abstraction layer defined in
`providers/base.py`.

```
providers/base.py
  |
  +-- BaseProvider (ABC)
  |     |
  |     +-- @abstractmethod default_model -> str
  |     +-- @abstractmethod available_models() -> list[ModelInfo]
  |     +-- @abstractmethod generate(prompt, ...) -> GenerationResult
  |     +-- @abstractmethod generate_structured(prompt, schema, ...) -> dict
  |     +-- upload_file(path) -> object         # optional, raises NotImpl
  |     +-- generate_with_file(file, prompt, ...) -> GenerationResult  # optional
  |
  +-- ModelCapability (Enum)
  |     TEXT_GENERATION, VISION, LONG_CONTEXT, STRUCTURED_OUTPUT,
  |     CODE_GENERATION, FILE_UPLOAD, STREAMING
  |
  +-- ModelInfo (frozen dataclass)
  |     name, provider, max_context_tokens, max_output_tokens,
  |     capabilities: frozenset[ModelCapability],
  |     cost_per_1k_input, cost_per_1k_output
  |
  +-- GenerationConfig (dataclass)
  |     temperature, top_p, max_output_tokens,
  |     stop_sequences, response_format
  |
  +-- GenerationResult (dataclass)
        text, model, input_tokens, output_tokens,
        finish_reason, raw_response
```

**Four backends** implement `BaseProvider`:

| Provider    | Module                        | Class               | Auth Env Var       |
|-------------|-------------------------------|----------------------|--------------------|
| Gemini      | `providers/gemini.py`         | `GeminiProvider`     | `GEMINI_API_KEY`   |
| OpenAI      | `providers/openai_provider.py`| `OpenAIProvider`     | `OPENAI_API_KEY`   |
| Anthropic   | `providers/anthropic_provider.py`| `AnthropicProvider`| `ANTHROPIC_API_KEY`|
| Ollama      | `providers/ollama.py`         | `OllamaProvider`     | `OLLAMA_HOST`      |

### 2.3 Capability-Based Routing

The `ProviderRegistry` in `providers/registry.py` implements capability-
based routing so the pipeline can automatically select the best available
provider for each task.

**`ModelCapability` enum values:**

| Capability          | Value                | Description                              |
|---------------------|----------------------|------------------------------------------|
| `TEXT_GENERATION`   | `"text_generation"`  | Basic text completion                    |
| `VISION`            | `"vision"`           | Image / diagram understanding            |
| `LONG_CONTEXT`      | `"long_context"`     | 100K+ token context windows              |
| `STRUCTURED_OUTPUT` | `"structured_output"`| JSON-schema-constrained output           |
| `CODE_GENERATION`   | `"code_generation"`  | Optimized for code synthesis             |
| `FILE_UPLOAD`       | `"file_upload"`      | Native PDF/file upload support           |
| `STREAMING`         | `"streaming"`        | Token-by-token streaming responses       |

**Per-capability preference orders** (defined in `_CAPABILITY_PREFERENCES`):

```python
LONG_CONTEXT:      ["gemini", "anthropic", "openai", "ollama"]
VISION:            ["gemini", "openai", "anthropic", "ollama"]
CODE_GENERATION:   ["anthropic", "openai", "gemini", "ollama"]
STRUCTURED_OUTPUT: ["openai", "gemini", "anthropic", "ollama"]
TEXT_GENERATION:    ["openai", "anthropic", "gemini", "ollama"]
FILE_UPLOAD:       ["gemini"]
STREAMING:         ["openai", "anthropic", "gemini", "ollama"]
```

**Resolution via `ProviderRegistry.best_for(capability)`:**

```
best_for(LONG_CONTEXT)
  |
  +-> detect_available()  -- checks env vars / Ollama connectivity
  |     returns ["gemini", "ollama"]          (example)
  |
  +-> iterate preference order for LONG_CONTEXT:
  |     gemini -> in available? YES -> return "gemini"
  |
  +-> ProviderRegistry.create("gemini") -> GeminiProvider instance
```

**Convenience function `get_provider()`** resolution order:

1. Explicit `provider_name` given -> use directly
2. `required_capability` given -> `best_for(capability)`
3. Neither -> first available from default list (`openai -> anthropic -> gemini -> ollama`)

### 2.4 Lazy Imports

All heavy imports are deferred to method bodies — particularly in
`AgentOrchestrator` and `main.py` — to avoid circular imports and
enable fast CLI startup:

```python
# main.py :: run_classic()
def run_classic(...):
    from config import Q2RConfig                     # deferred
    from providers.registry import get_provider      # deferred
    from core.paper_parser import PaperParser        # deferred
    from core.strategy_extractor import StrategyExtractor  # deferred
    from core.planner import DecomposedPlanner        # deferred
    from core.coder import CodeSynthesizer            # deferred
    from core.validator import CodeValidator           # deferred
    ...
```

```python
# agents/base.py :: PaperAnalysisAgent.execute()
def execute(self, ...):
    from core.paper_parser import PaperParser          # deferred
    from core.strategy_extractor import StrategyExtractor  # deferred
    ...
```

This pattern is used consistently across all agent classes
(`PaperAnalysisAgent`, `PlanningAgent`, `FileAnalysisAgent`,
`CodeGenerationAgent`, `ValidationAgent`) and in the orchestrator's
stage methods.

### 2.5 Graceful Degradation

Every optional dependency and backend is wrapped in `try/except
ImportError` guards with fallback paths:

```
PaperParser.parse(pdf_path)
  |
  +-> try _parse_grobid()    -- needs running GROBID server + lxml
  |     except -> fallback
  |
  +-> try _parse_pymupdf()   -- needs PyMuPDF (fitz)
  |     except ImportError -> fallback
  |
  +-> try _parse_pypdf2()    -- needs PyPDF2 (always installed)
  |     except -> raise RuntimeError("All backends failed")
```

```
TEI XML parsing:
  try:
      from lxml import etree    # full XML parser
  except ImportError:
      _parse_tei_regex()        # regex fallback (no lxml needed)
```

Similar fallback chains exist for:
- Provider creation (missing SDK -> skip provider in `detect_available()`)
- Pipeline cache (missing `advanced/cache.py` -> `cache = None`, proceed)
- CodeRAG (disabled by default, guarded with `try/except` in orchestrator)
- Context manager (optional, controlled by `enable_context_manager` flag)
- Docker execution (missing Docker -> fall back to local `subprocess`)

### 2.6 Quant-Domain Specialization

Unlike Research2Repo (R2R) which targets general ML papers, Q2R adds
domain-specific components tailored to quantitative finance:

| R2R Component       | Q2R Equivalent             | Specialization                          |
|---------------------|----------------------------|-----------------------------------------|
| `PaperAnalyzer`     | `StrategyExtractor`        | Extracts signals, portfolio rules, asset universe, reported Sharpe ratios |
| Generic validation  | `BacktestValidator`        | Checks for look-ahead bias, survivorship bias, data snooping, overfitting |
| N/A                 | `StrategyCatalog`          | 47 pre-indexed strategies with paper URLs, Sharpe ratios, asset classes |
| Generic prompts     | Quant prompt templates     | 14 templates in `prompts/` with signal-construction, bias-detection focus |
| N/A                 | `quant/signals.py`         | Signal type taxonomy (momentum, value, carry, mean-reversion, etc.) |
| N/A                 | `quant/asset_classes.py`   | Asset class definitions and universe filters |
| N/A                 | `quant/metrics.py`         | Quant performance metrics (Sharpe, Sortino, Calmar, VaR, CVaR, etc.) |
| N/A                 | `quant/data_sources.py`    | Data source registry (yfinance, WRDS, Bloomberg, etc.) |

**`StrategyExtraction` dataclass** captures quant-specific fields:

```
StrategyExtraction
  +-- strategy_name: str
  +-- authors: list[str]
  +-- publication_year: int
  +-- asset_classes: list[str]      # ["equities", "bonds", ...]
  +-- signals: list[SignalConstruction]
  |     +-- signal_type: str        # "momentum", "value", ...
  |     +-- formula: str            # LaTeX equation
  |     +-- lookback_period: str    # "12 months"
  |     +-- skip_period: str        # "1 month" (12-1 momentum)
  |     +-- normalization: str      # "cross-sectional rank"
  |     +-- is_cross_sectional: bool
  |     +-- is_time_series: bool
  |     +-- detailed_steps: list[str]
  +-- portfolio: PortfolioConstruction
  |     +-- method: str             # "quartile sort", "decile", ...
  |     +-- long_leg / short_leg: str
  |     +-- weighting: str          # "equal-weight", "value-weight"
  |     +-- rebalancing_frequency: str
  +-- reported_results: ReportedResults
  |     +-- sharpe_ratio: float
  |     +-- annual_return: float
  |     +-- max_drawdown: float
  |     +-- t_statistic: float
  |     +-- sample_period: str
  +-- data_requirements: list[str]
  +-- key_equations: list[str]
  +-- risk_model: str
```

---

## 3. High-Level Component Diagram

```
+=========================================================================+
|                          CLI / Entry Points                              |
|                                                                         |
|  main.py                          gateway_adapter.py                    |
|  +-- run_classic()                +-- is_gateway_mode()                 |
|  +-- run_agent()                  +-- run_gateway_job()                 |
|  +-- list_catalog()               +-- write_status_file()              |
|  +-- search_catalog()                                                   |
|  +-- list_providers_cmd()                                               |
+====+=======================+========================================+===+
     |                       |                                        |
     v                       v                                        |
+====+======================+====+                                    |
|      Provider Layer             |                                    |
|                                 |                                    |
|  providers/registry.py          |                                    |
|  +-- ProviderRegistry           |                                    |
|  |   +-- create()               |                                    |
|  |   +-- detect_available()     |                                    |
|  |   +-- best_for(capability)   |                                    |
|  |   +-- estimate_cost()        |                                    |
|  +-- get_provider()             |                                    |
|                                 |                                    |
|  providers/base.py              |                                    |
|  +-- BaseProvider (ABC)         |                                    |
|  +-- ModelCapability (Enum)     |                                    |
|  +-- retry_on_error()           |                                    |
|                                 |                                    |
|  providers/gemini.py            |                                    |
|  providers/openai_provider.py   |                                    |
|  providers/anthropic_provider.py|                                    |
|  providers/ollama.py            |                                    |
+=============+==================++=                                   |
              |                                                        |
              v                                                        |
+=============+====================================================+   |
|                     Core Pipeline (core/)                         |   |
|                                                                   |   |
|  paper_parser.py        strategy_extractor.py    planner.py       |   |
|  +-- PaperParser        +-- StrategyExtractor    +-- Decomposed   |   |
|  +-- ParsedPaper        +-- StrategyExtraction   |   Planner      |   |
|  +-- download_pdf()     +-- SignalConstruction   +-- OverallPlan  |   |
|                         +-- PortfolioConstr.     +-- Architecture |   |
|                         +-- ReportedResults      |   Design       |   |
|                                                  +-- LogicDesign  |   |
|                                                  +-- Architecture |   |
|  file_analyzer.py       coder.py                 |   Plan         |   |
|  +-- FileAnalyzer       +-- CodeSynthesizer                      |   |
|  +-- FileAnalysis       +-- _compute_depth_                      |   |
|                         |   levels()  (topo sort)                 |   |
|  validator.py           +-- generate_codebase()                   |   |
|  +-- CodeValidator                                                |   |
|  +-- ValidationReport   refiner.py                                |   |
|  +-- ValidationIssue    +-- SelfRefiner                           |   |
|                         +-- RefinementResult                      |   |
+==============+====================================================+   |
               |                                                        |
               v                                                        |
+==============+====================================================+   |
|                   Advanced Layer (advanced/)                       |   |
|                                                                   |   |
|  backtest_validator.py   executor.py          debugger.py         |   |
|  +-- BacktestValidator   +-- ExecutionSandbox +-- AutoDebugger    |   |
|  +-- BacktestValidation  +-- ExecutionResult  +-- DebugReport     |   |
|      Report              +-- Docker/local     +-- DebugFix        |   |
|  +-- BiasCheck                fallback                            |   |
|                                                                   |   |
|  evaluator.py            test_generator.py    devops.py           |   |
|  +-- ReferenceEvaluator  +-- TestGenerator    +-- DevOpsGenerator |   |
|  +-- EvaluationScore     +-- 4 test specs:    +-- Dockerfile      |   |
|                          |   signals,         +-- Makefile        |   |
|  code_rag.py             |   portfolio,       +-- CI workflow     |   |
|  +-- CodeRAG             |   metrics,         +-- docker-compose  |   |
|  +-- CodeRAGIndex        |   config           +-- setup.py        |   |
|  +-- ReferenceFile                                                |   |
|                          cache.py                                 |   |
|  context_manager.py      +-- PipelineCache                       |   |
|  +-- ContextManager      +-- hash_file()                         |   |
|  +-- FileSummary         +-- Content-addressed                   |   |
|                              storage                              |   |
+==============+====================================================+   |
               |                                                        |
               v                                                        |
+==============+====================================================+   |
|                     Agent Layer (agents/)                          |   |
|                                                                   |   |
|  base.py                                                          |   |
|  +-- BaseAgent (ABC)                                              |   |
|  |   +-- execute() @abstractmethod                                |   |
|  |   +-- communicate(target, message)                             |   |
|  |   +-- receive(message)                                         |   |
|  +-- AgentMessage                                                 |   |
|  +-- PaperAnalysisAgent   (wraps PaperParser + StrategyExtractor) |   |
|  +-- PlanningAgent         (wraps DecomposedPlanner)              |   |
|  +-- FileAnalysisAgent     (wraps FileAnalyzer)                   |   |
|  +-- CodeGenerationAgent   (wraps CodeSynthesizer)                |   |
|  +-- ValidationAgent       (wraps CodeValidator)                  |   |
|                                                                   |   |
|  orchestrator.py                                                  |   |
|  +-- AgentOrchestrator                                            |   |
|  |   +-- run() -> PipelineResult                                  |   |
|  |   +-- _stage_parse_paper()                                     |   |
|  |   +-- _stage_extract_strategy()                                |   |
|  |   +-- _stage_plan()                                            |   |
|  |   +-- _stage_analyze_files()                                   |   |
|  |   +-- _stage_generate_code()                                   |   |
|  |   +-- _stage_generate_tests()                                  |   |
|  |   +-- _stage_validate()                                        |   |
|  |   +-- _stage_backtest_validate()                               |   |
|  |   +-- _stage_execute()                                         |   |
|  |   +-- _stage_devops()                                          |   |
|  |   +-- _stage_evaluate()                                        |   |
|  +-- PipelineResult                                               |   |
+==============+====================================================+   |
               |                                                        |
               v                                                        |
+==============+====================================================+   |
|                   Quant Domain (quant/)                            |<--+
|                                                                   |
|  catalog.py            signals.py          asset_classes.py       |
|  +-- StrategyEntry     +-- Signal type     +-- Asset class        |
|  +-- list_strategies()    taxonomy            definitions         |
|  +-- search()          +-- MOMENTUM,       +-- EQUITIES,         |
|  +-- get_by_id()          VALUE, CARRY,       BONDS, CMDTY,      |
|  +-- filter_by()          MEAN_REVERSION,     CURRENCIES,        |
|                           VOLATILITY, ...     CRYPTO, REITS,     |
|  metrics.py                                   MULTI_ASSET        |
|  +-- Performance       data_sources.py                           |
|     metric defs        +-- Data source                           |
|  +-- Sharpe, Sortino,     registry                               |
|     Calmar, VaR,       +-- yfinance,                             |
|     CVaR, info_ratio      WRDS, etc.                             |
+===============================================================+===+
```

---

## 4. Module Dependency Graph

### 4.1 Import Tree (Simplified)

```
main.py
  |
  +--[classic]--> config.Q2RConfig.from_env()
  |               providers.registry.get_provider()
  |               core.paper_parser.PaperParser, download_pdf
  |               core.strategy_extractor.StrategyExtractor
  |               core.planner.DecomposedPlanner
  |               core.coder.CodeSynthesizer
  |               core.validator.CodeValidator
  |
  +--[agent]----> providers.registry.get_provider()
  |               agents.orchestrator.AgentOrchestrator
  |
  +--[catalog]--> quant.catalog.list_strategies, search, get_by_id
  |
  +--[provs]----> providers.registry.ProviderRegistry

gateway_adapter.py
  +-------------> main.run_classic() or main.run_agent()  (function import)
  +-------------> json, os, sys, time, requests
```

### 4.2 Provider Layer Imports

```
providers/registry.py
  +-> providers/base.py (BaseProvider, ModelCapability)
  +-> importlib (dynamic provider loading)
  |
  +-- .create("gemini") --> providers/gemini.py
  |                           +-> google.generativeai  (SDK)
  |                           +-> providers/base.py
  |
  +-- .create("openai") --> providers/openai_provider.py
  |                           +-> openai  (SDK)
  |                           +-> providers/base.py
  |
  +-- .create("anthropic") --> providers/anthropic_provider.py
  |                              +-> anthropic  (SDK)
  |                              +-> providers/base.py
  |
  +-- .create("ollama") --> providers/ollama.py
                              +-> urllib.request  (stdlib)
                              +-> providers/base.py
```

### 4.3 Orchestrator Internal Imports (Lazy)

```
agents/orchestrator.py
  |
  +-- Stage 1 --> core.paper_parser.PaperParser, download_pdf
  +-- Stage 2 --> core.strategy_extractor.StrategyExtractor
  +-- Stage 3 --> core.planner.DecomposedPlanner
  |               core.refiner.SelfRefiner          (if --refine)
  +-- Stage 4 --> core.file_analyzer.FileAnalyzer
  |               advanced.code_rag.CodeRAG          (if --code-rag)
  +-- Stage 5 --> core.coder.CodeSynthesizer
  |               advanced.context_manager.ContextManager
  +-- Stage 6 --> advanced.test_generator.TestGenerator
  +-- Stage 7 --> core.validator.CodeValidator
  +-- Stage 8 --> advanced.backtest_validator.BacktestValidator
  +-- Stage 9 --> advanced.executor.ExecutionSandbox
  |               advanced.debugger.AutoDebugger     (if execution fails)
  +-- Stage 10 -> advanced.devops.DevOpsGenerator
  +-- Stage 11 -> advanced.evaluator.ReferenceEvaluator  (if --evaluate)
  |
  +-- Cache ----> advanced.cache.PipelineCache       (try/except)
  +-- Catalog --> quant.catalog.get_by_id            (if --catalog)
```

### 4.4 Core Module Cross-Dependencies

```
core/paper_parser.py     -- standalone (requests, PyPDF2/fitz/lxml)
core/strategy_extractor.py -- providers/base.py (GenerationConfig)
core/planner.py          -- providers/base.py (GenerationConfig)
core/file_analyzer.py    -- providers/base.py (GenerationConfig)
core/coder.py            -- providers/base.py (GenerationConfig)
                            os, json, re, collections (topo sort)
core/validator.py        -- providers/base.py (GenerationConfig)
core/refiner.py          -- providers/base.py (GenerationConfig)
```

> **Note:** Core modules never import from `advanced/` or `agents/`.
> The dependency flow is strictly `agents/ -> advanced/ -> core/ -> providers/`.

---

## 5. Data Flow

### 5.1 Classic Mode (6 Stages)

Classic mode executes a linear pipeline without agent orchestration,
self-refinement, test generation, or execution.

```
+-------------+     +------------------+     +---------------------+
|  Stage 1    |     |  Stage 2         |     |  Stage 3            |
|  Parse      |     |  Extract         |     |  Plan               |
|             |     |                  |     |                     |
|  pdf_url or |     |  paper_text      |     |  paper_text         |
|  pdf_path   |     |       |          |     |  extraction_dict    |
|     |       |     |       v          |     |       |             |
|     v       |     | StrategyExtractor|     |       v             |
| download_pdf|     |       |          |     | DecomposedPlanner   |
| PaperParser |---->|       v          |---->|   4-sub-stages:     |
|     |       |     | StrategyExtract- |     |   1. Overall plan   |
|     v       |     |   ion (dataclass)|     |   2. Arch design    |
| paper_text  |     |                  |     |   3. Logic design   |
| (str)       |     |  extraction_dict |     |   4. Config gen     |
+-------------+     |  (dict)          |     |       |             |
                     +------------------+     |       v             |
                                              | ArchitecturePlan   |
                                              | (files list, class |
                                              |  diagram, config)  |
                                              +----------+---------+
                                                         |
                    +------------------------------------+
                    |
                    v
+-------------------+-------+     +---------------------+     +------------+
|  Stage 4                  |     |  Stage 5            |     |  Stage 6   |
|  Generate Code            |     |  Validate           |     |  Save      |
|                           |     |                     |     |            |
|  plan.files               |     |  generated_files    |     |  files     |
|  paper_text               |     |  paper_text         |     |  output_dir|
|  extraction_dict          |     |  extraction_dict    |     |     |      |
|       |                   |     |       |             |     |     v      |
|       v                   |     |       v             |     |  os.mkdir  |
|  CodeSynthesizer          |     |  CodeValidator      |     |  write()   |
|  _compute_depth_levels()  |     |  .validate()        |     |            |
|  generate per-file in     |---->|       |             |---->|  N files   |
|  dependency order         |     |       v             |     |  to disk   |
|       |                   |     |  ValidationReport   |     |            |
|       v                   |     |  score: 0-100       |     |  Done!     |
|  generated_files          |     |  if !passed:        |     |  elapsed   |
|  dict[str, str]           |     |    .fix_issues() x2 |     |            |
|  {path: content}          |     |    re-validate      |     |            |
+---------------------------+     +---------------------+     +------------+
```

**Data types flowing between stages:**

| From -> To        | Data Type                          | Key Fields                         |
|-------------------|------------------------------------|------------------------------------|
| Stage 1 -> 2      | `str` (paper_text)                 | Full paper text, up to 500K chars  |
| Stage 2 -> 3      | `dict` (extraction_dict)           | strategy_name, signals, portfolio  |
| Stage 2 -> 4,5    | `dict` (extraction_dict)           | Same as above (reused)             |
| Stage 3 -> 4      | `ArchitecturePlan`                 | files[], class_diagram, config     |
| Stage 4 -> 5      | `dict[str, str]` (generated_files) | {filepath: source_code}            |
| Stage 5 -> 6      | `dict[str, str]` (validated files) | Same dict, possibly with fixes     |

### 5.2 Agent Mode (11 Stages)

Agent mode adds self-refinement, file analysis, test generation,
backtest validation, sandboxed execution with auto-debugging, DevOps
file generation, and reference evaluation.

```
+=======================================================================+
|  Stage 1: Paper Parsing                                               |
|  pdf_url/pdf_path/catalog_id -> PaperParser -> paper_text (str)       |
|  catalog_id -> quant.catalog.get_by_id() -> catalog_metadata (dict)   |
+=====+=================================================================+
      |
      v
+=====+=================================================================+
|  Stage 2: Strategy Extraction                                         |
|  paper_text -> StrategyExtractor -> StrategyExtraction (dataclass)     |
|  -> extraction_dict (dict serialization)                              |
+=====+=================================================================+
      |
      v
+=====+=================================================================+
|  Stage 3: Decomposed Planning (+ optional SelfRefiner)                |
|  paper_text + extraction_dict -> DecomposedPlanner                     |
|    Sub-stage 3a: Overall backtest plan  (OverallPlan)                  |
|    Sub-stage 3b: Architecture design    (ArchitectureDesign)           |
|    Sub-stage 3c: Signal logic design    (LogicDesign)                  |
|    Sub-stage 3d: Config generation      (config YAML)                 |
|  If --refine: SelfRefiner.refine(plan) -> verify -> refine -> verify  |
|  Output: PlanningResult -> combined_plan (ArchitecturePlan)            |
+=====+=================================================================+
      |
      v
+=====+=================================================================+
|  Stage 4: Per-File Analysis (+ optional CodeRAG in parallel)          |
|  plan.files + paper_text -> FileAnalyzer.analyze_all()                 |
|    -> dict[str, FileAnalysis]                                         |
|  If --code-rag: CodeRAG.search_and_index() runs in parallel           |
|    -> CodeRAGIndex (reference code from GitHub)                       |
+=====+=================================================================+
      |
      v
+=====+=================================================================+
|  Stage 5: Code Synthesis (+ ContextManager)                           |
|  plan + paper_text + extraction + file_analyses                        |
|  -> CodeSynthesizer.generate_codebase()                               |
|  ContextManager rebuilds prompt per file:                             |
|    architecture plan (compressed)                                     |
|    + cumulative code summaries (1 paragraph per prior file)            |
|    + full source of direct dependencies                               |
|    + optional CodeRAG reference snippets                              |
|  Topological sort via _compute_depth_levels() for dep ordering        |
|  Output: dict[str, str]  {path: source_code}                         |
+=====+=================================================================+
      |
      v
+=====+=================================================================+
|  Stage 6: Test Generation                                             |
|  generated_files + extraction + paper_text -> TestGenerator            |
|  Generates 4 test files:                                              |
|    tests/test_signals.py     (signal correctness, no look-ahead bias) |
|    tests/test_portfolio.py   (portfolio construction logic)           |
|    tests/test_metrics.py     (performance calculations)               |
|    tests/test_config.py      (no hardcoded magic numbers)             |
|  Output: merged into generated_files dict                             |
+=====+=================================================================+
      |
      v
+=====+=================================================================+
|  Stage 7: Code Validation (+ auto-fix loop)                           |
|  generated_files -> CodeValidator.validate()                           |
|    -> ValidationReport (score 0-100, issues list)                     |
|  If !passed: fix_issues() + re-validate (up to max_fix_iterations)    |
|  Categories: signal_fidelity, look_ahead_bias, data_handling, config  |
+=====+=================================================================+
      |
      v
+=====+=================================================================+
|  Stage 8: Backtest Validation (bias detection)                        |
|  generated_files -> BacktestValidator                                  |
|  Static analysis (regex/AST):                                         |
|    - Look-ahead bias (future data access)                             |
|    - Survivorship bias (no universe filtering)                        |
|    - Data snooping (parameter optimization on test set)               |
|    - Transaction cost omission                                        |
|  LLM-powered deep validation                                         |
|  Output: BacktestValidationReport (bias_risk_score 0-100)             |
+=====+=================================================================+
      |
      v
+=====+=================================================================+
|  Stage 9: Execution Sandbox + Auto-Debugger (if --execute)            |
|  generated_files -> ExecutionSandbox                                   |
|    Docker preferred -> local subprocess fallback                      |
|    -> ExecutionResult (stdout, stderr, exit_code, duration)           |
|  If execution fails:                                                  |
|    AutoDebugger.debug_loop(files, error)                              |
|    -> DebugFix[] -> apply fixes -> re-execute                         |
|    Up to max_debug_iterations (default 3)                             |
+=====+=================================================================+
      |
      v
+=====+=================================================================+
|  Stage 10: DevOps Generation                                          |
|  generated_files -> DevOpsGenerator.generate_all()                     |
|  Adds: Dockerfile, docker-compose.yml, Makefile,                      |
|        .github/workflows/ci.yml, setup.py                             |
|  Output: merged into generated_files dict                             |
+=====+=================================================================+
      |
      v
+=====+=================================================================+
|  Stage 11: Reference Evaluation (if --evaluate)                       |
|  generated_files + paper_text -> ReferenceEvaluator                    |
|    Optional: compare against reference_dir (known-good implementation)|
|    Multiple independent LLM evaluations, aggregated                   |
|  Output: EvaluationScore (overall 1-5, per-component, coverage %)     |
+=====+=================================================================+
      |
      v
+=====+=================================================================+
|  Save to Disk                                                         |
|  generated_files -> output_dir/                                        |
|  q2r_metadata.json -> run provenance (provider, timestamps, scores)   |
+=====+=================================================================+
```

### 5.3 Data Type Summary (Agent Mode)

| Stage | Input Type(s)                                         | Output Type                      |
|-------|-------------------------------------------------------|----------------------------------|
| 1     | `str` (url/path), `str` (catalog_id)                  | `str` (paper_text), `ParsedPaper`|
| 2     | `str` (paper_text)                                    | `StrategyExtraction` -> `dict`   |
| 3     | `str`, `dict`                                         | `PlanningResult` (w/ `ArchitecturePlan`) |
| 4     | `ArchitecturePlan`, `str`, `dict`                     | `dict[str, FileAnalysis]`        |
| 5     | `ArchitecturePlan`, `str`, `dict`, file analyses      | `dict[str, str]` (files)         |
| 6     | `dict[str, str]`, `dict`, `str`                       | `dict[str, str]` (files + tests) |
| 7     | `dict[str, str]`, `str`, `dict`                       | `ValidationReport`, `dict`       |
| 8     | `dict[str, str]`                                      | `BacktestValidationReport`       |
| 9     | `dict[str, str]`                                      | `ExecutionResult`                |
| 10    | `dict[str, str]`                                      | `dict[str, str]` (files + devops)|
| 11    | `dict[str, str]`, `str`                               | `EvaluationScore`                |

---

## 6. Key Design Patterns

### 6.1 Strategy Pattern — Provider Abstraction

The `BaseProvider` abstract base class (`providers/base.py`) defines the
contract that all LLM backends must implement.  The pipeline code is
written against the abstract interface and never knows which concrete
provider is executing the request.

```
           BaseProvider (ABC)
          /       |       \        \
         /        |        \        \
  GeminiProvider  OpenAI   Anthropic  Ollama
                 Provider   Provider  Provider
```

Key abstract methods:
- `generate(prompt, ...) -> GenerationResult`
- `generate_structured(prompt, schema, ...) -> dict`
- `available_models() -> list[ModelInfo]`

Optional (default raises `NotImplementedError`):
- `upload_file(path) -> object`
- `generate_with_file(file, prompt, ...) -> GenerationResult`

### 6.2 Template Method — Prompt Templates

Prompt templates are loaded from the `prompts/` directory with
`{{placeholder}}` replacement.  Each pipeline stage loads its own
template file:

```
prompts/
  +-- strategy_extractor.txt    # Stage 2: strategy analysis
  +-- backtest_planner.txt      # Stage 3a: overall plan
  +-- architecture_design.txt   # Stage 3b: file structure
  +-- signal_logic.txt          # Stage 3c: signal logic
  +-- file_analysis.txt         # Stage 4: per-file specs
  +-- coder.txt                 # Stage 5: code generation
  +-- test_generator.txt        # Stage 6: test generation
  +-- validator.txt             # Stage 7: code validation
  +-- backtest_validator.txt    # Stage 8: bias detection
  +-- auto_debug.txt            # Stage 9: error fixing
  +-- devops.txt                # Stage 10: DevOps files
  +-- reference_eval.txt        # Stage 11: evaluation
  +-- self_refine_verify.txt    # Refinement: verify step
  +-- self_refine_refine.txt    # Refinement: refine step
```

**14 prompt templates** total.  Loading pattern:

```python
def _load_prompt(self) -> str:
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "prompts", "strategy_extractor.txt"
    )
    if os.path.exists(prompt_path):
        with open(prompt_path) as f:
            return f.read()
    return self._default_prompt()   # hardcoded fallback
```

Substitution: `prompt.replace("{{paper_text}}", paper_text)`

### 6.3 Pipeline / Chain — Sequential Stage Execution

Both classic and agent modes execute stages sequentially, where the
output of each stage feeds into the next:

```
Classic:  Parse -> Extract -> Plan -> Generate -> Validate -> Save
          [1]      [2]        [3]     [4]         [5]         [6]

Agent:    Parse -> Extract -> Plan -> Analyze -> Generate -> TestGen
          [1]      [2]        [3]     [4]        [5]         [6]
            -> Validate -> BiasCheck -> Execute -> DevOps -> Evaluate
               [7]         [8]          [9]        [10]      [11]
```

Each stage is a method on `AgentOrchestrator`:

```python
class AgentOrchestrator:
    def run(self, ...):
        paper_text = self._stage_parse_paper(...)     # Stage 1
        extraction = self._stage_extract_strategy(...)# Stage 2
        plan       = self._stage_plan(...)            # Stage 3
        analyses   = self._stage_analyze_files(...)   # Stage 4
        files      = self._stage_generate_code(...)   # Stage 5
        files      = self._stage_generate_tests(...)  # Stage 6
        report     = self._stage_validate(...)        # Stage 7
        bias       = self._stage_backtest_validate(...)# Stage 8
        exec_result= self._stage_execute(...)         # Stage 9
        files      = self._stage_devops(...)          # Stage 10
        eval_score = self._stage_evaluate(...)        # Stage 11
```

### 6.4 Observer — Agent Message Passing

`BaseAgent` subclasses communicate via `AgentMessage` objects:

```python
@dataclass
class AgentMessage:
    role: str = ""         # sender identifier
    content: str = ""      # message payload
    metadata: dict = {}    # arbitrary key-value pairs

class BaseAgent(ABC):
    def communicate(self, target: BaseAgent, message: AgentMessage):
        target.receive(message)

    def receive(self, message: AgentMessage):
        self._messages.append(message)

    def get_messages(self, role: str = None) -> list:
        ...
```

This enables inter-agent coordination — for example, the
`ValidationAgent` can send fix suggestions back to the
`CodeGenerationAgent` via messages.

### 6.5 Factory — Provider Registry

`ProviderRegistry.create()` is a factory method that instantiates
provider objects by name, using dynamic module loading:

```python
@classmethod
def create(cls, provider_name, *, api_key=None, model_name=None):
    module_path, class_name, _env_key = cls._PROVIDERS[provider_name]
    module = importlib.import_module(module_path)    # dynamic import
    provider_cls = getattr(module, class_name)
    return provider_cls(**kwargs)
```

Registration of custom providers:

```python
ProviderRegistry.register(
    name="my_provider",
    module_path="my_package.provider",
    class_name="MyProvider",
    env_key="MY_API_KEY",
)
```

### 6.6 Topological Sort — Dependency-Ordered Code Generation

`CodeSynthesizer._compute_depth_levels()` groups files by dependency
depth using topological sort (BFS/Kahn's algorithm).  Files at the
same depth can be generated in parallel:

```
Depth 0:  config.py, requirements.txt
Depth 1:  data_loader.py
Depth 2:  signals.py
Depth 3:  portfolio.py
Depth 4:  analysis.py
Depth 5:  visualization.py, main.py
```

Implicit dependency map (`_IMPLICIT_DEPS`):

```python
_IMPLICIT_DEPS = {
    "signals.py":        ["config.py", "data_loader.py"],
    "portfolio.py":      ["config.py", "signals.py"],
    "analysis.py":       ["config.py", "portfolio.py"],
    "visualization.py":  ["config.py", "analysis.py"],
    "main.py":           ["config.py", "data_loader.py", "signals.py"],
}
```

This ensures that when `signals.py` is generated, `config.py` and
`data_loader.py` are already available as context.

### 6.7 Content-Addressed Cache

`PipelineCache` in `advanced/cache.py` provides file-system-backed
caching keyed by the SHA-256 hash of the input PDF:

```
.q2r_cache/
  <pdf_hash_16chars>/
    extraction.pkl      -- pickled StrategyExtraction
    plan.pkl            -- pickled ArchitecturePlan
    metadata.json       -- provider name, timestamps, config
    files/              -- generated source tree
      config.py
      data_loader.py
      signals.py
      ...
```

```python
class PipelineCache:
    @staticmethod
    def hash_file(file_path: str) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
```

This enables fast re-runs when iterating on the same paper — the
extraction and planning stages can be skipped entirely if the cache
contains valid results.

---

## 7. Cross-Cutting Concerns

### 7.1 Logging

Standard Python `logging` with per-module loggers and a global format:

```python
# main.py (root configuration)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

# Per-module logger
logger = logging.getLogger(__name__)    # e.g. "core.planner"
```

Verbose mode (`--verbose`) escalates to `DEBUG`:

```python
if verbose:
    logging.getLogger().setLevel(logging.DEBUG)
```

Agent classes add a user-facing prefix:

```python
class BaseAgent:
    def log(self, message: str):
        logger.info(f"[{self.name}] {message}")
        print(f"  [{self.name}] {message}")
```

### 7.2 Error Handling

**Retry decorator** for transient LLM failures (`providers/base.py`):

```python
@retry_on_error(max_retries=2, backoff=1.0)
def generate(self, prompt, ...):
    ...
```

Retries on:
- `ConnectionError`, `TimeoutError`, `OSError` — network failures
- Any exception with `"rate"`, `"429"`, or `"quota"` in message — rate limits

Backoff: exponential (`backoff * 2^attempt`), default 1s -> 2s -> 4s.

**Graceful degradation** at every integration point:

```python
# Orchestrator: optional pipeline cache
try:
    from advanced.cache import PipelineCache
    cache = PipelineCache(cache_dir)
except (ImportError, Exception):
    cache = None    # proceed without caching

# Orchestrator: optional CodeRAG
if self.config.get("enable_code_rag"):
    try:
        from advanced.code_rag import CodeRAG
        ...
    except (ImportError, Exception):
        logger.warning("CodeRAG not available")
```

**Auto-fix loops** in validation:

```python
# Classic mode: up to max_fix_iterations (default 2)
for i in range(max_fix_iterations):
    generated_files = validator.fix_issues(generated_files, report, paper_text)
    if not validator._last_fixed_paths:
        break    # no files changed, stop early
    report = validator.validate(generated_files, paper_text, extraction_dict)
    if report.passed:
        break
```

### 7.3 Configuration

`Q2RConfig` dataclass in `config.py` with `from_env()` factory:

```python
@dataclass
class Q2RConfig:
    # Provider defaults
    default_provider: str = "auto"
    default_model: str = ""

    # Pipeline toggles
    enable_validation: bool = True
    enable_test_generation: bool = True
    enable_backtest_validation: bool = True
    enable_caching: bool = True
    max_fix_iterations: int = 2

    # Generation settings
    code_temperature: float = 0.15
    analysis_temperature: float = 0.1
    max_code_tokens: int = 16384
    max_analysis_tokens: int = 8192

    # Backtest-specific settings
    default_start_date: str = "2000-01-01"
    default_end_date: str = "2023-12-31"
    default_initial_capital: float = 1_000_000.0
    default_transaction_cost_bps: float = 10.0
    default_data_source: str = "yfinance"
    backtest_metrics: list  # 12 metrics: sharpe, sortino, calmar, ...

    # Adaptive token limits
    def max_tokens_for_file(self, file_path: str) -> int:
        # model/signal files: 12288
        # backtest/portfolio: 10240
        # test files: 6144
        # config/utils: 4096
        # default: 8192

    @classmethod
    def from_env(cls) -> "Q2RConfig":
        # Reads Q2R_PROVIDER, Q2R_MODEL, Q2R_CACHE_DIR,
        # Q2R_VERBOSE, Q2R_DATA_SOURCE from environment
```

**Environment variables:**

| Variable          | Purpose                          | Default    |
|-------------------|----------------------------------|------------|
| `GEMINI_API_KEY`  | Gemini provider auth             | —          |
| `OPENAI_API_KEY`  | OpenAI provider auth             | —          |
| `ANTHROPIC_API_KEY`| Anthropic provider auth         | —          |
| `OLLAMA_HOST`     | Ollama server address            | `localhost:11434` |
| `Q2R_PROVIDER`    | Default provider override        | `"auto"`   |
| `Q2R_MODEL`       | Default model override           | `""`       |
| `Q2R_CACHE_DIR`   | Pipeline cache directory         | `.q2r_cache`|
| `Q2R_VERBOSE`     | Enable debug logging             | `false`    |
| `Q2R_DATA_SOURCE` | Default market data source       | `yfinance` |

### 7.4 Caching

Content-addressed caching (see [Section 6.7](#67-content-addressed-cache)):

```
Input PDF  -->  SHA-256  -->  first 16 hex chars  -->  cache key
                              e.g. "a3f8b2c1d4e5f6a7"

.q2r_cache/a3f8b2c1d4e5f6a7/
  extraction.pkl
  plan.pkl
  metadata.json
  files/
```

Cache lookup order in the orchestrator:
1. Hash input PDF
2. Check if `<cache_dir>/<hash>/extraction.pkl` exists
3. If hit: deserialize and skip extraction stage
4. If miss: run extraction, serialize result to cache

### 7.5 Prompt Management

**14 prompt templates** in the `prompts/` directory:

| Template File               | Used By                  | Stage | Focus Area                          |
|-----------------------------|--------------------------|-------|-------------------------------------|
| `strategy_extractor.txt`    | `StrategyExtractor`      | 2     | Signal/portfolio/universe extraction|
| `backtest_planner.txt`      | `DecomposedPlanner`      | 3a    | Overall backtest plan               |
| `architecture_design.txt`   | `DecomposedPlanner`      | 3b    | File structure and relationships    |
| `signal_logic.txt`          | `DecomposedPlanner`      | 3c    | Execution order, dependency graph   |
| `file_analysis.txt`         | `FileAnalyzer`           | 4     | Per-file detailed specifications    |
| `coder.txt`                 | `CodeSynthesizer`        | 5     | File-by-file code generation        |
| `test_generator.txt`        | `TestGenerator`          | 6     | Pytest test file generation         |
| `validator.txt`             | `CodeValidator`          | 7     | Code review and issue detection     |
| `backtest_validator.txt`    | `BacktestValidator`      | 8     | Bias detection prompts              |
| `auto_debug.txt`            | `AutoDebugger`           | 9     | Error analysis and fix generation   |
| `devops.txt`                | `DevOpsGenerator`        | 10    | Dockerfile/Makefile/CI templates    |
| `reference_eval.txt`        | `ReferenceEvaluator`     | 11    | Paper-vs-code evaluation            |
| `self_refine_verify.txt`    | `SelfRefiner`            | 3*    | Artifact critique / verification    |
| `self_refine_refine.txt`    | `SelfRefiner`            | 3*    | Artifact refinement iteration       |

All templates use `{{placeholder}}` syntax for variable injection.
Each module falls back to a hardcoded `_default_prompt()` method if the
template file is missing from disk.

---

## 8. Technology Stack

### 8.1 Runtime Requirements

| Component        | Version   | Purpose                                 |
|------------------|-----------|-----------------------------------------|
| Python           | 3.10+     | Runtime environment                     |
| `requests`       | any       | HTTP client for PDF download, GROBID    |
| `PyPDF2`         | any       | Fallback PDF text extraction            |
| `pyyaml`         | any       | Config serialization (optional)         |

### 8.2 Optional Dependencies (Engine)

| Component              | Version   | Purpose                              |
|------------------------|-----------|--------------------------------------|
| `PyMuPDF` (`fitz`)     | any       | Primary PDF parsing + image export   |
| `lxml`                 | any       | GROBID TEI-XML parsing               |
| `google-generativeai`  | any       | Gemini provider SDK                  |
| `openai`               | >=1.0     | OpenAI provider SDK                  |
| `anthropic`            | any       | Anthropic provider SDK               |

### 8.3 Execution Environment

| Component        | Purpose                                          |
|------------------|--------------------------------------------------|
| Docker Engine    | Sandboxed backtest execution (preferred)          |
| `subprocess`     | Local execution fallback                          |
| `concurrent.futures` | Parallel file generation (ThreadPoolExecutor) |

### 8.4 Generated Repository Dependencies

The generated backtest repositories typically require:

| Package          | Purpose (in generated code)                      |
|------------------|--------------------------------------------------|
| `pandas` >=2.0   | Data manipulation, time series handling           |
| `numpy` >=1.24   | Numerical computations, signal calculations       |
| `yfinance` >=0.2 | Market data acquisition                          |
| `matplotlib` >=3.7| Equity curves, drawdown charts, factor plots     |
| `scipy` >=1.10   | Statistical tests, optimization                  |

### 8.5 Development and Testing

| Tool             | Purpose                                          |
|------------------|--------------------------------------------------|
| `pytest`         | Test framework (generated test suites)           |
| `ruff` / `flake8`| Linting (in generated CI workflows)              |
| `black`          | Code formatting (in generated CI workflows)      |
| `make`           | Build automation (generated Makefile)             |

### 8.6 File Counts by Layer

```
Layer           Files  Total Lines (approx.)
-----------     -----  ---------------------
CLI              2     main.py (~260), gateway_adapter.py (~270)
Providers        6     base.py (~210), registry.py (~250),
                       gemini.py, openai_provider.py,
                       anthropic_provider.py, ollama.py
Core             7     paper_parser.py (~260), strategy_extractor.py (~260),
                       planner.py (~400), file_analyzer.py (~370),
                       coder.py (~410), validator.py (~410),
                       refiner.py (~380)
Advanced         8     backtest_validator.py (~450), executor.py (~300),
                       debugger.py (~420), evaluator.py (~390),
                       test_generator.py (~370), devops.py (~400),
                       code_rag.py (~590), context_manager.py (~560),
                       cache.py (~220)
Agents           2     base.py (~160), orchestrator.py (~510)
Quant            5     catalog.py (~330), signals.py, asset_classes.py,
                       metrics.py, data_sources.py
Prompts         14     .txt template files
Catalog          1     strategies.json (~660 lines, 47 strategies)
Tests            1     tests/test_quant2repo.py
-----------     -----
Total           ~46    ~7,500+ lines of Python
```

---

## Appendix A: Gateway Adapter Protocol

The `gateway_adapter.py` module implements the **Any2Repo Engine
Protocol v1.0**, enabling Quant2Repo to run as a managed engine behind
the Any2Repo-Gateway:

```
Any2Repo-Gateway                    Quant2Repo Engine
+------------------+                +------------------+
|                  |   JOB_ID env   |                  |
|  Job Scheduler   |  +----------> | gateway_adapter  |
|                  |   INPUT_URL    |  .is_gateway_    |
|                  |   OUTPUT_DIR   |   mode()         |
|                  |   MODE         |  .run_gateway_   |
|  Status Monitor  | <-----------+ |   job()          |
|                  |  status.json   |  .write_status_  |
|                  |  callback POST |   file()         |
+------------------+                +------------------+
```

Detection: `os.environ.get("JOB_ID")` is truthy -> gateway mode.

Status file: `.any2repo_status.json` written to `OUTPUT_DIR` with:
- `job_id`, `status` (running/completed/failed), `output_url`, `error`

---

## Appendix B: Configuration Constants

Signal type constants defined in `config.py`:

```
SIGNAL_MOMENTUM, SIGNAL_VALUE, SIGNAL_CARRY, SIGNAL_MEAN_REVERSION,
SIGNAL_VOLATILITY, SIGNAL_QUALITY, SIGNAL_SENTIMENT, SIGNAL_SEASONAL,
SIGNAL_TREND, SIGNAL_STATISTICAL_ARBITRAGE
```

Asset class constants:

```
ASSET_EQUITIES, ASSET_BONDS, ASSET_COMMODITIES, ASSET_CURRENCIES,
ASSET_CRYPTO, ASSET_REITS, ASSET_MULTI
```

Rebalancing frequency constants:

```
REBAL_DAILY, REBAL_WEEKLY, REBAL_MONTHLY, REBAL_QUARTERLY,
REBAL_SEMI_ANNUAL, REBAL_ANNUAL, REBAL_INTRADAY
```

---

## Appendix C: Backtest Validation Checks

The `BacktestValidator` (`advanced/backtest_validator.py`) performs both
static analysis and LLM-powered validation:

**Static checks (regex/AST-based):**

| Check                      | Severity  | What It Detects                              |
|----------------------------|-----------|----------------------------------------------|
| Look-Ahead Bias            | Critical  | Using future data (e.g. `shift(-1)`)         |
| Survivorship Bias          | Critical  | No universe filtering for delisted securities|
| Data Snooping              | Warning   | Optimizing parameters on in-sample data      |
| Transaction Cost Omission  | Warning   | No transaction costs in P&L calculation      |
| Hardcoded Parameters       | Info      | Magic numbers instead of config variables    |
| Missing Risk Management    | Warning   | No position sizing or stop-loss logic        |

**`BacktestValidationReport` fields:**

```
checks: list[BiasCheck]         # individual check results
bias_risk_score: int            # 0 (safe) to 100 (extreme risk)
recommendations: list[str]     # actionable improvement suggestions
passed: bool                    # True if no critical failures
critical_count: int             # property: count of critical failures
warning_count: int              # property: count of warnings
info_count: int                 # property: count of info items
```

---

## Appendix D: CLI Argument Reference

```
python main.py [OPTIONS]

Input Sources (mutually exclusive):
  --pdf_url URL           Paper URL (SSRN, arXiv, NBER, direct PDF)
  --pdf_path PATH         Local PDF file path
  --catalog ID            Strategy ID from the built-in catalog

Mode:
  --mode {classic,agent}  Pipeline mode (default: classic)

Provider:
  --provider NAME         LLM provider (gemini, openai, anthropic, ollama)
  --model NAME            Override default model for the provider

Feature Flags (agent mode):
  --refine                Enable self-refinement loops on plans
  --execute               Run generated backtest in sandbox
  --evaluate              Score output against paper (1-5 scale)
  --interactive           Enable interactive prompts during pipeline

Toggles:
  --no-tests              Skip test generation
  --no-devops             Skip DevOps file generation
  --no-context-manager    Disable clean-slate context management
  --code-rag              Enable GitHub reference code mining
  --skip-validation       Skip code validation stage (classic mode)

Limits:
  --max-refine N          Max refinement iterations (default: 2)
  --max-debug N           Max debug iterations (default: 3)
  --max-fix N             Max validation fix iterations (default: 2)

Output:
  --output_dir DIR        Output directory (default: ./generated_repo)
  --reference-dir DIR     Reference implementation for evaluation

Catalog Commands:
  --list-catalog          List all 47 strategies in the catalog
  --search-catalog QUERY  Search catalog by keyword

Utility:
  --list-providers        Show available providers and models
  --verbose               Enable debug-level logging
```
