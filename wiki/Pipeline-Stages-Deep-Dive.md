# Pipeline Stages Deep Dive

> **Quant2Repo Wiki** | _Comprehensive walkthrough of every pipeline stage in Classic and Agent modes_

---

## Table of Contents

1. [Pipeline Overview](#1-pipeline-overview)
2. [Classic Mode Pipeline (6 Stages)](#2-classic-mode-pipeline-6-stages)
   - [Stage 1: Paper Parsing](#stage-1-paper-parsing)
   - [Stage 2: Strategy Extraction](#stage-2-strategy-extraction)
   - [Stage 3: Planning](#stage-3-planning)
   - [Stage 4: Code Generation](#stage-4-code-generation)
   - [Stage 5: Validation + Auto-Fix](#stage-5-validation--auto-fix)
   - [Stage 6: Save](#stage-6-save)
3. [Agent Mode Pipeline (11 Stages)](#3-agent-mode-pipeline-11-stages)
   - [Stage 3a: Decomposed Planning + Self-Refine](#stage-3a-decomposed-planning--self-refine)
   - [Stage 4a: Per-File Analysis + CodeRAG (parallel)](#stage-4a-per-file-analysis--coderag-parallel)
   - [Stage 5a: Code Generation + Context Manager](#stage-5a-code-generation--context-manager)
   - [Stage 6a: Test Generation](#stage-6a-test-generation)
   - [Stage 7a: Validation + Auto-Fix](#stage-7a-validation--auto-fix)
   - [Stage 8a: Backtest Validation (Bias Checks)](#stage-8a-backtest-validation-bias-checks)
   - [Stage 9a: Execution Sandbox + Auto-Debug](#stage-9a-execution-sandbox--auto-debug)
   - [Stage 10a: DevOps Generation](#stage-10a-devops-generation)
   - [Stage 11a: Reference Evaluation](#stage-11a-reference-evaluation)
4. [Self-Refine Mechanism](#4-self-refine-mechanism)
5. [Strategy Catalog Integration](#5-strategy-catalog-integration)
6. [Pipeline Comparison Summary](#6-pipeline-comparison-summary)

---

## 1. Pipeline Overview

Quant2Repo provides **two pipeline modes** that share the same first two stages
but diverge significantly after strategy extraction. Classic mode targets fast,
lightweight generation; Agent mode adds iterative refinement, bias checking,
execution, and evaluation.

### High-Level Flow

```
                          +------------------+
                          |  PDF / arXiv URL |
                          +--------+---------+
                                   |
                          +--------v---------+
                          | 1. Paper Parsing  |  <-- shared
                          +--------+---------+
                                   |
                          +--------v---------+
                          | 2. Strategy       |  <-- shared
                          |    Extraction     |
                          +--------+---------+
                                   |
                    +--------------+--------------+
                    |                             |
             Classic Mode                   Agent Mode
                    |                             |
          +---------v----------+     +------------v-------------+
          | 3. Planning        |     | 3. Planning + Self-Refine|
          +---------+----------+     +------------+-------------+
                    |                             |
          +---------v----------+     +------------v-------------+
          | 4. Code Generation |     | 4. File Analysis + RAG   |
          +---------+----------+     +------------+-------------+
                    |                             |
          +---------v----------+     +------------v-------------+
          | 5. Validation      |     | 5. CodeGen + ContextMgr  |
          |    + Auto-Fix      |     +------------+-------------+
          +---------+----------+                  |
                    |                +------------v-------------+
          +---------v----------+     | 6. Test Generation       |
          | 6. Save            |     +------------+-------------+
          +--------------------+                  |
                                     +------------v-------------+
                                     | 7. Validation + Auto-Fix |
                                     +------------+-------------+
                                                  |
                                     +------------v-------------+
                                     | 8. Backtest Validation   |
                                     |    (Bias Checks)         |
                                     +------------+-------------+
                                                  |
                                     +------------v-------------+
                                     | 9. Execution Sandbox     |
                                     |    + Auto-Debug          |
                                     +------------+-------------+
                                                  |
                                     +------------v-------------+
                                     | 10. DevOps Generation    |
                                     +------------+-------------+
                                                  |
                                     +------------v-------------+
                                     | 11. Reference Evaluation |
                                     +------------+-------------+
                                                  |
                                     +------------v-------------+
                                     | 12. Save                 |
                                     +----------------------------+
```

### Pipeline Comparison Table

| Stage | Classic Mode              | Agent Mode                                   |
|-------|---------------------------|----------------------------------------------|
| 1     | Paper Parsing             | Paper Parsing                                |
| 2     | Strategy Extraction       | Strategy Extraction                          |
| 3     | Planning (basic)          | Decomposed Planning + Self-Refine            |
| 4     | ---                       | Per-File Analysis + CodeRAG (parallel)       |
| 5     | Code Generation           | Code Generation + Context Manager            |
| 6     | Validation + Auto-Fix     | Test Generation                              |
| 7     | Save                      | Validation + Auto-Fix                        |
| 8     | ---                       | Backtest Validation (bias checks)            |
| 9     | ---                       | Execution Sandbox + Auto-Debug               |
| 10    | ---                       | DevOps Generation                            |
| 11    | ---                       | Reference Evaluation                         |
| 12    | ---                       | Save                                         |

> **Key difference:** Classic mode runs 6 stages in a single forward pass.
> Agent mode runs 12 stages with iterative refinement loops at planning (Stage 3),
> code validation (Stage 7), and execution (Stage 9).

---

## 2. Classic Mode Pipeline (6 Stages)

Classic mode is the default pipeline. It performs a single forward pass from PDF
to generated repository with one optional auto-fix cycle. No Docker execution,
no bias analysis, no test generation.

```
  PDF ──> Parse ──> Extract ──> Plan ──> Generate ──> Validate ──> Save
   1        2          3          4          5            6
```

---

### Stage 1: Paper Parsing

| Property       | Value                                    |
|----------------|------------------------------------------|
| **Module**     | `PaperParser`                            |
| **File**       | `core/paper_parser.py`                   |
| **Purpose**    | Download and parse academic PDFs into structured text for LLM consumption. |

#### Implementation Details

- **Multi-backend fallback chain:**
  The parser tries three extraction backends in order of quality:

  ```
  GROBID (TEI XML)  ──>  PyMuPDF (fitz)  ──>  PyPDF2 (legacy)
        |                      |                     |
    Best quality          Good quality          Last resort
    (needs server)        (local, fast)         (basic text)
  ```

  1. **GROBID** — sends the PDF to a GROBID server (configurable endpoint),
     receives TEI XML with structured sections, authors, references, tables.
     Preferred when a GROBID instance is available.
  2. **PyMuPDF** (`fitz`) — local extraction with layout-aware text blocks,
     table detection heuristics, and figure caption extraction.
  3. **PyPDF2** — basic page-by-page text extraction. Used only when the
     above two fail or are unavailable.

- **URL normalization in `download_pdf()`:**
  - **arXiv:** Converts `/abs/XXXX.XXXXX` URLs to `/pdf/XXXX.XXXXX.pdf`
  - **SSRN:** Converts `abstract_id=NNNNNNN` URLs to the corresponding
    `Delivery.cfm` download endpoint
  - Handles both `http` and `https` variants automatically
  - Sets appropriate `User-Agent` headers for reliable downloads

- **Section detection:**
  - Identifies standard academic sections (Abstract, Introduction,
    Methodology, Data, Results, Conclusion, References)
  - Falls back to page-boundary splitting when no section headers are found
  - Preserves mathematical notation where the backend supports it

- **Token estimation:**
  - `raw_token_estimate` computed as `len(full_text) // 4` (rough GPT
    tokenizer approximation)
  - Used downstream to decide chunking strategy for LLM calls

#### Output Dataclass: `ParsedPaper`

| Field               | Type                   | Description                                    |
|----------------------|------------------------|------------------------------------------------|
| `title`             | `str`                  | Paper title extracted from metadata or text     |
| `authors`           | `list[str]`            | List of author names                            |
| `abstract`          | `str`                  | Paper abstract text                             |
| `sections`          | `list[ParsedSection]`  | Ordered list of parsed sections                 |
| `full_text`         | `str`                  | Complete extracted text (all sections joined)    |
| `references`        | `list[str]`            | Bibliographic references                        |
| `tables`            | `list[str]`            | Extracted table content (text representation)    |
| `figures`           | `list[str]`            | Figure captions and descriptions                |
| `page_count`        | `int`                  | Number of pages in the PDF                      |
| `source_path`       | `str`                  | Local path to the downloaded/provided PDF       |
| `parse_backend`     | `str`                  | Which backend was used (`grobid`/`pymupdf`/`pypdf2`) |
| `raw_token_estimate`| `int`                  | Estimated token count for LLM context budgeting |

#### Key Method: `get_text_for_analysis()`

```python
def get_text_for_analysis(self, max_chars: int = 500000) -> str:
    """
    Returns LLM-ready text truncated to max_chars.
    Prioritizes: abstract > methodology > data > results > other sections.
    """
```

This method ensures the most analytically relevant sections are included
first when the paper exceeds context limits. The priority order reflects
what matters most for strategy extraction:

1. Abstract — high-level strategy description
2. Methodology / Model — signal construction details
3. Data — universe, frequency, sources
4. Results — reported performance metrics
5. Remaining sections — background, literature review, etc.

#### Configuration

| Setting              | Default        | Description                            |
|----------------------|----------------|----------------------------------------|
| `grobid_url`         | `None`         | GROBID server endpoint (optional)      |
| `pdf_download_dir`   | `/tmp/q2r_pdfs`| Directory for downloaded PDFs          |
| `max_pdf_size_mb`    | `50`           | Maximum PDF file size to process       |

---

### Stage 2: Strategy Extraction

| Property       | Value                                    |
|----------------|------------------------------------------|
| **Module**     | `StrategyExtractor`                      |
| **File**       | `core/strategy_extractor.py`             |
| **Purpose**    | Extract structured quantitative strategy details from parsed paper text using LLM. |

#### Implementation Details

- **Prompt template:** `prompts/strategy_extractor.txt`
  - Instructs the LLM to identify signals, portfolio construction rules,
    data requirements, and reported results
  - Includes few-shot examples for common strategy types (momentum,
    mean-reversion, carry, value)

- **LLM call configuration:**
  ```
  temperature:        0.1        (near-deterministic for factual extraction)
  max_output_tokens:  8192       (strategies can be complex)
  response_format:    "json"     (structured output parsing)
  ```

- **Vision support:**
  - For Gemini models, uses `generate_with_file()` to send the raw PDF
    alongside text, enabling the LLM to read tables and figures directly
  - Falls back to text-only extraction for non-vision models

- **Extraction pipeline:**
  ```
  Paper Text ──> Prompt Template ──> LLM (JSON mode) ──> Parse ──> StrategyExtraction
                      |                                       |
               strategy_extractor.txt               json.loads() + validation
  ```

#### Output Dataclass: `StrategyExtraction`

##### Top-Level Fields

| Field                        | Type                    | Description                                        |
|------------------------------|-------------------------|----------------------------------------------------|
| `strategy_name`              | `str`                   | Descriptive name for the strategy                  |
| `authors`                    | `list[str]`             | Paper authors                                      |
| `publication_year`           | `int`                   | Year of publication                                |
| `abstract_summary`           | `str`                   | Concise summary of the strategy                    |
| `asset_classes`              | `list[str]`             | e.g., `["equities", "futures"]`                    |
| `instrument_types`           | `list[str]`             | e.g., `["stocks", "ETFs"]`                         |
| `universe_description`       | `str`                   | Description of the investment universe             |
| `universe_filters`           | `list[str]`             | Filters applied (market cap, liquidity, etc.)      |
| `signals`                    | `list[SignalConstruction]` | All signals described in the paper              |
| `portfolio`                  | `PortfolioConstruction` | Portfolio construction methodology                 |
| `data_requirements`          | `list[str]`             | Required data fields (price, volume, etc.)         |
| `data_frequency`             | `str`                   | `"daily"`, `"monthly"`, `"weekly"`, etc.           |
| `data_sources_mentioned`     | `list[str]`             | CRSP, Compustat, Bloomberg, etc.                   |
| `reported_results`           | `ReportedResults`       | Performance metrics from the paper                 |
| `robustness_tests`           | `list[str]`             | Robustness checks mentioned in paper               |
| `transaction_cost_assumptions`| `str`                  | How paper handles transaction costs                |
| `key_equations`              | `list[str]`             | LaTeX or text equations from the paper             |
| `risk_model`                 | `str`                   | Risk model used (if any)                           |

##### Nested: `SignalConstruction`

| Field                 | Type           | Description                                          |
|-----------------------|----------------|------------------------------------------------------|
| `signal_type`         | `str`          | `"momentum"`, `"value"`, `"carry"`, etc.             |
| `formula`             | `str`          | Mathematical formula or description                  |
| `lookback_period`     | `str`          | e.g., `"12 months"`, `"252 days"`                    |
| `formation_period`    | `str`          | Period over which signal is formed                   |
| `skip_period`         | `str`          | Gap between formation and holding (e.g., `"1 month"`)|
| `normalization`       | `str`          | How signal is normalized (z-score, rank, etc.)       |
| `is_cross_sectional`  | `bool`         | Whether signal is cross-sectional                    |
| `is_time_series`      | `bool`         | Whether signal is time-series                        |
| `combination_weights` | `list[float]`  | Weights if multiple sub-signals are combined         |
| `detailed_steps`      | `list[str]`    | Step-by-step signal construction procedure           |

##### Nested: `PortfolioConstruction`

| Field                  | Type        | Description                                        |
|------------------------|-------------|----------------------------------------------------|
| `method`               | `str`       | `"long-short"`, `"long-only"`, `"risk-parity"`     |
| `long_leg`             | `str`       | How the long portfolio is formed                   |
| `short_leg`            | `str`       | How the short portfolio is formed                  |
| `weighting`            | `str`       | `"equal"`, `"value"`, `"signal"`, `"inverse-vol"`  |
| `rebalancing_frequency`| `str`       | `"monthly"`, `"weekly"`, `"daily"`                 |
| `rebalancing_lag`      | `str`       | Lag between signal and trade execution             |
| `max_positions`        | `int`       | Maximum number of positions                        |
| `turnover_constraints` | `str`       | Constraints on portfolio turnover                  |

##### Nested: `ReportedResults`

| Field                | Type             | Description                                  |
|----------------------|------------------|----------------------------------------------|
| `annual_return`      | `float`          | Reported annualized return                   |
| `annual_volatility`  | `float`          | Reported annualized volatility               |
| `sharpe_ratio`       | `float`          | Reported Sharpe ratio                        |
| `max_drawdown`       | `float`          | Maximum drawdown                             |
| `t_statistic`        | `float`          | Statistical significance                     |
| `sample_period`      | `str`            | e.g., `"1990-2020"`                          |
| `benchmark`          | `str`            | Benchmark used for comparison                |
| `additional_metrics` | `dict[str, Any]` | Any other reported metrics                   |

#### Configuration

| Setting                | Default  | Description                                 |
|------------------------|----------|---------------------------------------------|
| `extraction_model`     | (global) | LLM model used for extraction               |
| `temperature`          | `0.1`    | Low temperature for factual extraction       |
| `max_output_tokens`    | `8192`   | Maximum response length                      |
| `enable_vision`        | `True`   | Use vision mode when available (Gemini)      |

---

### Stage 3: Planning

| Property       | Value                                    |
|----------------|------------------------------------------|
| **Module**     | `DecomposedPlanner`                      |
| **File**       | `core/planner.py`                        |
| **Purpose**    | Generate a complete architecture plan for the backtest repository through multi-step decomposition. |

#### Implementation Details

The planner uses a **4-step decomposition** approach, where each step builds
on the output of the previous one. In classic mode, self-refine is **not**
applied (see [Stage 3a](#stage-3a-decomposed-planning--self-refine) for agent
mode).

```
  Strategy ──> Step 1 ──> Step 2 ──> Step 3 ──> Step 4 ──> ArchitecturePlan
  Extraction   Overall    Arch.      Signal     Config
               Plan       Design     Logic      Gen.
```

##### Step 1: Overall Backtest Plan

Generates a high-level plan covering all major components:

**Output:** `OverallPlan`

| Field                    | Type        | Description                              |
|--------------------------|-------------|------------------------------------------|
| `core_modules`           | `list[str]` | Modules to implement                     |
| `data_pipeline`          | `str`       | Data loading and processing approach     |
| `signal_generation`      | `str`       | Signal computation methodology           |
| `portfolio_rules`        | `str`       | Portfolio construction and rebalancing    |
| `performance_evaluation` | `str`       | Metrics and analysis approach            |
| `robustness_checks`      | `str`       | Planned robustness/sensitivity tests     |
| `summary`                | `str`       | Overall plan summary                     |

##### Step 2: Architecture Design

Generates the file structure and relationships:

**Output:** `ArchitectureDesign`

| Field                    | Type              | Description                            |
|--------------------------|-------------------|----------------------------------------|
| `file_list`              | `list[FileSpec]`  | Files to generate with descriptions    |
| `class_diagram_mermaid`  | `str`             | Mermaid class diagram                  |
| `sequence_diagram_mermaid`| `str`            | Mermaid sequence diagram               |
| `module_relationships`   | `dict[str, list]` | Dependency graph between modules       |

##### Step 3: Signal Logic Design

Designs the detailed execution flow:

**Output:** `LogicDesign`

| Field                | Type              | Description                              |
|----------------------|-------------------|------------------------------------------|
| `execution_order`    | `list[str]`       | Order in which files should be generated |
| `dependency_graph`   | `dict[str, list]` | Which files depend on which              |
| `file_specifications`| `list[FileSpec]`  | Detailed specs per file (classes, funcs) |

##### Step 4: Config Generation

Generates a `config.py` file containing all paper hyperparameters:

```python
# config.py — auto-generated from paper parameters
LOOKBACK_PERIOD = 252        # 12-month lookback (trading days)
FORMATION_PERIOD = 12        # months
SKIP_PERIOD = 1              # 1-month skip
REBALANCING_FREQUENCY = "monthly"
TOP_PERCENTILE = 0.1         # top decile for long leg
BOTTOM_PERCENTILE = 0.1      # bottom decile for short leg
TRANSACTION_COST_BPS = 10    # basis points per trade
START_DATE = "1990-01-01"
END_DATE = "2020-12-31"
```

#### Combined Output: `ArchitecturePlan`

| Field              | Type              | Description                               |
|--------------------|-------------------|-------------------------------------------|
| `files`            | `list[FileSpec]`  | All files to generate                     |
| `class_diagram`    | `str`             | Mermaid class diagram                     |
| `sequence_diagram` | `str`             | Mermaid sequence diagram                  |
| `config_content`   | `str`             | Generated config.py content               |
| `summary`          | `str`             | Human-readable plan summary               |

#### Default File List

In classic mode, the planner generates these files by default:

```
project/
  config.py            # All hyperparameters from the paper
  data_loader.py       # Data downloading and preprocessing
  signals.py           # Signal construction (core logic)
  portfolio.py         # Portfolio construction and rebalancing
  analysis.py          # Performance metrics and statistics
  visualization.py     # Charts, plots, tearsheets
  main.py              # Entry point — runs the full backtest
  requirements.txt     # Python dependencies
  README.md            # Documentation with paper reference
```

#### Configuration

| Setting              | Default   | Description                                |
|----------------------|-----------|--------------------------------------------|
| `planning_model`     | (global)  | LLM model for planning                    |
| `temperature`        | `0.2`     | Slightly higher than extraction for creativity |
| `enable_self_refine` | `False`   | Disabled in classic mode                   |

---

### Stage 4: Code Generation

| Property       | Value                                    |
|----------------|------------------------------------------|
| **Module**     | `CodeSynthesizer`                        |
| **File**       | `core/coder.py`                          |
| **Purpose**    | Generate Python source files in dependency order with parallel execution of independent files. |

#### Implementation Details

- **Dependency-ordered generation:**
  Files are generated using **topological sort** via `_compute_depth_levels()`.
  This ensures that every file's dependencies are generated before it.

  ```
  Depth 0:  config.py, requirements.txt, README.md
  Depth 1:  data_loader.py
  Depth 2:  signals.py
  Depth 3:  portfolio.py
  Depth 4:  analysis.py, visualization.py
  Depth 5:  main.py
  ```

- **Implicit dependency map:**
  ```python
  IMPLICIT_DEPS = {
      "signals.py":        ["config.py", "data_loader.py"],
      "portfolio.py":      ["config.py", "signals.py"],
      "analysis.py":       ["config.py", "portfolio.py"],
      "visualization.py":  ["config.py", "analysis.py"],
      "main.py":           ["config.py", "data_loader.py", "signals.py",
                            "portfolio.py", "analysis.py", "visualization.py"],
  }
  ```

- **Parallel generation:**
  Files at the same depth level are generated concurrently using
  `ThreadPoolExecutor` with `max_workers=4`:

  ```
  Time ──────────────────────────────────────────────>

  [config.py] [requirements.txt] [README.md]          # depth 0 (parallel)
                                              |
                                    [data_loader.py]   # depth 1
                                              |
                                    [signals.py]       # depth 2
                                              |
                                    [portfolio.py]     # depth 3
                                              |
                              [analysis.py] [viz.py]   # depth 4 (parallel)
                                              |
                                    [main.py]          # depth 5
  ```

- **Prompt construction:**
  Each file's generation prompt includes:
  - Paper context (truncated to ~15,000 characters)
  - Key equations extracted from the strategy
  - Full strategy extraction details (signals, portfolio rules)
  - Code from dependency files (truncated to ~3,000 characters per dependency)
  - File-specific analysis (from FileAnalyzer in agent mode, empty in classic)

- **Code requirements injected into every prompt:**
  - Implement exactly what the paper describes (no embellishments)
  - Use pandas/numpy vectorized operations (no row-by-row loops)
  - Include docstrings with paper references
  - **NO look-ahead bias** — never use future data in signal construction
  - Proper date alignment across all DataFrames
  - Handle missing data explicitly (`dropna`, `fillna`, forward-fill)
  - All parameters must reference `config.py` (no magic numbers)

- **Output cleaning pipeline:**
  ```
  Raw LLM Output ──> Strip markdown fences ──> Remove ```python / ``` ──>
  Validate syntax via compile() ──> Clean file
  ```
  - Markdown fence removal handles triple-backtick code blocks
  - `compile()` call validates Python syntax; if it fails, the raw output
    is kept and flagged for validation in Stage 5

#### Configuration

| Setting              | Default   | Description                               |
|----------------------|-----------|--------------------------------------------|
| `coding_model`       | (global)  | LLM model for code generation             |
| `temperature`        | `0.2`     | Low temp for correct code                  |
| `max_output_tokens`  | `16384`   | Large limit for complex files              |
| `max_workers`        | `4`       | Parallel generation threads                |
| `paper_context_chars`| `15000`   | Max chars of paper text in prompt          |
| `dep_context_chars`  | `3000`    | Max chars per dependency file in prompt    |

---

### Stage 5: Validation + Auto-Fix

| Property       | Value                                    |
|----------------|------------------------------------------|
| **Module**     | `CodeValidator`                          |
| **File**       | `core/validator.py`                      |
| **Purpose**    | Validate generated code for quant-specific correctness and auto-fix critical issues. |

#### Implementation Details

- **Validation checks performed:**
  - **Signal fidelity** — Does the code implement the signals described in
    the paper? Checks for presence of key computations.
  - **Look-ahead bias** — Detects `.shift(-N)`, future data access,
    using close prices before market close, etc.
  - **Rebalancing lag** — Ensures signals are computed before execution
    (signal on day T, trade on day T+lag).
  - **Transaction costs** — Verifies costs are applied and configurable.
  - **Universe selection** — Checks for survivorship bias indicators
    (e.g., using current S&P 500 constituents for historical backtest).
  - **Configurable hyperparameters** — Ensures parameters reference
    `config.py` rather than being hardcoded.

- **Scoring system:**
  ```
  Score = 100 - (critical_count * 20) - (warning_count * 5) - (info_count * 1)
  
  Pass condition:  score >= 80  AND  critical_count == 0
  ```

- **Auto-fix loop:**
  ```
  Generated Code ──> Validate ──> Issues found?
                                      |
                         Yes (critical) │  No ──> Pass
                                      |
                              Fix via LLM ──> Re-validate
                                      |
                              max 2 iterations
  ```

  - Only files with **critical** issues are sent for auto-fix
  - Maximum `max_fix_iterations=2` to prevent infinite loops
  - Each fix iteration sends the file + issues to the LLM with a
    targeted fix prompt

#### Output Dataclass: `ValidationReport`

| Field              | Type                      | Description                           |
|--------------------|---------------------------|---------------------------------------|
| `issues`           | `list[ValidationIssue]`   | All detected issues                   |
| `score`            | `int`                     | Overall quality score (0-100)         |
| `signal_coverage`  | `float`                   | Fraction of paper signals implemented (0-1) |
| `data_coverage`    | `float`                   | Fraction of data requirements met (0-1) |
| `passed`           | `bool`                    | `score >= 80 and critical_count == 0` |

##### Nested: `ValidationIssue`

| Field         | Type   | Description                                          |
|---------------|--------|------------------------------------------------------|
| `severity`    | `str`  | `"critical"` / `"warning"` / `"info"`                |
| `file_path`   | `str`  | File where issue was found                           |
| `line_hint`   | `int`  | Approximate line number                              |
| `description` | `str`  | Human-readable issue description                     |
| `suggestion`  | `str`  | Suggested fix                                        |
| `category`    | `str`  | Issue category (bias, coverage, style, etc.)         |

#### Configuration

| Setting              | Default | Description                                |
|----------------------|---------|--------------------------------------------|
| `validation_model`   | (global)| LLM model for validation                  |
| `max_fix_iterations`  | `2`    | Maximum auto-fix attempts                  |
| `pass_threshold`     | `80`    | Minimum score to pass validation           |
| `auto_fix_enabled`   | `True`  | Whether to attempt auto-fixes              |

---

### Stage 6: Save

| Property       | Value                                    |
|----------------|------------------------------------------|
| **Module**     | (inline in pipeline)                     |
| **File**       | `core/pipeline.py`                       |
| **Purpose**    | Write all generated files to disk, creating directories as needed. |

#### Implementation Details

- Creates `output_dir` if it does not exist (`os.makedirs(exist_ok=True)`)
- Writes each file from the generation result to its specified path
- Preserves the directory structure defined in the architecture plan
- Sets appropriate file permissions (readable, not executable except shell scripts)
- Logs the final file count and total lines of code generated

#### Output Structure

```
output_dir/
  config.py
  data_loader.py
  signals.py
  portfolio.py
  analysis.py
  visualization.py
  main.py
  requirements.txt
  README.md
```

---

## 3. Agent Mode Pipeline (11 Stages)

Agent mode extends the classic pipeline with iterative refinement, execution,
and evaluation. Stages 1 and 2 are **identical** to classic mode (see above).
The pipeline diverges at Stage 3.

```
  Stages 1-2 (shared)
       |
       v
  ┌─────────────────────────────────────────────────────────────┐
  │  AGENT MODE EXTENSIONS                                      │
  │                                                              │
  │  3. Plan + Self-Refine ─> 4. Analysis + RAG ─> 5. CodeGen   │
  │       |                       |                    |         │
  │       v                       v                    v         │
  │  [refine loop]          [parallel batch]     [context mgr]   │
  │                                                    |         │
  │  6. Test Gen ─> 7. Validate ─> 8. Bias Check ─>   │         │
  │                                      |              │         │
  │  9. Execute + Debug ─> 10. DevOps ─> 11. Evaluate   │         │
  │       |                                              │         │
  │  [debug loop]                                        │         │
  │                                                      │         │
  │  12. Save                                            │         │
  └─────────────────────────────────────────────────────────────┘
```

---

### Stage 3a: Decomposed Planning + Self-Refine

| Property       | Value                                    |
|----------------|------------------------------------------|
| **Module**     | `DecomposedPlanner` + `SelfRefiner`      |
| **File**       | `core/planner.py`, `core/refiner.py`     |
| **Purpose**    | Generate architecture plan with iterative verification and refinement for higher quality. |

#### Implementation Details

Same `DecomposedPlanner` as classic mode, **but** Steps 1 (Overall Plan) and
Step 2 (Architecture Design) are wrapped with the `SelfRefiner`:

```
  Step 1: Overall Plan
       |
       v
  SelfRefiner.refine(overall_plan)
       |
       ├──> Verify: critique the plan
       |        |
       |        v
       ├──> Refine: address critique
       |        |
       |        v
       └──> Re-verify: check improvements
       |
       v
  Step 2: Architecture Design
       |
       v
  SelfRefiner.refine(architecture_design)
       |
       v
  Steps 3-4: (same as classic)
```

- **Self-refine cycle:**
  1. **Verify** — LLM critiques the artifact for quant-specific issues
  2. **Refine** — LLM produces an improved version addressing the critique
  3. **Re-verify** — LLM checks whether improvements were effective
  4. **Decision** — Continue refining or accept (max iterations configurable)

- **JSON round-tripping:**
  JSON artifacts (plans, architecture) are serialized to JSON and parsed
  back after each refinement to ensure structural validity.

- **Early exit:**
  If only minor issues remain after the first iteration, the refiner
  exits early to save LLM calls.

- **Interactive pause:**
  When `--interactive` flag is set, the pipeline displays the finalized
  plan and waits for user confirmation (`Enter` to continue, `Ctrl+C`
  to abort).

See [Section 4: Self-Refine Mechanism](#4-self-refine-mechanism) for full
details on the verify/refine loop.

#### Configuration

| Setting              | Default | Description                                |
|----------------------|---------|--------------------------------------------|
| `enable_self_refine` | `True`  | Enable self-refine in agent mode           |
| `max_refine_iters`   | `2`     | Maximum refinement iterations              |
| `interactive`        | `False` | Pause for user confirmation after planning |

---

### Stage 4a: Per-File Analysis + CodeRAG (parallel)

| Property       | Value                                    |
|----------------|------------------------------------------|
| **Module**     | `FileAnalyzer` + `CodeRAG`               |
| **File**       | `core/file_analyzer.py`, `advanced/code_rag.py` |
| **Purpose**    | Analyze each planned file in detail and mine GitHub for reference implementations, both running in parallel. |

#### Implementation Details

Two processes run concurrently:

```
  ┌──────────────────────────────┐    ┌──────────────────────────────┐
  │  FileAnalyzer (main thread)  │    │  CodeRAG (background thread) │
  │                              │    │                              │
  │  Batch 1: [config, data]     │    │  build_index()               │
  │  Batch 2: [signals, portf]   │    │    - Search GitHub           │
  │  Batch 3: [analysis, viz]    │    │    - Clone top repos          │
  │  Batch 4: [main]             │    │    - Extract relevant code   │
  │                              │    │    - Build vector index       │
  └──────────────────────────────┘    └──────────────────────────────┘
```

##### FileAnalyzer

- Analyzes each `.py` file in the architecture plan **before** code generation
- Produces a `FileAnalysis` for each file, giving the code generator rich context
- Processed in **batches of 4** concurrently using `ThreadPoolExecutor`
- Prior analyses are fed as context for consistency across files

**Output:** `FileAnalysis`

| Field              | Type              | Description                               |
|--------------------|-------------------|-------------------------------------------|
| `file_path`        | `str`             | Target file path                          |
| `classes`          | `list[ClassSpec]`  | Classes to implement                      |
| `functions`        | `list[FuncSpec]`   | Standalone functions to implement         |
| `imports`          | `list[str]`        | Required imports                          |
| `dependencies`     | `list[str]`        | Files this file depends on                |
| `algorithms`       | `list[str]`        | Algorithms to implement (from paper)      |
| `input_output_spec`| `str`             | Expected inputs and outputs               |
| `test_criteria`    | `list[str]`        | What to test for this file                |
| `quant_specific`   | `str`             | Quant-specific considerations             |

##### CodeRAG

- Runs in a **background thread** while FileAnalyzer processes files
- `CodeRAG.build_index()` searches GitHub for reference backtests matching
  the strategy type
- Extracts relevant code snippets and builds a vector index for retrieval
  during code generation
- Results are available by the time code generation starts

#### Configuration

| Setting             | Default  | Description                                 |
|---------------------|----------|---------------------------------------------|
| `analysis_batch_size`| `4`     | Files per analysis batch                    |
| `enable_code_rag`   | `True`   | Enable GitHub code mining                   |
| `rag_max_repos`     | `5`      | Maximum repos to clone for reference        |

---

### Stage 5a: Code Generation + Context Manager

| Property       | Value                                    |
|----------------|------------------------------------------|
| **Module**     | `CodeSynthesizer` + `ContextManager`     |
| **File**       | `core/coder.py`, `advanced/context_manager.py` |
| **Purpose**    | Generate code with enhanced context management for consistency across files. |

#### Implementation Details

Same `CodeSynthesizer` as classic mode, but enhanced with the `ContextManager`:

- **ContextManager responsibilities:**
  - Builds **rich prompts** that include file analyses, RAG results, and
    cumulative context from previously generated files
  - **Records generated files** as they are produced, maintaining a running
    summary of the entire codebase
  - Maintains a **clean-slate context** with cumulative code summaries to
    avoid exceeding LLM context windows
  - Uses LLM-generated summaries of previously generated files to stay
    within `context_max_chars=80000`

```
  For each file at depth N:
  ┌─────────────────────────────────────────────────────────────┐
  │  Context Manager builds prompt:                             │
  │                                                              │
  │  1. Paper context (15K chars)                                │
  │  2. Strategy extraction (full)                               │
  │  3. File analysis from Stage 4 (per-file)                    │
  │  4. CodeRAG snippets (relevant matches)                      │
  │  5. Dependency file code (full or summarized)                │
  │  6. Cumulative codebase summary (for non-deps)               │
  │  7. File specification from architecture plan                │
  └─────────────────────────────────────────────────────────────┘
```

- **Context budget management:**
  When total context exceeds `context_max_chars`, the Context Manager:
  1. Keeps full code for direct dependencies (highest priority)
  2. Replaces indirect dependency code with LLM-generated summaries
  3. Truncates paper context if still over budget
  4. Drops CodeRAG snippets as last resort

#### Configuration

| Setting              | Default  | Description                               |
|----------------------|----------|-------------------------------------------|
| `context_max_chars`  | `80000`  | Maximum context window budget             |
| `summary_model`      | (global) | LLM for generating code summaries         |
| `include_rag`        | `True`   | Include CodeRAG results in context        |

---

### Stage 6a: Test Generation

| Property       | Value                                    |
|----------------|------------------------------------------|
| **Module**     | `TestGenerator`                          |
| **File**       | `advanced/test_generator.py`             |
| **Purpose**    | Auto-generate a pytest test suite covering signals, portfolio construction, and data handling. |

#### Implementation Details

- Generates test files for the three core areas:
  ```
  tests/
    test_signals.py      # Signal calculation correctness
    test_portfolio.py    # Portfolio construction logic
    test_data.py         # Data loading and preprocessing
  ```

- **Test categories generated:**

  | Test Area         | What It Tests                                              |
  |-------------------|------------------------------------------------------------|
  | Signal tests      | Correct computation, no NaN propagation, proper lookback   |
  | Portfolio tests   | Rebalancing frequency, position limits, weight sums to 1   |
  | Data tests        | Loading without errors, correct date parsing, no gaps      |
  | Bias tests        | No future data leakage, proper lag in signal-to-trade      |
  | Integration tests | End-to-end pipeline runs without errors                    |

- Uses file analyses from Stage 4 to determine test criteria per file
- Tests include both **unit tests** (isolated function checks) and
  **integration tests** (multi-module interactions)

#### Configuration

| Setting              | Default  | Description                               |
|----------------------|----------|-------------------------------------------|
| `test_model`         | (global) | LLM for test generation                  |
| `generate_tests`     | `True`   | Whether to generate tests                 |
| `test_framework`     | `pytest` | Test framework to use                     |

---

### Stage 7a: Validation + Auto-Fix

Identical to [Classic Stage 5](#stage-5-validation--auto-fix). Same
`CodeValidator`, same scoring, same auto-fix loop.

The only difference is that in agent mode, the validator also checks the
generated test files for correctness and consistency with the main code.

---

### Stage 8a: Backtest Validation (Bias Checks)

| Property       | Value                                    |
|----------------|------------------------------------------|
| **Module**     | `BacktestValidator`                      |
| **File**       | `advanced/backtest_validator.py`         |
| **Purpose**    | Deep analysis of the generated backtest for quantitative biases and methodological issues. |

#### Implementation Details

The BacktestValidator performs **two kinds of analysis**:

##### 1. Static Checks (Regex/AST-based)

Fast, deterministic checks that scan source code for known anti-patterns:

| Check ID                       | Severity   | Detection Method      | What It Catches                              |
|--------------------------------|------------|----------------------|----------------------------------------------|
| `potential_future_shift`       | Critical   | Regex: `.shift(-N)`   | Negative shift = using future data           |
| `no_lag_in_signal`             | Critical   | AST scan              | Signal files missing `.shift()` / lag logic  |
| `hardcoded_dates`              | Warning    | Regex: date patterns  | >5 hardcoded dates outside `config.py`       |
| `iloc_last_in_signal`          | Warning    | Regex: `.iloc[-1]`    | Using last element in signal (potential bias)|
| `hardcoded_transaction_costs`  | Warning    | Regex + AST           | Costs not referencing `config`               |
| `ambiguous_merge_in_signal`    | Warning    | AST: `merge()` calls  | Merge without explicit `how=` parameter      |
| `missing_random_seed`          | Info       | Regex: `random`       | Random operations without fixed seed         |

```python
# Example: what triggers potential_future_shift
df['signal'] = df['price'].shift(-1)    # CRITICAL: using tomorrow's price
df['signal'] = df['price'].shift(1)     # OK: using yesterday's price

# Example: what triggers no_lag_in_signal
# If signals.py has NO .shift() calls at all, the check fires
# because signals should always be lagged before trading
```

##### 2. LLM Checks (Semantic Analysis)

Deep semantic validation using LLM to understand code logic:

| Check                      | Severity | What It Catches                                     |
|----------------------------|----------|-----------------------------------------------------|
| Look-ahead bias            | Critical | Signals using future data in non-obvious ways       |
| Survivorship bias          | Critical | Universe not accounting for delistings/bankruptcies |
| Rebalancing timing         | Critical | Signal and trade executed on same date              |
| Point-in-time data         | Warning  | Using revised data instead of as-reported           |
| Transaction costs          | Warning  | Hardcoded or missing transaction costs              |
| Data snooping              | Warning  | Excessive parameter tuning on in-sample data        |
| Capacity constraints       | Info     | Strategy may not scale to large AUM                 |
| Sample period sensitivity  | Info     | Results depend heavily on specific date range       |

#### Full Bias Checks Table

| Check                    | Severity   | What It Catches                                 |
|--------------------------|------------|-------------------------------------------------|
| Look-ahead bias          | Critical   | Signals using future data                       |
| Survivorship bias        | Critical   | Universe not accounting for delistings          |
| Rebalancing timing       | Critical   | Signal and trade on same date                   |
| No lag in signal         | Critical   | Signal files missing `.shift()`                 |
| Point-in-time data       | Warning    | Using revised data instead of as-reported       |
| Transaction costs        | Warning    | Hardcoded or missing costs                      |
| Data snooping            | Warning    | Excessive parameter tuning                      |
| Capacity constraints     | Info       | Strategy may not scale                          |
| Sample period sensitivity| Info       | Results depend on specific dates                |

#### Bias Risk Scoring

```python
bias_risk = min(100, critical_fails * 25 + warning_fails * 10)

# Examples:
#   0 critical, 0 warnings  =>  bias_risk =   0  (clean)
#   1 critical, 0 warnings  =>  bias_risk =  25
#   2 critical, 1 warning   =>  bias_risk =  60
#   4 critical, 0 warnings  =>  bias_risk = 100  (maximum risk)
```

#### Output Dataclass: `BacktestValidationReport`

| Field               | Type                          | Description                        |
|---------------------|-------------------------------|------------------------------------|
| `checks`            | `list[BacktestCheck]`         | All checks performed and results   |
| `bias_risk_score`   | `int`                         | Aggregate risk score (0-100)       |
| `recommendations`   | `list[str]`                   | Specific improvement suggestions   |
| `passed`            | `bool`                        | `True` if bias_risk_score < 50     |

#### Configuration

| Setting                | Default  | Description                              |
|------------------------|----------|------------------------------------------|
| `bias_check_model`     | (global) | LLM for semantic bias analysis           |
| `enable_static_checks` | `True`   | Run regex/AST-based checks               |
| `enable_llm_checks`    | `True`   | Run LLM-based semantic checks            |
| `bias_risk_threshold`  | `50`     | Maximum acceptable bias risk score       |

---

### Stage 9a: Execution Sandbox + Auto-Debug

| Property       | Value                                    |
|----------------|------------------------------------------|
| **Module**     | `ExecutionSandbox` + `AutoDebugger`      |
| **File**       | `advanced/executor.py`, `advanced/debugger.py` |
| **Purpose**    | Execute the generated backtest in an isolated environment and iteratively fix runtime errors. |

#### Implementation Details

##### ExecutionSandbox

Two execution modes, chosen based on availability:

```
  ┌─────────────────────────────────┐
  │  Docker Available?              │
  │                                 │
  │  Yes ──> Docker Mode            │
  │           - Build image         │
  │           - Run in container    │
  │           - Full isolation      │
  │                                 │
  │  No  ──> Local Mode             │
  │           - subprocess.run()    │
  │           - PYTHONPATH set      │
  │           - Process isolation   │
  └─────────────────────────────────┘
```

- **Docker mode (preferred):**
  - Builds a Docker image from the generated `Dockerfile`
  - Runs the entry point (`main.py`) inside a container
  - Full filesystem and process isolation
  - Captures stdout/stderr from container logs

- **Local mode (fallback):**
  - Uses `subprocess.run()` with the repository directory on `PYTHONPATH`
  - Process-level isolation only
  - Captures stdout/stderr from subprocess pipes

**Output:** `ExecutionResult`

| Field              | Type          | Description                               |
|--------------------|---------------|-------------------------------------------|
| `success`          | `bool`        | Whether execution completed without error |
| `stdout`           | `str`         | Standard output                           |
| `stderr`           | `str`         | Standard error                            |
| `exit_code`        | `int`         | Process exit code                         |
| `duration_seconds` | `float`       | Wall-clock execution time                 |
| `error_type`       | `str`         | Classified error type (if failed)         |
| `modified_files`   | `list[str]`   | Files modified during execution           |

##### AutoDebugger

Iterative error analysis and fixing loop:

```
  Execute ──> Success?
                |
       Yes ──> Done!
                |
       No  ──> AutoDebugger
                |
                ├──> Analyze error (LLM)
                ├──> Generate targeted fix
                ├──> Apply fix to source
                ├──> Re-execute
                |
                └──> Repeat (max 3 iterations)
```

- **Error analysis:** The debugger sends the error traceback, relevant source
  file, and execution context to the LLM for root cause analysis
- **Targeted fixes:** Generates minimal, focused fixes rather than rewriting
  entire files
- **19+ Python error types handled:**
  ```
  ImportError, ModuleNotFoundError, FileNotFoundError,
  KeyError, IndexError, ValueError, TypeError,
  AttributeError, NameError, ZeroDivisionError,
  MemoryError, TimeoutError, ConnectionError,
  PermissionError, OSError, RuntimeError,
  SyntaxError, IndentationError, RecursionError
  ```

**Output:** `DebugReport`

| Field           | Type              | Description                             |
|-----------------|-------------------|-----------------------------------------|
| `iteration`     | `int`             | Debug iteration number                  |
| `error_message` | `str`             | Error message being addressed           |
| `error_type`    | `str`             | Classified Python error type            |
| `fixes`         | `list[DebugFix]`  | Fixes applied in this iteration         |
| `resolved`      | `bool`            | Whether this iteration resolved the error |

#### Configuration

| Setting                | Default  | Description                              |
|------------------------|----------|------------------------------------------|
| `execution_mode`       | `auto`   | `docker`, `local`, or `auto` (prefer Docker) |
| `execution_timeout`    | `300`    | Maximum execution time in seconds        |
| `max_debug_iterations` | `3`      | Maximum auto-debug attempts              |
| `debug_model`          | (global) | LLM for error analysis                   |

---

### Stage 10a: DevOps Generation

| Property       | Value                                    |
|----------------|------------------------------------------|
| **Module**     | `DevOpsGenerator`                        |
| **File**       | `advanced/devops.py`                     |
| **Purpose**    | Generate production-ready DevOps configuration files for the repository. |

#### Implementation Details

Generates the following files:

| File                             | Purpose                                         |
|----------------------------------|-------------------------------------------------|
| `Dockerfile`                     | Multi-stage build for the backtest environment  |
| `docker-compose.yml`            | Service definition with volume mounts            |
| `Makefile`                       | Common tasks: `make run`, `make test`, `make lint` |
| `.github/workflows/ci.yml`      | GitHub Actions CI pipeline                      |
| `setup.py`                       | Package installation configuration              |

- **Dockerfile:**
  ```dockerfile
  FROM python:3.11-slim
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt
  COPY . .
  CMD ["python", "main.py"]
  ```

- **GitHub Actions CI:**
  - Runs on push/PR to main branch
  - Installs dependencies
  - Runs pytest suite
  - Executes the backtest
  - Uploads results as artifacts

- **Makefile targets:**
  ```makefile
  run:       python main.py
  test:      pytest tests/ -v
  lint:      flake8 *.py
  docker:    docker-compose up --build
  clean:     rm -rf __pycache__ *.pyc
  ```

#### Configuration

| Setting               | Default  | Description                               |
|-----------------------|----------|-------------------------------------------|
| `generate_devops`     | `True`   | Whether to generate DevOps files          |
| `python_version`      | `3.11`   | Python version for Dockerfile             |
| `ci_provider`         | `github` | CI provider (currently GitHub Actions)    |

---

### Stage 11a: Reference Evaluation

| Property       | Value                                    |
|----------------|------------------------------------------|
| **Module**     | `ReferenceEvaluator`                     |
| **File**       | `advanced/evaluator.py`                  |
| **Purpose**    | Score the generated backtest against the paper's methodology and reported results. |

#### Implementation Details

Two evaluation modes depending on whether a reference implementation exists:

```
  ┌─────────────────────────────────┐
  │  Reference Implementation       │
  │  Available?                     │
  │                                 │
  │  Yes ──> Compare to reference   │
  │           - Code structure      │
  │           - Signal logic        │
  │           - Performance match   │
  │                                 │
  │  No  ──> Compare to paper       │
  │           - Methodology match   │
  │           - Reported numbers    │
  │           - Completeness        │
  └─────────────────────────────────┘
```

- **With reference implementation:**
  - Compares generated code structure against known-good implementation
  - Checks signal logic equivalence
  - Compares output metrics (returns, Sharpe, etc.)

- **Without reference (default):**
  - Compares generated code against paper text and reported performance
  - Evaluates methodology coverage
  - Checks for missing and extra components relative to paper description

#### Output Dataclass: `EvaluationScore`

| Field                | Type              | Description                              |
|----------------------|-------------------|------------------------------------------|
| `overall_score`      | `float`           | Overall quality score (1-5 scale)        |
| `component_scores`   | `dict[str, float]`| Per-component scores                     |
| `coverage`           | `float`           | Methodology coverage percentage (0-100%) |
| `missing_components` | `list[str]`       | Paper components not implemented         |
| `extra_components`   | `list[str]`       | Components added beyond the paper        |
| `summary`            | `str`             | Human-readable evaluation summary        |
| `severity_breakdown` | `dict[str, int]`  | Count of issues by severity              |

#### Grading Scale

| Grade | Score Range | Interpretation                                    |
|-------|-------------|---------------------------------------------------|
| **A** | >= 4.5      | Excellent — faithfully reproduces the paper        |
| **B** | >= 3.5      | Good — minor deviations from methodology          |
| **C** | >= 2.5      | Acceptable — some components missing or incorrect  |
| **D** | >= 1.5      | Poor — significant methodology gaps               |
| **F** | < 1.5       | Failing — does not implement the paper's strategy  |

```
  Score Distribution (typical):
  
  F     D        C        B        A
  |-----|--------|--------|--------|
  0    1.5      2.5      3.5     4.5    5.0
```

#### Configuration

| Setting                 | Default  | Description                              |
|-------------------------|----------|------------------------------------------|
| `evaluation_model`      | (global) | LLM for evaluation                      |
| `reference_path`        | `None`   | Path to reference implementation         |
| `min_acceptable_grade`  | `C`      | Minimum grade to consider successful     |

---

### Stage 12a: Save (Agent Mode)

Same as [Classic Stage 6](#stage-6-save), but writes additional files:

```
output_dir/
  config.py
  data_loader.py
  signals.py
  portfolio.py
  analysis.py
  visualization.py
  main.py
  requirements.txt
  README.md
  setup.py                          # from DevOps generation
  Dockerfile                        # from DevOps generation
  docker-compose.yml                # from DevOps generation
  Makefile                          # from DevOps generation
  .github/
    workflows/
      ci.yml                        # from DevOps generation
  tests/
    test_signals.py                 # from Test generation
    test_portfolio.py               # from Test generation
    test_data.py                    # from Test generation
```

---

## 4. Self-Refine Mechanism

The Self-Refine mechanism is the core quality improvement loop in Agent mode.
It wraps planning artifacts with an iterative verify-refine cycle that catches
quant-specific issues before code generation begins.

### Module Details

| Property       | Value                                    |
|----------------|------------------------------------------|
| **Class**      | `SelfRefiner`                            |
| **File**       | `core/refiner.py`                        |
| **Purpose**    | Iteratively verify and improve planning artifacts using LLM-based critique. |

### Verify / Refine Loop

```
                    ┌─────────────┐
                    │  Artifact   │
                    │  (original) │
                    └──────┬──────┘
                           │
                    ┌──────v──────┐
             ┌──────│   VERIFY    │
             │      │             │
             │      │  Critique   │
             │      │  the plan   │
             │      └──────┬──────┘
             │             │
             │      ┌──────v──────┐
             │      │  Needs      │
             │      │  refinement?│──── No ──> Accept artifact
             │      └──────┬──────┘
             │             │ Yes
             │      ┌──────v──────┐
             │      │   REFINE    │
             │      │             │
             │      │  Improve    │
             │      │  artifact   │
             │      └──────┬──────┘
             │             │
             │      ┌──────v──────┐
             └──────│ RE-VERIFY   │──── Max iterations? ──> Accept
                    │             │
                    └─────────────┘
```

### Prompt Templates

- **Verify prompt:** loaded from `prompts/self_refine_verify.txt`
  - Instructs the LLM to critique the artifact for quant-specific issues
  - Asks for structured feedback: what's good, what's missing, what's wrong

- **Refine prompt:** loaded from `prompts/self_refine_refine.txt`
  - Receives the original artifact + verification critique
  - Instructs the LLM to produce an improved version addressing all issues

### Applied To

The self-refiner wraps these specific planning artifacts:

| Artifact              | Planning Step | Why It's Refined                            |
|-----------------------|---------------|---------------------------------------------|
| `overall_plan`        | Step 1        | Ensure complete methodology coverage        |
| `architecture_design` | Step 2        | Verify file structure and dependencies      |

Steps 3 (signal logic) and 4 (config) are **not** refined because they
depend on the already-refined outputs of Steps 1 and 2.

### What the Verifier Checks

The verification step specifically looks for:

- **Signal construction completeness** — Are all signals from the paper
  represented in the plan?
- **Look-ahead bias risks** — Does the architecture allow for potential
  future data leakage?
- **Missing paper methodology** — Are any key methodology steps from the
  paper omitted?
- **Hardcoded parameters** — Are parameters configurable or hardcoded?
- **Data handling issues** — Missing data handling, incorrect frequency
  assumptions, etc.

### Refinement Decision: `_needs_refinement()`

The refiner decides whether to iterate based on keyword detection in the
verification critique:

```python
REFINEMENT_TRIGGERS = [
    "critical",
    "missing",
    "incorrect",
    "look-ahead bias",
    "not implemented",
    "hardcoded",
    "error",
]

def _needs_refinement(critique: str) -> bool:
    """Returns True if critique contains any trigger keywords."""
    critique_lower = critique.lower()
    return any(trigger in critique_lower for trigger in REFINEMENT_TRIGGERS)
```

If none of these keywords appear, the artifact is accepted as-is.

### Output Dataclass: `RefinementResult`

| Field          | Type   | Description                                      |
|----------------|--------|--------------------------------------------------|
| `original`     | `Any`  | The original artifact before refinement          |
| `refined`      | `Any`  | The refined artifact (or original if no changes) |
| `critique`     | `str`  | Verification critique text                       |
| `improvements` | `str`  | Summary of improvements made                     |
| `iterations`   | `int`  | Number of refinement iterations performed        |
| `improved`     | `bool` | Whether the artifact was actually changed        |

### Example Flow

```
Iteration 1:
  Verify:  "The plan is missing the skip period between formation and
            holding. Signal construction does not mention cross-sectional
            normalization. CRITICAL: no lag between signal generation
            and portfolio rebalancing."
  
  Decision: "critical" and "missing" detected → refine
  
  Refine:  Updated plan now includes skip period, cross-sectional z-score
           normalization, and explicit 1-day lag between signal and trade.

Iteration 2:
  Re-verify: "Plan now covers skip period and normalization. Minor
              suggestion: consider adding a configurable lookback
              window. Overall the plan is solid."
  
  Decision: No trigger keywords → accept
  
  Result: RefinementResult(iterations=2, improved=True)
```

---

## 5. Strategy Catalog Integration

The strategy catalog provides a curated collection of 47 pre-indexed
quantitative strategies that users can generate directly by ID, bypassing
the need to provide a PDF URL.

### How Catalog Entry Resolves

```
  User CLI                        Catalog                     Pipeline
  ─────────                       ───────                     ────────
  
  --catalog time-series-momentum
        │
        └──> get_strategy("time-series-momentum")
                    │
                    └──> Lookup in catalog/strategies.json
                              │
                              └──> StrategyEntry
                                      │
                                      ├── paper_url ──> used as pdf_url
                                      │                    │
                                      │               Pipeline Stage 1
                                      │               (Paper Parsing)
                                      │
                                      └── metadata ──> result.metadata["catalog"]
                                                       (attached to output)
```

### Step-by-Step Resolution

1. **User invokes:** `quant2repo --catalog time-series-momentum`
2. **Lookup:** `get_strategy("time-series-momentum")` searches `catalog/strategies.json`
3. **Returns:** `StrategyEntry` with full metadata
4. **Pipeline uses:** `paper_url` as the PDF URL for Stage 1
5. **Metadata attached:** catalog info stored in `result.metadata["catalog"]`

### `StrategyEntry` Dataclass

| Field            | Type          | Description                                  |
|------------------|---------------|----------------------------------------------|
| `id`             | `str`         | Unique strategy identifier (kebab-case)      |
| `title`          | `str`         | Full strategy title                          |
| `asset_classes`  | `list[str]`   | Applicable asset classes                     |
| `signal_type`    | `str`         | Signal category (momentum, value, etc.)      |
| `sharpe_ratio`   | `float`       | Reported Sharpe ratio from paper             |
| `volatility`     | `float`       | Reported annualized volatility               |
| `rebalancing`    | `str`         | Rebalancing frequency                        |
| `paper_url`      | `str`         | URL to the paper PDF                         |
| `ssrn_id`        | `str`         | SSRN paper ID (if applicable)                |
| `authors`        | `list[str]`   | Paper authors                                |
| `year`           | `int`         | Publication year                             |
| `description`    | `str`         | Brief strategy description                   |

### Catalog Functions

```python
from catalog import (
    list_strategies,
    get_strategy,
    search,
    by_asset_class,
    by_signal_type,
    by_sharpe_range,
    by_rebalancing,
    filter_strategies,
)
```

| Function                          | Returns               | Description                            |
|-----------------------------------|-----------------------|----------------------------------------|
| `list_strategies()`              | `list[StrategyEntry]` | All 47 strategies in the catalog       |
| `get_strategy(id)`               | `StrategyEntry`       | Single strategy by exact ID            |
| `search(query)`                  | `list[StrategyEntry]` | Fuzzy search using `SequenceMatcher`   |
| `by_asset_class(ac)`             | `list[StrategyEntry]` | Filter by asset class                  |
| `by_signal_type(st)`             | `list[StrategyEntry]` | Filter by signal type                  |
| `by_sharpe_range(low, high)`     | `list[StrategyEntry]` | Filter by Sharpe ratio range           |
| `by_rebalancing(freq)`           | `list[StrategyEntry]` | Filter by rebalancing frequency        |
| `filter_strategies(**kwargs)`    | `list[StrategyEntry]` | Combined AND-logic filter              |

### Search Implementation

The `search()` function uses `difflib.SequenceMatcher` for fuzzy matching:

```python
from difflib import SequenceMatcher

def search(query: str) -> list[StrategyEntry]:
    """
    Fuzzy search across strategy titles, descriptions, and IDs.
    Returns strategies sorted by match score (descending).
    """
    results = []
    for strategy in all_strategies:
        score = max(
            SequenceMatcher(None, query.lower(), strategy.id.lower()).ratio(),
            SequenceMatcher(None, query.lower(), strategy.title.lower()).ratio(),
            SequenceMatcher(None, query.lower(), strategy.description.lower()).ratio(),
        )
        if score > 0.4:  # minimum match threshold
            results.append((score, strategy))
    return [s for _, s in sorted(results, key=lambda x: -x[0])]
```

### Combined Filter Example

```python
# Find all monthly-rebalanced equity momentum strategies with Sharpe > 0.5
results = filter_strategies(
    asset_class="equities",
    signal_type="momentum",
    rebalancing="monthly",
    sharpe_range=(0.5, None),
)

# Returns list of matching StrategyEntry objects
for s in results:
    print(f"{s.id}: {s.title} (Sharpe={s.sharpe_ratio})")
```

---

## 6. Pipeline Comparison Summary

### Feature Comparison: Classic vs Agent Mode

| Feature                         | Classic Mode | Agent Mode |
|---------------------------------|:------------:|:----------:|
| Paper parsing                   | Yes          | Yes        |
| Strategy extraction             | Yes          | Yes        |
| Decomposed planning             | Yes          | Yes        |
| Self-refine on plans            | No           | Yes        |
| Interactive plan approval       | No           | Yes        |
| Per-file analysis               | No           | Yes        |
| CodeRAG (GitHub mining)         | No           | Yes        |
| Context manager                 | No           | Yes        |
| Parallel code generation        | Yes          | Yes        |
| Test generation                 | No           | Yes        |
| Code validation                 | Yes          | Yes        |
| Auto-fix                        | Yes          | Yes        |
| Backtest bias checks (static)   | No           | Yes        |
| Backtest bias checks (LLM)      | No           | Yes        |
| Docker execution                | No           | Yes        |
| Local execution                 | No           | Yes        |
| Auto-debug                      | No           | Yes        |
| DevOps generation               | No           | Yes        |
| Reference evaluation            | No           | Yes        |
| Strategy catalog support        | Yes          | Yes        |

### Performance Characteristics

| Metric                    | Classic Mode     | Agent Mode         |
|---------------------------|------------------|--------------------|
| **Total stages**          | 6                | 12                 |
| **LLM calls (typical)**  | 10-15            | 40-80              |
| **Wall-clock time**       | 2-5 minutes      | 10-30 minutes      |
| **Output files**          | ~9               | ~15-20             |
| **Refinement loops**      | 1 (validation)   | 3+ (plan, code, exec) |
| **Bias detection**        | Basic            | Comprehensive      |
| **Execution verification**| None             | Docker/local       |

### When to Use Each Mode

```
  Use CLASSIC mode when:
  ┌────────────────────────────────────────────┐
  │  - Quick prototype needed                  │
  │  - Simple strategy (single signal)         │
  │  - Limited LLM budget                      │
  │  - No Docker available                     │
  │  - Iterating rapidly on paper selection    │
  └────────────────────────────────────────────┘

  Use AGENT mode when:
  ┌────────────────────────────────────────────┐
  │  - Production-quality output needed        │
  │  - Complex strategy (multiple signals)     │
  │  - Bias-free implementation required       │
  │  - Need executable, tested code            │
  │  - Want CI/CD and Docker setup             │
  │  - Evaluating against paper benchmarks     │
  └────────────────────────────────────────────┘
```

### Data Flow Summary

```
                       CLASSIC MODE
  ┌──────────────────────────────────────────────────┐
  │                                                    │
  │  PDF ──> ParsedPaper ──> StrategyExtraction       │
  │              │                   │                  │
  │              └────────┬──────────┘                  │
  │                       │                             │
  │              ArchitecturePlan                       │
  │                       │                             │
  │              Generated Files                       │
  │                       │                             │
  │              ValidationReport                      │
  │                       │                             │
  │              Output Directory                      │
  │                                                    │
  └──────────────────────────────────────────────────┘

                        AGENT MODE
  ┌──────────────────────────────────────────────────┐
  │                                                    │
  │  PDF ──> ParsedPaper ──> StrategyExtraction       │
  │              │                   │                  │
  │              └────────┬──────────┘                  │
  │                       │                             │
  │     ArchitecturePlan + RefinementResult            │
  │                       │                             │
  │     FileAnalysis[] + CodeRAG Index                 │
  │                       │                             │
  │     Generated Files (with ContextManager)          │
  │                       │                             │
  │     Test Files                                     │
  │                       │                             │
  │     ValidationReport                               │
  │                       │                             │
  │     BacktestValidationReport                       │
  │                       │                             │
  │     ExecutionResult + DebugReport[]                │
  │                       │                             │
  │     DevOps Files                                   │
  │                       │                             │
  │     EvaluationScore                                │
  │                       │                             │
  │     Output Directory                               │
  │                                                    │
  └──────────────────────────────────────────────────┘
```

---

> **Next:** [Configuration Reference](Configuration-Reference) |
> **Previous:** [Architecture Overview](Architecture-Overview) |
> **Home:** [Wiki Home](Home)
