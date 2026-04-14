# Quant2Repo v1.0

**Multi-model agentic framework that converts quantitative finance research papers into production-ready backtesting repositories.**

Inspired by [Research2Repo](https://github.com/nellaivijay/Research2Repo) and the [awesome-systematic-trading](https://github.com/paperswithbacktest/awesome-systematic-trading) catalog. Implements decomposed planning, per-file analysis, self-refine loops, execution sandbox, and backtest-specific validation on top of a multi-model provider system.

Supports **Google Gemini**, **OpenAI GPT-4o/o3**, **Anthropic Claude**, and **Ollama** (local models).

## What Makes This Different from Research2Repo?

| Feature | Research2Repo (ML) | Quant2Repo (Finance) |
|---------|-------------------|---------------------|
| **Input** | ML/DL papers | Quant/finance papers (SSRN, NBER, journals) |
| **Output** | Training/inference repos | Backtesting repos with data, signals, portfolios |
| **Strategy Extraction** | Architecture + equations | Signals, rebalancing rules, portfolio formation |
| **Validation** | Equation fidelity | Look-ahead bias, survivorship bias, signal fidelity |
| **Catalog** | N/A | 47 strategies from awesome-systematic-trading |
| **Domain Knowledge** | PyTorch/TF conventions | pandas/numpy, yfinance/FRED, quant conventions |
| **Metrics** | Accuracy, loss | Sharpe, drawdown, turnover, t-statistic |

## Features

### Core Pipeline
| Feature | Description |
|---------|-------------|
| **Strategy Extraction** | LLM-powered extraction of signals, portfolio rules, rebalancing logic from papers |
| **Decomposed Planning** | 4-stage: overall plan -> architecture design (UML) -> signal logic -> config generation |
| **Per-File Analysis** | Deep per-file specification before code generation |
| **Self-Refine Loops** | Verify/refine cycles at every pipeline stage |
| **Execution Sandbox** | Docker/local sandbox to run generated backtests |
| **Auto-Debug** | Iterative error analysis + fix (19+ Python error types) |
| **Backtest Validation** | Checks for look-ahead bias, survivorship bias, data snooping, etc. |
| **Strategy Catalog** | 47 pre-indexed strategies from awesome-systematic-trading |

### Advanced Features
| Feature | Description |
|---------|-------------|
| **CodeRAG** | Mine GitHub for reference backtest implementations |
| **Context Manager** | Clean-slate context with cumulative code summaries |
| **DevOps Generation** | Dockerfile, docker-compose, Makefile, GitHub Actions CI |
| **Reference Evaluation** | Score generated backtest against paper-reported results |
| **Multi-Model** | Gemini, OpenAI, Anthropic Claude, Ollama (local) |

## Architecture

### Classic Mode

```
PDF --> [Paper Parser] --> [Strategy Extractor] --> [Planner] --> [Coder] --> [Validator] --> Repo
           |                     |                     |             |            |
      Multi-backend         Signal/Portfolio       4-stage       Rolling      Bias checks
      (GROBID/PyMuPDF)      extraction            decomposed    context      + auto-fix
```

### Agent Mode

```
PDF --> [Paper Parser] --> [Strategy Extractor] --> [Decomposed Planner]
           |                     |                        |
      Multi-backend         Signals, portfolio       4-stage planning
      PDF parsing           rules, equations         + UML diagrams
                                                          |
                                                   [Self-Refine]
                                                          |
                                                   [Per-File Analyzer]
                                                          |
                                                   [CodeRAG (opt)]
                                                          |
                                                   [Context-Managed Coder]
                                                          |
                                                   [Test Generator]
                                                          |
                                                   [Code Validator]
                                                          |
                                                   [Backtest Validator]  <-- bias checks
                                                          |
                                                   [Execution Sandbox]
                                                          |
                                                   [Auto-Debugger]
                                                          |
                                                   [DevOps Generator]
                                                          |
                                                   [Reference Evaluator]
                                                          |
                                                       Repository
```

### Pipeline Stages

| Stage | Module | What It Does |
|-------|--------|-------------|
| 1 | `PaperParser` | Multi-backend PDF parsing (GROBID, PyMuPDF, PyPDF2) |
| 2 | `StrategyExtractor` | Extract signals, portfolio rules, equations, parameters |
| 3 | `DecomposedPlanner` | 4-stage: overall -> architecture (UML) -> signal logic -> config |
| 4 | `FileAnalyzer` | Per-file deep analysis with accumulated context |
| 4b | `CodeRAG` | Mine GitHub for reference backtests (optional) |
| 5 | `CodeSynthesizer` + `ContextManager` | File-by-file generation with clean-slate context |
| 6 | `TestGenerator` | Auto-generated pytest suite for backtest validation |
| 7 | `CodeValidator` | Self-review + iterative auto-fix loop |
| 8 | `BacktestValidator` | Check for look-ahead bias, survivorship bias, data snooping |
| 9 | `ExecutionSandbox` + `AutoDebugger` | Run backtest in sandbox, auto-debug failures |
| 10 | `DevOpsGenerator` | Generate Dockerfile, Makefile, CI, setup.py |
| 11 | `ReferenceEvaluator` | Score against paper-reported results (1-5 scale) |
| 12 | Save | Write all files + metadata to output directory |

## Strategy Catalog

Built-in catalog of **47 strategies** from [awesome-systematic-trading](https://github.com/paperswithbacktest/awesome-systematic-trading), covering:

| Asset Class | Strategies | Top Sharpe |
|------------|-----------|-----------|
| Equities | 30 | 0.835 (Asset Growth Effect) |
| Commodities | 5 | 0.482 (Skewness Effect) |
| Currencies | 4 | 0.254 (FX Carry Trade) |
| Crypto | 2 | 0.892 (Overnight Seasonality in Bitcoin) |
| Multi-Asset | 5 | 0.691 (Paired Switching) |
| REITs | 1 | 0.155 (Value and Momentum) |

```bash
# List all strategies
python main.py --list-catalog

# Search strategies
python main.py --search-catalog "momentum"

# Generate from catalog entry
python main.py --catalog time-series-momentum --mode agent
```

## Installation

```bash
git clone https://github.com/nellaivijay/Quant2Repo.git
cd Quant2Repo
pip install -r requirements.txt
```

### Provider Setup (pick one or more)

```bash
# Google Gemini (recommended — 2M token context + vision)
export GEMINI_API_KEY="your_key_here"

# OpenAI GPT-4o
export OPENAI_API_KEY="your_key_here"
pip install openai

# Anthropic Claude
export ANTHROPIC_API_KEY="your_key_here"
pip install anthropic

# Ollama (local, free)
# Install from https://ollama.ai, then:
ollama pull deepseek-coder-v2
```

### Install all providers at once

```bash
pip install -e ".[all]"
```

## Usage

### Classic Mode

```bash
# From SSRN paper URL
python main.py --pdf_url "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975"

# From local PDF
python main.py --pdf_path ./papers/momentum.pdf

# Specific provider
python main.py --pdf_url "..." --provider gemini --model gemini-2.5-pro

# Skip validation (fast run)
python main.py --pdf_url "..." --skip-validation --skip-tests
```

### Agent Mode

```bash
# Basic agent mode with decomposed planning
python main.py --pdf_url "..." --mode agent

# With self-refine loops
python main.py --pdf_url "..." --mode agent --refine

# With execution sandbox + auto-debug
python main.py --pdf_url "..." --mode agent --execute

# Full pipeline with all features
python main.py --pdf_url "..." --mode agent --refine --execute --evaluate

# With CodeRAG (mine GitHub for reference code)
python main.py --pdf_url "..." --mode agent --code-rag

# Interactive mode (pause after planning)
python main.py --pdf_url "..." --mode agent --interactive
```

### From Strategy Catalog

```bash
# Generate backtest from catalog
python main.py --catalog time-series-momentum

# With agent mode
python main.py --catalog asset-growth-effect --mode agent --refine --execute

# List all strategies
python main.py --list-catalog

# Search
python main.py --search-catalog "value"
```

## Generated Repository Structure

Quant2Repo generates a complete backtesting repository:

```
generated_repo/
  config.py              # Strategy parameters, asset universe, date ranges
  data_loader.py         # Data fetching (yfinance/FRED) and preprocessing
  signals.py             # Signal generation (momentum, value, etc.)
  portfolio.py           # Portfolio construction and rebalancing
  analysis.py            # Performance metrics and factor analysis
  visualization.py       # Charts and report generation
  main.py                # CLI orchestrator
  requirements.txt       # Dependencies
  README.md              # Auto-generated documentation
  tests/                 # pytest test suite
    test_signals.py
    test_portfolio.py
    conftest.py
  Dockerfile             # Docker support
  Makefile               # Build targets
  .github/workflows/     # CI pipeline
  q2r_metadata.json      # Generation metadata
```

## Project Structure

```
Quant2Repo/
  main.py                          # CLI entry point: classic + agent modes
  config.py                        # Global configuration

  providers/                       # Multi-model abstraction layer
    base.py                        # BaseProvider ABC + ModelCapability enum
    gemini.py                      # Google Gemini provider
    openai_provider.py             # OpenAI GPT provider
    anthropic_provider.py          # Anthropic Claude provider
    ollama.py                      # Local Ollama provider
    registry.py                    # Auto-detection + factory

  core/                            # Pipeline stages
    paper_parser.py                # Multi-backend PDF parsing
    strategy_extractor.py          # Trading strategy extraction (quant-specific)
    planner.py                     # Decomposed 4-stage planning
    file_analyzer.py               # Per-file deep analysis
    coder.py                       # File-by-file code generation
    validator.py                   # Code validation + auto-fix
    refiner.py                     # Self-refine verify/refine loops

  quant/                           # Quant domain modules
    catalog.py                     # Strategy catalog (47 strategies)
    signals.py                     # Signal type definitions
    asset_classes.py               # Asset class definitions + universes
    metrics.py                     # Performance metric specifications
    data_sources.py                # Data source registry

  advanced/                        # Advanced capabilities
    backtest_validator.py          # Backtest bias detection
    cache.py                       # Content-addressed pipeline cache
    executor.py                    # Execution sandbox (Docker/local)
    debugger.py                    # Auto-debugger (iterative fixing)
    evaluator.py                   # Reference evaluation (1-5 scoring)
    devops.py                      # DevOps file generation
    test_generator.py              # Pytest suite generation
    code_rag.py                    # GitHub reference mining
    context_manager.py             # Clean-slate context management

  agents/                          # Multi-agent orchestration
    base.py                        # BaseAgent ABC + specialized agents
    orchestrator.py                # 11-stage pipeline controller

  prompts/                         # 14 quant-specific prompt templates
    strategy_extractor.txt         # Strategy extraction
    backtest_planner.txt           # Overall planning
    architecture_design.txt        # Repo structure design
    signal_logic.txt               # Signal logic specifications
    coder.txt                      # Code generation
    validator.txt                  # Code validation
    backtest_validator.txt         # Bias detection
    file_analysis.txt              # Per-file analysis
    self_refine_verify.txt         # Self-refine verification
    self_refine_refine.txt         # Self-refine refinement
    auto_debug.txt                 # Auto-debugging
    devops.txt                     # DevOps generation
    test_generator.txt             # Test generation
    reference_eval.txt             # Reference evaluation

  catalog/                         # Strategy catalog data
    strategies.json                # 47 strategies from awesome-systematic-trading

  tests/                           # Project tests
    test_quant2repo.py
```

## Supported Models

| Provider | Models | Context | Vision | Cost |
|----------|--------|---------|--------|------|
| **Gemini** | 2.5 Pro, 2.0 Flash, 1.5 Pro | 1M-2M | Yes | $0.0001-$0.01/1K |
| **OpenAI** | GPT-4o, GPT-4-turbo, o3, o1 | 128K-200K | Yes | $0.0025-$0.06/1K |
| **Anthropic** | Claude Sonnet 4, Opus 4, 3.5 Sonnet | 200K | Yes | $0.003-$0.075/1K |
| **Ollama** | DeepSeek, Llama 3.1, CodeLlama, Mistral | 4K-128K | Partial | Free |

## CLI Reference

```
python main.py [OPTIONS]

Required (one of):
  --pdf_url URL              URL of the research paper PDF
  --pdf_path PATH            Path to a local PDF file
  --catalog ID               Strategy ID from built-in catalog

Mode:
  --mode MODE                classic (default) | agent

Provider:
  --provider NAME            gemini | openai | anthropic | ollama
  --model NAME               Specific model name

Classic Pipeline Options:
  --output_dir DIR           Output directory (default: ./generated_repo)
  --skip-validation          Skip validation pass
  --skip-tests               Skip test generation
  --max-fix-iterations N     Max auto-fix attempts (default: 2)

Agent Pipeline Options (--mode agent):
  --refine                   Enable self-refine loops at each stage
  --execute                  Enable execution sandbox + auto-debug
  --evaluate                 Enable reference-based evaluation
  --interactive              Pause after planning for user review
  --no-tests                 Disable test generation
  --no-devops                Disable DevOps file generation
  --code-rag                 Enable CodeRAG: mine GitHub for reference code
  --no-context-manager       Disable context manager
  --reference-dir DIR        Reference implementation for evaluation
  --max-refine-iterations N  Max self-refine iterations (default: 2)
  --max-debug-iterations N   Max auto-debug iterations (default: 3)

Catalog Commands:
  --list-catalog             List all 47 strategies in the catalog
  --search-catalog QUERY     Search strategies by keyword

Misc:
  --list-providers           Show available providers and models
  --verbose, -v              Verbose output
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GEMINI_API_KEY` | Google Gemini API key | For Gemini provider |
| `OPENAI_API_KEY` | OpenAI API key | For OpenAI provider |
| `ANTHROPIC_API_KEY` | Anthropic API key | For Anthropic provider |
| `OLLAMA_HOST` | Ollama server URL (default: localhost:11434) | For Ollama |
| `Q2R_PROVIDER` | Default provider override | No |
| `Q2R_MODEL` | Default model override | No |
| `Q2R_DATA_SOURCE` | Default data source (default: yfinance) | No |
| `Q2R_CACHE_DIR` | Custom cache directory | No |

## Backtest Validation Checks

Quant2Repo validates generated backtests for common pitfalls:

| Check | Severity | What It Catches |
|-------|----------|----------------|
| Look-ahead bias | Critical | Signals using future data |
| Survivorship bias | Critical | Universe not accounting for delistings |
| Rebalancing timing | Critical | Signal and trade on same date |
| Point-in-time data | Warning | Using revised data instead of as-reported |
| Transaction costs | Warning | Hardcoded or missing costs |
| Data snooping | Warning | Excessive parameter tuning |
| Capacity constraints | Info | Strategy may not scale |
| Sample period sensitivity | Info | Results depend on specific dates |

## Comparison with Research2Repo

| Feature | Research2Repo v3.1 | Quant2Repo v1.0 |
|---------|-------------------|-----------------|
| Domain | ML/DL papers | Quant/finance papers |
| Strategy extraction | N/A | Signal, portfolio, rebalancing rules |
| Planning | 4-stage (ML-focused) | 4-stage (backtest-focused) |
| Bias detection | N/A | Look-ahead, survivorship, data snooping |
| Strategy catalog | N/A | 47 strategies from awesome-systematic-trading |
| CodeRAG | GitHub ML repos | GitHub backtest repos |
| Execution sandbox | Docker + local | Docker + local |
| Auto-debug | 19+ error types | 19+ error types + quant-specific |
| Multi-model | 4 providers | 4 providers (same abstraction) |
| Self-refine | All stages | All stages |
| DevOps | Dockerfile, CI | Dockerfile, CI, Makefile |

## Any2Repo Engine Protocol

Quant2Repo implements the [Any2Repo Engine Protocol v1.0](https://github.com/nellaivijay/Any2Repo-Gateway/blob/main/docs/engine_protocol.md), enabling seamless integration with the Any2Repo-Gateway control plane.

### Engine Manifest

```json
{
  "engine_id": "quant2repo",
  "version": "2.0.0",
  "display_name": "Quant2Repo",
  "description": "Convert quantitative finance papers into trading strategy repositories",
  "protocol_version": "1.0",
  "capabilities": ["pdf_input", "text_input", "catalog_input", "github_output", "local_output", "streaming_logs", "incremental_validation"],
  "accepted_inputs": ["pdf_url", "pdf_base64", "paper_text", "catalog_id"],
  "container_image": "any2repo/quant2repo:latest",
  "supported_backends": ["gcp_vertex", "aws_bedrock", "azure_ml", "on_prem"],
  "cpu_request": "4",
  "memory_request": "16Gi",
  "timeout_seconds": 3600
}
```

### Gateway Integration

Quant2Repo can be deployed as a managed engine behind the [Any2Repo-Gateway](https://github.com/nellaivijay/Any2Repo-Gateway):

- **GCP Vertex AI**: Runs as a Vertex AI custom job
- **AWS Bedrock**: Runs via Lambda async invocation
- **Azure ML**: Runs as an Azure ML command job
- **On-Premise**: Runs as a Docker container or HTTP service

See the [Gateway documentation](https://github.com/nellaivijay/Any2Repo-Gateway) for deployment instructions.

## License

Apache 2.0

## Credits

- Strategy catalog from [awesome-systematic-trading](https://github.com/paperswithbacktest/awesome-systematic-trading)
- Architecture inspired by [Research2Repo](https://github.com/nellaivijay/Research2Repo) and [PaperCoder](https://arxiv.org/abs/2407.01503)
