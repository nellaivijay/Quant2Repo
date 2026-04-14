# Quant2Repo Wiki

**Multi-model agentic framework that converts quantitative finance research papers into production-ready backtesting repositories.**

Version 1.0 | Inspired by [Research2Repo](https://github.com/nellaivijay/Research2Repo) and [awesome-systematic-trading](https://github.com/paperswithbacktest/awesome-systematic-trading) | Apache 2.0 License

---

## Quick Navigation

### Core Documentation
| Document | Description |
|----------|-------------|
| [Architecture Overview](Architecture-Overview) | System architecture, component interactions, design philosophy |
| [Usage Guide](Usage-Guide) | Installation, CLI reference, examples for both classic and agent modes |
| [Provider System & Configuration](Provider-System-and-Configuration) | Multi-model provider setup, auto-detection, capability routing |
| [Pipeline Stages Deep Dive](Pipeline-Stages-Deep-Dive) | Detailed walkthrough of all 11 stages in both modes |

### Operations
| Document | Description |
|----------|-------------|
| [Gateway Integration](Gateway-Integration) | Dual-mode architecture, Any2Repo-Gateway protocol, worked examples |
| [Deployment & DevOps](Deployment-and-DevOps) | Docker, CI/CD, production considerations |

---

## Project Overview

Quant2Repo automates the conversion of quantitative finance research papers (PDFs) into fully functional backtesting repositories. Given a paper URL, the system:

1. **Parses** the paper using long-context LLMs (up to 2M tokens with Gemini)
2. **Extracts Strategy** signals, rebalancing rules, portfolio formation logic, and universe definitions
3. **Plans** the repository structure through decomposed multi-stage planning
4. **Analyzes** each file specification before code generation
5. **Generates** production-quality backtesting code with rolling dependency context
6. **Validates** output against look-ahead bias, survivorship bias, and signal fidelity
7. **Executes** generated code in a sandbox and **auto-debugs** failures

### Dual Pipeline Modes

| Mode | Description | Best For |
|------|-------------|----------|
| **Classic** (`--mode classic`) | Linear pipeline, streamlined generation | Fast generation, simple strategies |
| **Agent** (`--mode agent`) | Enhanced pipeline with decomposed planning, self-refine, execution | Complex papers, production quality |

### What Makes This Different from Research2Repo

| Feature | Research2Repo (ML) | Quant2Repo (Finance) |
|---------|-------------------|---------------------|
| **Input** | ML/DL papers | Quant/finance papers |
| **Output** | Training/inference repos | Backtesting repos |
| **Strategy Extraction** | Architecture + equations | Signals, rebalancing rules, portfolio formation |
| **Validation** | Equation fidelity | Look-ahead bias, survivorship bias, signal fidelity |
| **Catalog** | N/A | 47 strategies from awesome-systematic-trading |
| **Domain Knowledge** | PyTorch/TF | pandas/numpy, yfinance/FRED |
| **Metrics** | Accuracy, loss | Sharpe, drawdown, turnover, t-statistic |

### Supported Providers

| Provider | Models | Context Window | Vision | Cost |
|----------|--------|---------------|--------|------|
| **Google Gemini** | 2.5 Pro, 2.0 Flash, 1.5 Pro | 1M-2M tokens | Yes | $0.0001-$0.01/1K |
| **OpenAI** | GPT-4o, GPT-4-turbo, o3, o1 | 128K-200K tokens | Yes | $0.0025-$0.06/1K |
| **Anthropic** | Claude Sonnet 4, Opus 4, 3.5 Sonnet | 200K tokens | Yes | $0.003-$0.075/1K |
| **Ollama** | DeepSeek, Llama 3.1, CodeLlama, Mistral | 4K-128K tokens | Partial | Free (local) |

---

## Strategy Catalog

Quant2Repo ships with a curated catalog of **47 strategies** spanning **6 asset classes**, sourced from [awesome-systematic-trading](https://github.com/paperswithbacktest/awesome-systematic-trading):

| Asset Class | Strategies |
|-------------|-----------|
| **Equities** | 30 |
| **Commodities** | 5 |
| **Currencies** | 4 |
| **Crypto** | 2 |
| **Multi-Asset** | 5 |
| **REITs** | 1 |

---

### Key Metrics

| Metric | Value |
|--------|-------|
| Python files | 31 |
| Total Python lines | ~8,500 |
| Prompt templates | 14 |
| Pipeline stages (agent mode) | 11 |
| Supported LLM providers | 4 |
| Bias checks | 8 |
| Strategy catalog | 47 strategies |
| Error types auto-debugged | 19+ |

---

## Getting Started

```bash
# Clone and install
git clone https://github.com/nellaivijay/Quant2Repo.git
cd Quant2Repo
pip install -r requirements.txt

# Set up a provider
export GEMINI_API_KEY="your_key_here"

# Run (classic mode)
python main.py --pdf_url "https://arxiv.org/pdf/YOUR_PAPER.pdf" --mode classic

# Run (agent mode with all features)
python main.py --pdf_url "https://arxiv.org/pdf/YOUR_PAPER.pdf" \
  --mode agent --refine --execute
```

See the [Usage Guide](Usage-Guide) for complete instructions.
