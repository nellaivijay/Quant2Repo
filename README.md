# Quant2Repo

**Educational agentic framework for converting quantitative finance research into backtesting repositories**

Quant2Repo is an open source educational tool designed to help students and researchers understand how to convert quantitative finance research papers into production-ready backtesting repositories. It demonstrates domain-specific applications of agentic AI systems in financial contexts.

## Educational Purpose

This tool serves educational purposes by helping students and researchers:
- Learn about quantitative finance research implementation
- Understand trading strategy extraction from academic papers
- Practice backtesting and strategy validation techniques
- Study financial data sources and API integration
- Explore bias detection and validation in financial systems
- Gain hands-on experience with algorithmic trading concepts

## Key Features

- **Strategy Extraction**: LLM-powered extraction of signals, portfolio rules, and rebalancing logic
- **Decomposed Planning**: Four-stage planning for financial system architecture
- **Backtest Validation**: Automatic detection of look-ahead bias, survivorship bias, and data snooping
- **Strategy Catalog**: Pre-indexed trading strategies from systematic trading research
- **Self-Refine Loops**: Verify and refine financial models at each pipeline stage
- **Execution Sandbox**: Docker/local sandbox for running backtests safely
- **Auto-Debug**: Iterative error analysis and fixing for financial code
- **Multi-Model Support**: Integration with multiple LLM providers

## Advanced Features

### Domain-Specific Validation
Financial-specific validation including:
- Look-ahead bias detection
- Survivorship bias detection
- Data snooping prevention
- Signal fidelity verification
- Financial metrics calculation (Sharpe, drawdown, turnover)

### Strategy Catalog
Built-in catalog of systematic trading strategies covering:
- Equities (30 strategies)
- Commodities (5 strategies)
- Currencies (4 strategies)
- Crypto (2 strategies)
- Multi-asset (5 strategies)
- REITs (1 strategy)

### Financial Data Integration
Integration with financial data sources:
- yfinance for market data
- FRED for economic indicators
- Custom data source registry

### Quant-Specific Metrics
Financial performance metrics:
- Sharpe ratio calculation
- Drawdown analysis
- Turnover measurement
- T-statistic evaluation
- Factor analysis

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/nellaivijay/Quant2Repo.git
cd Quant2Repo

# Install dependencies
pip install -r requirements.txt
```

### Provider Setup

```bash
# Google Gemini (recommended)
export GEMINI_API_KEY="your_key_here"

# OpenAI GPT-4o
export OPENAI_API_KEY="your_key_here"
pip install openai

# Anthropic Claude
export ANTHROPIC_API_KEY="your_key_here"
pip install anthropic

# Ollama (local models)
ollama pull deepseek-coder-v2
```

### Basic Usage

```bash
# From research paper URL
python main.py --pdf_url "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975"

# From local PDF file
python main.py --pdf_path ./papers/momentum.pdf

# Agent mode with decomposed planning
python main.py --pdf_url "..." --mode agent

# Agent mode with self-refine loops
python main.py --pdf_url "..." --mode agent --refine

# Agent mode with execution sandbox
python main.py --pdf_url "..." --mode agent --execute

# From strategy catalog
python main.py --catalog time-series-momentum

# List all strategies
python main.py --list-catalog
```

## Architecture

### Classic Mode
```
PDF → [Paper Parser] → [Strategy Extractor] → [Planner] → [Coder] → [Validator] → Repository
```

### Agent Mode
```
PDF → [Paper Parser] → [Strategy Extractor] → [Decomposed Planner] → [Per-File Analyzer]
  → [CodeRAG] → [Context-Managed Coder] → [Test Generator] → [Code Validator]
  → [Backtest Validator] → [Execution Sandbox] → [Auto-Debugger] → [DevOps Generator]
  → [Reference Evaluator] → Repository
```

## Pipeline Stages

1. **PaperParser**: Multi-backend PDF parsing for financial papers
2. **StrategyExtractor**: Extract signals, portfolio rules, equations, parameters
3. **DecomposedPlanner**: 4-stage planning (overall → architecture → signal logic → config)
4. **FileAnalyzer**: Per-file deep analysis with accumulated context
5. **CodeRAG**: Mine GitHub for reference backtest implementations
6. **CodeSynthesizer**: File-by-file code generation with context management
7. **TestGenerator**: Auto-generated pytest suite for backtesting
8. **CodeValidator**: Self-review and iterative auto-fix
9. **BacktestValidator**: Bias detection and validation
10. **ExecutionSandbox**: Run backtest in sandbox environment
11. **AutoDebugger**: Iterative error fixing
12. **DevOpsGenerator**: Generate Dockerfile, Makefile, CI
13. **ReferenceEvaluator**: Score against paper-reported results

## Strategy Catalog

Built-in catalog covering multiple asset classes:
- **Equities**: 30 strategies
- **Commodities**: 5 strategies
- **Currencies**: 4 strategies
- **Crypto**: 2 strategies
- **Multi-Asset**: 5 strategies
- **REITs**: 1 strategy

## Project Structure

```
Quant2Repo/
├── main.py                    # CLI entry point
├── config.py                  # Global configuration
├── providers/                 # Multi-model abstraction
├── core/                      # Pipeline stages
│   ├── paper_parser.py
│   ├── strategy_extractor.py
│   ├── planner.py
│   ├── file_analyzer.py
│   ├── coder.py
│   └── validator.py
├── quant/                     # Quant-specific modules
│   ├── catalog.py
│   ├── signals.py
│   ├── asset_classes.py
│   ├── metrics.py
│   └── data_sources.py
├── advanced/                  # Advanced capabilities
│   ├── backtest_validator.py
│   ├── cache.py
│   ├── executor.py
│   ├── debugger.py
│   ├── evaluator.py
│   ├── devops.py
│   ├── test_generator.py
│   ├── code_rag.py
│   └── context_manager.py
├── agents/                    # Multi-agent orchestration
├── prompts/                   # Quant-specific prompts
├── catalog/                   # Strategy catalog data
└── tests/                     # Test suite
```

## Development

### Adding New Strategies

Add new strategies to the strategy catalog following existing patterns.

### Testing

Run the test suite:
```bash
pytest tests/
```

## License

Apache 2.0 License - See LICENSE file for details.

## Educational Use

This tool is provided for educational purposes to help students and researchers learn about:
- Quantitative finance research implementation
- Trading strategy extraction and validation
- Financial backtesting and bias detection
- Algorithmic trading concepts and metrics
- Domain-specific applications of agentic AI systems