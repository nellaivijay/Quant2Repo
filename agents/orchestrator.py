"""Agent orchestrator — master controller for the Quant2Repo pipeline.

Coordinates all pipeline stages:
1. Paper parsing + strategy extraction
2. Decomposed planning (4-stage)
3. Per-file analysis
4. Code generation
5. Test generation
6. Validation + auto-fix
7. Backtest validation (bias checks)
8. Execution sandbox + auto-debug
9. DevOps generation
10. Reference evaluation
11. Save to disk
"""

import concurrent.futures
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Complete result from the orchestrator."""
    files: dict = field(default_factory=dict)
    plan: object = None
    extraction: object = None
    file_analyses: dict = field(default_factory=dict)
    validation_report: object = None
    backtest_validation: object = None
    execution_result: object = None
    evaluation_score: object = None
    metadata: dict = field(default_factory=dict)


class AgentOrchestrator:
    """Master controller for the Quant2Repo pipeline.

    Orchestrates all agents and pipeline stages for converting
    a quant paper into a backtesting repository.
    """

    DEFAULT_CONFIG = {
        "enable_refine": False,
        "enable_execution": False,
        "enable_tests": True,
        "enable_evaluation": False,
        "enable_devops": True,
        "enable_backtest_validation": True,
        "enable_code_rag": False,
        "enable_segmentation": True,
        "enable_context_manager": True,
        "interactive": False,
        "max_fix_iterations": 2,
        "max_refine_iterations": 2,
        "max_debug_iterations": 3,
        "reference_dir": "",
        "verbose": False,
    }

    def __init__(self, provider=None, config: dict = None):
        self.provider = provider
        self.config = {**self.DEFAULT_CONFIG, **(config or {})}

    def run(self, pdf_path: str = "", pdf_url: str = "",
            paper_text: str = "",
            output_dir: str = "./generated_repo",
            catalog_id: str = "") -> PipelineResult:
        """Execute the full pipeline.

        Args:
            pdf_path: Local path to PDF
            pdf_url: URL to download PDF from
            paper_text: Raw paper text (if already extracted)
            output_dir: Where to save generated files
            catalog_id: Strategy ID from catalog (auto-fills metadata)
        """
        start_time = time.time()
        result = PipelineResult()
        result.metadata["start_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
        result.metadata["config"] = dict(self.config)

        # Initialize pipeline cache for reuse across runs
        cache = None
        try:
            from advanced.cache import PipelineCache
            cache_dir = self.config.get("cache_dir", ".q2r_cache")
            cache = PipelineCache(cache_dir)
        except (ImportError, Exception):
            pass

        # Resolve catalog entry if provided
        catalog_metadata = {}
        if catalog_id:
            catalog_metadata = self._resolve_catalog(catalog_id)
            result.metadata["catalog"] = catalog_metadata

        # === Stage 1: Paper Parsing ===
        print("\n=== Stage 1/11: Paper Parsing ===")
        paper_text, parsed_paper = self._stage_parse_paper(
            pdf_path, pdf_url, paper_text
        )
        result.metadata["paper_title"] = getattr(parsed_paper, "title", "") if parsed_paper else ""

        # === Stage 2: Strategy Extraction ===
        print("\n=== Stage 2/11: Strategy Extraction ===")
        extraction = self._stage_extract_strategy(paper_text)
        result.extraction = extraction
        result.metadata["strategy_name"] = extraction.strategy_name

        # Convert to dict for downstream
        extraction_dict = self._extraction_to_dict(extraction)

        # === Stage 3: Decomposed Planning ===
        print("\n=== Stage 3/11: Decomposed Planning ===")
        refiner = None
        if self.config["enable_refine"]:
            from core.refiner import SelfRefiner
            refiner = SelfRefiner(self.provider,
                                  max_iterations=self.config["max_refine_iterations"])

        planning_result = self._stage_plan(paper_text, extraction_dict, refiner)
        result.plan = planning_result.combined_plan

        # Interactive pause
        if self.config["interactive"]:
            self._interactive_review(planning_result)

        # === Stage 4: Per-File Analysis ===
        # === Stage 4b: CodeRAG (optional) — run in parallel with Stage 4 ===
        print("\n=== Stage 4/11: Per-File Analysis ===")
        code_rag_index = None
        bg_futures = {}

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        try:
            # Launch CodeRAG in background while file analysis runs
            if self.config["enable_code_rag"]:
                bg_futures["code_rag"] = executor.submit(
                    self._stage_code_rag, extraction_dict, planning_result
                )

            # File analysis runs in foreground
            file_analyses = self._stage_file_analysis(
                planning_result.combined_plan, paper_text, extraction_dict
            )
            result.file_analyses = file_analyses

            # Collect CodeRAG result
            if "code_rag" in bg_futures:
                print("\n=== Stage 4b: CodeRAG (Reference Mining) ===")
                code_rag_index = bg_futures["code_rag"].result()
        finally:
            executor.shutdown(wait=False)

        # === Stage 5: Code Generation ===
        print("\n=== Stage 5/11: Code Generation ===")
        context_manager = None
        if self.config["enable_context_manager"]:
            from advanced.context_manager import ContextManager
            context_manager = ContextManager(
                self.provider, planning_result.combined_plan,
                code_rag_index=code_rag_index
            )

        generated_files = self._stage_code_generation(
            planning_result.combined_plan, paper_text, extraction_dict,
            file_analyses, context_manager
        )

        # Add config from planning if not already generated
        if "config.py" not in generated_files and planning_result.config_content:
            generated_files["config.py"] = planning_result.config_content

        # === Stage 6: Test Generation (optional) ===
        if self.config["enable_tests"]:
            print("\n=== Stage 6/11: Test Generation ===")
            test_files = self._stage_test_generation(
                generated_files, paper_text, extraction_dict
            )
            generated_files.update(test_files)

        # === Stage 7: Validation + Auto-Fix ===
        print("\n=== Stage 7/11: Validation ===")
        generated_files, validation_report = self._stage_validation(
            generated_files, paper_text, extraction_dict
        )
        result.validation_report = validation_report

        # === Stage 8: Backtest Validation (bias checks) ===
        if self.config["enable_backtest_validation"]:
            print("\n=== Stage 8/11: Backtest Validation ===")
            bt_report = self._stage_backtest_validation(
                generated_files, extraction_dict
            )
            result.backtest_validation = bt_report

        # === Stage 9: Execution + Auto-Debug (optional) ===
        if self.config["enable_execution"]:
            print("\n=== Stage 9/11: Execution Sandbox ===")
            generated_files, exec_result = self._stage_execution(
                generated_files, output_dir
            )
            result.execution_result = exec_result

        # === Stage 10: DevOps Generation (optional) ===
        if self.config["enable_devops"]:
            print("\n=== Stage 10/11: DevOps Generation ===")
            devops_files = self._stage_devops(
                planning_result.combined_plan, extraction_dict, generated_files
            )
            generated_files.update(devops_files)

        # === Stage 11: Evaluation (optional) ===
        if self.config["enable_evaluation"]:
            print("\n=== Stage 11/11: Reference Evaluation ===")
            eval_score = self._stage_evaluation(
                generated_files, paper_text, extraction_dict
            )
            result.evaluation_score = eval_score

        # === Save Files ===
        print(f"\n=== Saving to {output_dir} ===")
        self._save_files(generated_files, output_dir)
        result.files = generated_files

        elapsed = time.time() - start_time
        result.metadata["elapsed_seconds"] = round(elapsed, 1)
        result.metadata["files_generated"] = len(generated_files)

        # Save metadata
        metadata_path = os.path.join(output_dir, "q2r_metadata.json")
        with open(metadata_path, "w") as f:
            json.dump(result.metadata, f, indent=2, default=str)

        print(f"\nDone! Generated {len(generated_files)} files in {elapsed:.1f}s")
        return result

    # --- Stage implementations ---

    def _stage_parse_paper(self, pdf_path, pdf_url, paper_text):
        if paper_text:
            return paper_text, None

        from core.paper_parser import PaperParser, download_pdf

        if pdf_url:
            pdf_path = download_pdf(pdf_url)

        if not pdf_path:
            raise ValueError("Provide pdf_path, pdf_url, or paper_text")

        parser = PaperParser()
        parsed = parser.parse(pdf_path)
        print(f"  Parsed: {parsed.title or 'Untitled'} ({parsed.page_count} pages)")
        return parsed.get_text_for_analysis(), parsed

    def _stage_extract_strategy(self, paper_text):
        from core.strategy_extractor import StrategyExtractor
        extractor = StrategyExtractor(self.provider)
        extraction = extractor.extract(paper_text)
        print(f"  Strategy: {extraction.strategy_name}")
        print(f"  Asset classes: {extraction.asset_classes}")
        print(f"  Signals: {[s.signal_type for s in extraction.signals]}")
        return extraction

    def _stage_plan(self, paper_text, extraction_dict, refiner):
        from core.planner import DecomposedPlanner
        planner = DecomposedPlanner(self.provider)
        result = planner.plan(paper_text, extraction_dict, refiner=refiner)
        print(f"  Files planned: {len(result.combined_plan.files)}")
        for f in result.combined_plan.files:
            print(f"    {f['path']}: {f.get('description', '')[:60]}")
        return result

    def _stage_file_analysis(self, plan, paper_text, extraction_dict):
        from core.file_analyzer import FileAnalyzer
        analyzer = FileAnalyzer(self.provider)
        analyses = analyzer.analyze_all(plan, paper_text, extraction_dict)
        print(f"  Analyzed {len(analyses)} files")
        return analyses

    def _stage_code_rag(self, extraction_dict, planning_result):
        try:
            from advanced.code_rag import CodeRAG
            rag = CodeRAG(self.provider)
            index = rag.build_index(extraction_dict, planning_result.combined_plan)
            print(f"  Indexed {index.total_files_indexed} files from "
                  f"{index.repos_searched} repos")
            return index
        except Exception as e:
            logger.warning(f"CodeRAG failed: {e}")
            return None

    def _stage_code_generation(self, plan, paper_text, extraction_dict,
                                file_analyses, context_manager):
        from core.coder import CodeSynthesizer
        coder = CodeSynthesizer(self.provider)
        files = coder.generate_codebase(
            plan, paper_text, extraction_dict,
            file_analyses=file_analyses,
            context_manager=context_manager,
        )
        print(f"  Generated {len(files)} files")
        return files

    def _stage_test_generation(self, generated_files, paper_text, extraction_dict):
        try:
            from advanced.test_generator import TestGenerator
            gen = TestGenerator(self.provider)
            tests = gen.generate(generated_files, paper_text, extraction_dict)
            print(f"  Generated {len(tests)} test files")
            return tests
        except Exception as e:
            logger.warning(f"Test generation failed: {e}")
            return {}

    def _stage_validation(self, generated_files, paper_text, extraction_dict):
        from core.validator import CodeValidator
        validator = CodeValidator(self.provider)
        report = validator.validate(generated_files, paper_text, extraction_dict)
        print(f"  Score: {report.score}/100, Critical: {report.critical_count}, "
              f"Warnings: {report.warning_count}")

        if not report.passed:
            for i in range(self.config["max_fix_iterations"]):
                print(f"  Auto-fix iteration {i+1}")
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

        return generated_files, report

    def _stage_backtest_validation(self, generated_files, extraction_dict):
        try:
            from advanced.backtest_validator import BacktestValidator
            validator = BacktestValidator(self.provider)
            report = validator.validate(generated_files, extraction_dict)
            print(f"  Bias risk: {report.bias_risk_score}/100, "
                  f"Critical: {report.critical_count}")
            return report
        except Exception as e:
            logger.warning(f"Backtest validation failed: {e}")
            return None

    def _stage_execution(self, generated_files, output_dir):
        from advanced.executor import ExecutionSandbox
        from advanced.debugger import AutoDebugger

        # Save files first
        self._save_files(generated_files, output_dir)

        sandbox = ExecutionSandbox(prefer_docker=True)
        result = sandbox.execute(output_dir)

        if not result.success:
            print(f"  Execution failed ({result.error_type}), auto-debugging")
            debugger = AutoDebugger(self.provider,
                                    max_iterations=self.config["max_debug_iterations"])
            generated_files, reports = debugger.debug(
                output_dir, result, generated_files, executor=sandbox
            )
            if reports:
                result_final = reports[-1]
                print(f"  Debug resolved: {result_final.resolved}")
        else:
            print(f"  Execution succeeded ({result.duration_seconds:.1f}s)")

        return generated_files, result

    def _stage_devops(self, plan, extraction_dict, generated_files):
        try:
            from advanced.devops import DevOpsGenerator
            gen = DevOpsGenerator(self.provider)
            devops = gen.generate_all(plan, extraction_dict, generated_files)
            print(f"  Generated {len(devops)} DevOps files")
            return devops
        except Exception as e:
            logger.warning(f"DevOps generation failed: {e}")
            return {}

    def _stage_evaluation(self, generated_files, paper_text, extraction_dict):
        try:
            from advanced.evaluator import ReferenceEvaluator
            evaluator = ReferenceEvaluator(self.provider)

            if self.config["reference_dir"]:
                score = evaluator.evaluate_with_reference(
                    generated_files, self.config["reference_dir"], paper_text
                )
            else:
                paper_results = extraction_dict.get("reported_results", {})
                score = evaluator.evaluate_without_reference(
                    generated_files, paper_text, paper_results
                )

            print(f"  Score: {score.overall_score}/5, Coverage: {score.coverage}%")
            return score
        except Exception as e:
            logger.warning(f"Evaluation failed: {e}")
            return None

    # --- Utility methods ---

    def _save_files(self, files: dict, output_dir: str):
        """Save all generated files to disk."""
        os.makedirs(output_dir, exist_ok=True)
        for path, content in files.items():
            full_path = os.path.join(output_dir, path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)

    def _extraction_to_dict(self, extraction) -> dict:
        """Convert StrategyExtraction to dict for JSON serialization."""
        return {
            "strategy_name": extraction.strategy_name,
            "authors": extraction.authors,
            "publication_year": extraction.publication_year,
            "asset_classes": extraction.asset_classes,
            "signals": [
                {
                    "signal_type": s.signal_type,
                    "formula": s.formula,
                    "lookback_period": s.lookback_period,
                    "formation_period": s.formation_period,
                    "skip_period": s.skip_period,
                    "normalization": s.normalization,
                    "is_cross_sectional": s.is_cross_sectional,
                    "is_time_series": s.is_time_series,
                    "detailed_steps": s.detailed_steps,
                }
                for s in extraction.signals
            ],
            "signal_combination": extraction.signal_combination,
            "portfolio_construction": {
                "method": extraction.portfolio.method if extraction.portfolio else "",
                "long_leg": extraction.portfolio.long_leg if extraction.portfolio else "",
                "short_leg": extraction.portfolio.short_leg if extraction.portfolio else "",
                "weighting": extraction.portfolio.weighting if extraction.portfolio else "",
                "rebalancing_frequency": extraction.portfolio.rebalancing_frequency
                if extraction.portfolio else "",
                "rebalancing_lag": extraction.portfolio.rebalancing_lag
                if extraction.portfolio else "",
            } if extraction.portfolio else {},
            "universe_description": extraction.universe_description,
            "universe_filters": extraction.universe_filters,
            "data_requirements": extraction.data_requirements,
            "data_frequency": extraction.data_frequency,
            "reported_results": {
                "annual_return": extraction.reported_results.annual_return,
                "annual_volatility": extraction.reported_results.annual_volatility,
                "sharpe_ratio": extraction.reported_results.sharpe_ratio,
                "max_drawdown": extraction.reported_results.max_drawdown,
                "t_statistic": extraction.reported_results.t_statistic,
                "sample_period": extraction.reported_results.sample_period,
                "benchmark": extraction.reported_results.benchmark,
            } if extraction.reported_results else {},
            "robustness_tests": extraction.robustness_tests,
            "transaction_cost_assumptions": extraction.transaction_cost_assumptions,
            "key_equations": extraction.key_equations,
            "risk_model": extraction.risk_model,
        }

    def _resolve_catalog(self, catalog_id: str) -> dict:
        """Look up strategy metadata from catalog."""
        try:
            from quant.catalog import StrategyCatalog
            catalog = StrategyCatalog()
            entry = catalog.get_strategy(catalog_id)
            if entry:
                return {
                    "id": entry.id,
                    "title": entry.title,
                    "asset_classes": entry.asset_classes,
                    "sharpe_ratio": entry.sharpe_ratio,
                    "paper_url": entry.paper_url,
                }
        except Exception as e:
            logger.warning(f"Catalog lookup failed: {e}")
        return {}

    def _interactive_review(self, planning_result):
        """Pause for user review of the plan."""
        plan = planning_result.combined_plan
        print("\n--- Architecture Plan ---")
        for f in plan.files:
            print(f"  {f['path']}: {f.get('description', '')}")
        if plan.class_diagram:
            print(f"\nClass Diagram:\n{plan.class_diagram[:500]}")
        print("\nPress Enter to continue or Ctrl+C to abort...")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            raise SystemExit("Aborted by user")
