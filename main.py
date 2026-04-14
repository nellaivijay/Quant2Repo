#!/usr/bin/env python3
"""Quant2Repo — Convert quantitative finance papers into backtesting repositories.

Multi-model agentic framework inspired by Research2Repo, adapted for
quantitative finance and systematic trading strategies.

Usage:
    # From paper URL (SSRN, arXiv, direct PDF)
    python main.py --pdf_url "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975"

    # From local PDF
    python main.py --pdf_path ./papers/momentum.pdf

    # From strategy catalog
    python main.py --catalog time-series-momentum

    # Agent mode with all features
    python main.py --pdf_url "..." --mode agent --refine --execute

    # List catalog strategies
    python main.py --list-catalog

    # Search catalog
    python main.py --search-catalog "momentum"
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("quant2repo")


def run_classic(pdf_url: str = "", pdf_path: str = "",
                output_dir: str = "./generated_repo",
                provider_name: str = None, model_name: str = None,
                skip_validation: bool = False, skip_tests: bool = False,
                max_fix_iterations: int = 2, verbose: bool = False,
                catalog_id: str = ""):
    """Classic pipeline mode (linear, v1.0 compatible).

    PDF -> Analyze -> Plan -> Generate -> Validate -> Save
    """
    from config import Q2RConfig
    from providers.registry import get_provider
    from core.paper_parser import PaperParser, download_pdf
    from core.strategy_extractor import StrategyExtractor
    from core.planner import DecomposedPlanner
    from core.coder import CodeSynthesizer
    from core.validator import CodeValidator

    config = Q2RConfig.from_env()
    if verbose:
        config.verbose = True
        logging.getLogger().setLevel(logging.DEBUG)

    # Get provider
    provider = get_provider(provider_name=provider_name, model_name=model_name)
    print(f"Using provider: {provider.__class__.__name__} ({provider.default_model})")

    start_time = time.time()

    # Stage 1: Get paper text
    print("\n[1/6] Parsing paper...")
    paper_text = ""
    if pdf_url:
        pdf_path = download_pdf(pdf_url)
    if pdf_path:
        parser = PaperParser()
        parsed = parser.parse(pdf_path)
        paper_text = parsed.get_text_for_analysis()
        print(f"  Title: {parsed.title or 'Unknown'}")
        print(f"  Pages: {parsed.page_count}")

    if not paper_text:
        print("Error: No paper text available")
        sys.exit(1)

    # Stage 2: Extract strategy
    print("\n[2/6] Extracting strategy...")
    extractor = StrategyExtractor(provider, config)
    extraction = extractor.extract(paper_text)
    print(f"  Strategy: {extraction.strategy_name}")
    print(f"  Asset classes: {extraction.asset_classes}")
    print(f"  Signals: {[s.signal_type for s in extraction.signals]}")

    extraction_dict = _extraction_to_dict(extraction)

    # Stage 3: Plan architecture
    print("\n[3/6] Planning architecture...")
    planner = DecomposedPlanner(provider, config)
    planning = planner.plan(paper_text, extraction_dict)
    plan = planning.combined_plan
    print(f"  Files: {len(plan.files)}")

    # Stage 4: Generate code
    print("\n[4/6] Generating code...")
    coder = CodeSynthesizer(provider, config)
    generated_files = coder.generate_codebase(plan, paper_text, extraction_dict)

    if planning.config_content and "config.py" not in generated_files:
        generated_files["config.py"] = planning.config_content

    print(f"  Generated {len(generated_files)} files")

    # Stage 5: Validate
    if not skip_validation:
        print("\n[5/6] Validating...")
        validator = CodeValidator(provider, config)
        report = validator.validate(generated_files, paper_text, extraction_dict)
        print(f"  Score: {report.score}/100")

        if not report.passed:
            for i in range(max_fix_iterations):
                print(f"  Auto-fix iteration {i+1}...")
                generated_files = validator.fix_issues(
                    generated_files, report, paper_text
                )
                # Only re-validate if files were actually changed
                if not validator._last_fixed_paths:
                    print(f"  No files changed, stopping fix loop")
                    break
                report = validator.validate(
                    generated_files, paper_text, extraction_dict
                )
                print(f"  Score: {report.score}/100")
                if report.passed:
                    break
    else:
        print("\n[5/6] Validation skipped")

    # Stage 6: Save
    print(f"\n[6/6] Saving to {output_dir}...")
    os.makedirs(output_dir, exist_ok=True)
    # Pre-create all needed directories in a single batch
    needed_dirs = {os.path.dirname(os.path.join(output_dir, fp))
                   for fp in generated_files}
    for d in sorted(needed_dirs):
        os.makedirs(d, exist_ok=True)
    for path, content in generated_files.items():
        full_path = os.path.join(output_dir, path)
        with open(full_path, "w") as f:
            f.write(content)

    elapsed = time.time() - start_time
    print(f"\nDone! {len(generated_files)} files in {elapsed:.1f}s -> {output_dir}")


def run_agent(pdf_url: str = "", pdf_path: str = "",
              output_dir: str = "./generated_repo",
              provider_name: str = None, model_name: str = None,
              refine: bool = False, execute: bool = False,
              evaluate: bool = False, interactive: bool = False,
              no_tests: bool = False, no_devops: bool = False,
              code_rag: bool = False, no_context_manager: bool = False,
              reference_dir: str = "",
              max_refine_iterations: int = 2,
              max_debug_iterations: int = 3,
              verbose: bool = False,
              catalog_id: str = ""):
    """Agent pipeline mode (multi-agent orchestration)."""
    from providers.registry import get_provider
    from agents.orchestrator import AgentOrchestrator

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    provider = get_provider(provider_name=provider_name, model_name=model_name)
    print(f"Using provider: {provider.__class__.__name__} ({provider.default_model})")

    config = {
        "enable_refine": refine,
        "enable_execution": execute,
        "enable_tests": not no_tests,
        "enable_evaluation": evaluate,
        "enable_devops": not no_devops,
        "enable_backtest_validation": True,
        "enable_code_rag": code_rag,
        "enable_context_manager": not no_context_manager,
        "interactive": interactive,
        "max_refine_iterations": max_refine_iterations,
        "max_debug_iterations": max_debug_iterations,
        "reference_dir": reference_dir,
        "verbose": verbose,
    }

    orchestrator = AgentOrchestrator(provider=provider, config=config)
    result = orchestrator.run(
        pdf_path=pdf_path,
        pdf_url=pdf_url,
        output_dir=output_dir,
        catalog_id=catalog_id,
    )

    # Print summary
    if result.validation_report:
        print(f"\nValidation: {result.validation_report.score}/100 "
              f"({'PASS' if result.validation_report.passed else 'FAIL'})")
    if result.backtest_validation:
        print(f"Bias risk: {result.backtest_validation.bias_risk_score}/100")
    if result.evaluation_score:
        print(f"Evaluation: {result.evaluation_score.overall_score}/5")


def list_catalog():
    """List all strategies in the catalog."""
    from quant.catalog import list_strategies

    strategies = list_strategies()

    print(f"\nQuant2Repo Strategy Catalog ({len(strategies)} strategies)")
    print("=" * 90)

    current_asset = None
    for s in sorted(strategies, key=lambda x: (str(x.asset_classes), -x.sharpe_ratio)):
        asset_key = ", ".join(sorted(s.asset_classes))
        if asset_key != current_asset:
            current_asset = asset_key
            print(f"\n--- {asset_key.upper()} ---")

        sr = f"SR={s.sharpe_ratio:+.3f}" if s.sharpe_ratio is not None else "SR=N/A"
        vol = f"Vol={s.volatility*100:.1f}%" if s.volatility else "Vol=N/A"
        print(f"  {s.id:<55} {sr:>12}  {vol:>10}  {s.rebalancing}")

    print(f"\nUsage: python main.py --catalog <strategy-id>")


def search_catalog(query: str):
    """Search the catalog."""
    from quant.catalog import search as catalog_search

    results = catalog_search(query)

    if not results:
        print(f"No strategies found matching '{query}'")
        return

    print(f"\nSearch results for '{query}' ({len(results)} matches):")
    print("-" * 90)
    for score, s in results:
        sr = f"SR={s.sharpe_ratio:+.3f}" if s.sharpe_ratio is not None else "SR=N/A"
        assets = ", ".join(s.asset_classes)
        print(f"  {s.id:<50} {sr:>12}  [{assets}]")
        if s.description:
            print(f"    {s.description[:80]}")
        if s.paper_url:
            print(f"    Paper: {s.paper_url}")
        print()


def list_providers_cmd():
    """List available providers and models."""
    from providers.registry import ProviderRegistry
    registry = ProviderRegistry()

    available = registry.detect_available()
    all_providers = registry.list_providers()

    print("\nAvailable LLM Providers:")
    print("=" * 70)
    for name in all_providers:
        status = "available" if name in available else "not configured"
        marker = "+" if name in available else "-"
        print(f"  [{marker}] {name:15} ({status})")

        if name in available:
            try:
                provider = registry.create(name)
                for model in provider.available_models():
                    caps = ", ".join(c.value for c in model.capabilities)
                    default = " (default)" if model.name == provider.default_model else ""
                    print(f"      {model.name}{default}")
                    print(f"        Context: {model.max_context_tokens:,} tokens | {caps}")
            except Exception:
                pass

    print(f"\nConfigured: {len(available)}/{len(all_providers)} providers")
    if not available:
        print("\nTo configure a provider, set the appropriate API key:")
        print("  export GEMINI_API_KEY='your_key'       # Google Gemini")
        print("  export OPENAI_API_KEY='your_key'       # OpenAI")
        print("  export ANTHROPIC_API_KEY='your_key'    # Anthropic Claude")
        print("  # Or install Ollama for local models")


def _extraction_to_dict(extraction) -> dict:
    """Convert StrategyExtraction to dict."""
    return {
        "strategy_name": extraction.strategy_name,
        "authors": extraction.authors,
        "asset_classes": extraction.asset_classes,
        "signals": [
            {"signal_type": s.signal_type, "formula": s.formula,
             "lookback_period": s.lookback_period,
             "detailed_steps": s.detailed_steps}
            for s in extraction.signals
        ],
        "portfolio_construction": {
            "method": extraction.portfolio.method,
            "rebalancing_frequency": extraction.portfolio.rebalancing_frequency,
            "weighting": extraction.portfolio.weighting,
        } if extraction.portfolio else {},
        "data_requirements": extraction.data_requirements,
        "key_equations": extraction.key_equations,
        "reported_results": {
            "sharpe_ratio": extraction.reported_results.sharpe_ratio,
            "annual_return": extraction.reported_results.annual_return,
            "annual_volatility": extraction.reported_results.annual_volatility,
        } if extraction.reported_results else {},
        "robustness_tests": extraction.robustness_tests,
        "transaction_cost_assumptions": extraction.transaction_cost_assumptions,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Quant2Repo: Convert quant papers into backtesting repos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # From SSRN paper
  python main.py --pdf_url "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1079975"

  # From local PDF
  python main.py --pdf_path ./paper.pdf

  # From catalog with agent mode
  python main.py --catalog time-series-momentum --mode agent --refine

  # List available strategies
  python main.py --list-catalog

  # Search strategies
  python main.py --search-catalog "momentum"
        """,
    )

    # Input sources
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument("--pdf_url", type=str, help="URL of the research paper PDF")
    input_group.add_argument("--pdf_path", type=str, help="Path to a local PDF file")
    input_group.add_argument("--catalog", type=str, help="Strategy ID from catalog")

    # Mode
    parser.add_argument("--mode", choices=["classic", "agent"], default="classic",
                        help="Pipeline mode (default: classic)")

    # Provider
    parser.add_argument("--provider", type=str, help="LLM provider (gemini/openai/anthropic/ollama)")
    parser.add_argument("--model", type=str, help="Specific model name")

    # Output
    parser.add_argument("--output_dir", type=str, default="./generated_repo",
                        help="Output directory (default: ./generated_repo)")

    # Classic options
    parser.add_argument("--skip-validation", action="store_true", help="Skip validation pass")
    parser.add_argument("--skip-tests", action="store_true", help="Skip test generation")
    parser.add_argument("--max-fix-iterations", type=int, default=2,
                        help="Max auto-fix attempts (default: 2)")

    # Agent options
    parser.add_argument("--refine", action="store_true", help="Enable self-refine loops")
    parser.add_argument("--execute", action="store_true", help="Enable execution sandbox")
    parser.add_argument("--evaluate", action="store_true", help="Enable reference evaluation")
    parser.add_argument("--interactive", action="store_true", help="Pause after planning")
    parser.add_argument("--no-tests", action="store_true", help="Disable test generation")
    parser.add_argument("--no-devops", action="store_true", help="Disable DevOps generation")
    parser.add_argument("--code-rag", action="store_true", help="Enable CodeRAG reference mining")
    parser.add_argument("--no-context-manager", action="store_true",
                        help="Disable context manager")
    parser.add_argument("--reference-dir", type=str, default="",
                        help="Reference implementation for evaluation")
    parser.add_argument("--max-refine-iterations", type=int, default=2)
    parser.add_argument("--max-debug-iterations", type=int, default=3)

    # Catalog commands
    parser.add_argument("--list-catalog", action="store_true", help="List catalog strategies")
    parser.add_argument("--search-catalog", type=str, help="Search catalog")

    # Misc
    parser.add_argument("--list-providers", action="store_true",
                        help="Show available providers")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Handle utility commands
    if args.list_catalog:
        list_catalog()
        return
    if args.search_catalog:
        search_catalog(args.search_catalog)
        return
    if args.list_providers:
        list_providers_cmd()
        return

    # Resolve catalog entry
    pdf_url = args.pdf_url or ""
    pdf_path = args.pdf_path or ""
    catalog_id = args.catalog or ""

    if catalog_id:
        from quant.catalog import get_strategy
        entry = get_strategy(catalog_id)
        if not entry:
            print(f"Strategy '{catalog_id}' not found in catalog")
            print("Use --list-catalog to see available strategies")
            sys.exit(1)
        if entry.paper_url and not pdf_url:
            pdf_url = entry.paper_url
            print(f"Catalog: {entry.title}")
            print(f"Paper: {pdf_url}")

    if not pdf_url and not pdf_path and not catalog_id:
        parser.print_help()
        print("\nError: Provide --pdf_url, --pdf_path, or --catalog")
        sys.exit(1)

    # Run pipeline
    print(f"\n{'='*60}")
    print(f"  Quant2Repo v1.0 — Paper to Backtest Pipeline")
    print(f"  Mode: {args.mode}")
    print(f"{'='*60}")

    if args.mode == "agent":
        run_agent(
            pdf_url=pdf_url,
            pdf_path=pdf_path,
            output_dir=args.output_dir,
            provider_name=args.provider,
            model_name=args.model,
            refine=args.refine,
            execute=args.execute,
            evaluate=args.evaluate,
            interactive=args.interactive,
            no_tests=args.no_tests,
            no_devops=args.no_devops,
            code_rag=args.code_rag,
            no_context_manager=args.no_context_manager,
            reference_dir=args.reference_dir,
            max_refine_iterations=args.max_refine_iterations,
            max_debug_iterations=args.max_debug_iterations,
            verbose=args.verbose,
            catalog_id=catalog_id,
        )
    else:
        run_classic(
            pdf_url=pdf_url,
            pdf_path=pdf_path,
            output_dir=args.output_dir,
            provider_name=args.provider,
            model_name=args.model,
            skip_validation=args.skip_validation,
            skip_tests=args.skip_tests,
            max_fix_iterations=args.max_fix_iterations,
            verbose=args.verbose,
            catalog_id=catalog_id,
        )


if __name__ == "__main__":
    # Gateway mode: when JOB_ID env var is set, run via the gateway adapter
    # instead of the CLI. This enables Quant2Repo to work both as a
    # standalone tool and as a managed engine behind Any2Repo-Gateway.
    from gateway_adapter import is_gateway_mode
    if is_gateway_mode():
        from gateway_adapter import run_gateway_mode
        run_gateway_mode()  # does not return (calls sys.exit)

    main()
