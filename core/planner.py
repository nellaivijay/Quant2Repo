"""Decomposed planner for backtest repository architecture.

4-stage planning pipeline:
1. Overall backtest plan (data, signals, portfolio, evaluation)
2. Architecture design (file structure, class diagram, module relationships)
3. Signal logic design (execution order, dependency graph, per-file specs)
4. Config generation (strategy parameters YAML)
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class OverallPlan:
    """Step 1: High-level backtest plan."""
    core_modules: list = field(default_factory=list)
    data_pipeline: list = field(default_factory=list)
    signal_generation: list = field(default_factory=list)
    portfolio_rules: list = field(default_factory=list)
    performance_evaluation: list = field(default_factory=list)
    robustness_checks: list = field(default_factory=list)
    summary: str = ""


@dataclass
class ArchitectureDesign:
    """Step 2: Repository file structure and relationships."""
    file_list: list = field(default_factory=list)  # [{path, description, module}]
    class_diagram_mermaid: str = ""
    sequence_diagram_mermaid: str = ""
    module_relationships: dict = field(default_factory=dict)


@dataclass
class LogicDesign:
    """Step 3: Execution order and per-file specifications."""
    execution_order: list = field(default_factory=list)
    dependency_graph: dict = field(default_factory=dict)
    file_specifications: dict = field(default_factory=dict)


@dataclass
class ArchitecturePlan:
    """Backward-compatible combined plan for downstream stages."""
    files: list = field(default_factory=list)  # [{path, description, priority, module}]
    class_diagram: str = ""
    sequence_diagram: str = ""
    config_content: str = ""
    summary: str = ""


@dataclass
class PlanningResult:
    """Aggregate output from all planning stages."""
    overall_plan: Optional[OverallPlan] = None
    architecture_design: Optional[ArchitectureDesign] = None
    logic_design: Optional[LogicDesign] = None
    config_content: str = ""
    combined_plan: Optional[ArchitecturePlan] = None


class DecomposedPlanner:
    """4-stage decomposed planner for backtest repositories."""

    def __init__(self, provider, config=None):
        self.provider = provider
        self.config = config

    def plan(self, paper_text: str, strategy_extraction: dict,
             refiner=None) -> PlanningResult:
        """Run all 4 planning stages."""
        result = PlanningResult()

        # Stage 1: Overall plan
        logger.info("Planning Stage 1: Overall backtest plan")
        result.overall_plan = self._step1_overall_plan(paper_text, strategy_extraction)
        if refiner:
            refined = refiner.refine(
                json.dumps(self._plan_to_dict(result.overall_plan)),
                "overall_plan", paper_text
            )
            if refined.improved:
                result.overall_plan = self._dict_to_plan(json.loads(refined.refined))

        # Stage 2: Architecture design
        logger.info("Planning Stage 2: Architecture design")
        result.architecture_design = self._step2_architecture_design(
            paper_text, strategy_extraction, result.overall_plan
        )
        if refiner:
            refined = refiner.refine(
                json.dumps(self._arch_to_dict(result.architecture_design)),
                "architecture_design", paper_text
            )
            if refined.improved:
                result.architecture_design = self._dict_to_arch(json.loads(refined.refined))

        # Stage 3: Logic design
        logger.info("Planning Stage 3: Signal logic design")
        result.logic_design = self._step3_logic_design(
            paper_text, strategy_extraction,
            result.overall_plan, result.architecture_design
        )

        # Stage 4: Config generation
        logger.info("Planning Stage 4: Config generation")
        result.config_content = self._step4_config_generation(
            paper_text, strategy_extraction, result.overall_plan
        )

        # Combine into backward-compatible plan
        result.combined_plan = self._to_architecture_plan(result)

        return result

    def _step1_overall_plan(self, paper_text: str,
                            strategy_extraction: dict) -> OverallPlan:
        """Extract high-level backtest plan from paper."""
        prompt = self._load_prompt("backtest_planner.txt", {
            "paper_analysis": paper_text[:30000],
            "strategy_extraction": json.dumps(strategy_extraction, default=str)[:10000],
        })

        from providers.base import GenerationConfig
        config = GenerationConfig(temperature=0.1, max_output_tokens=4096,
                                  response_format="json")

        try:
            result = self.provider.generate_structured(
                prompt,
                schema={
                    "type": "object",
                    "properties": {
                        "core_modules": {"type": "array", "items": {"type": "string"}},
                        "data_pipeline": {"type": "array", "items": {"type": "string"}},
                        "signal_generation": {"type": "array", "items": {"type": "string"}},
                        "portfolio_rules": {"type": "array", "items": {"type": "string"}},
                        "performance_evaluation": {"type": "array", "items": {"type": "string"}},
                        "robustness_checks": {"type": "array", "items": {"type": "string"}},
                        "summary": {"type": "string"},
                    },
                },
                config=config,
            )
        except Exception:
            result_text = self.provider.generate(prompt, config=config)
            result = self._extract_json(result_text.text)

        return OverallPlan(
            core_modules=result.get("core_modules", []),
            data_pipeline=result.get("data_pipeline", []),
            signal_generation=result.get("signal_generation", []),
            portfolio_rules=result.get("portfolio_rules", []),
            performance_evaluation=result.get("performance_evaluation", []),
            robustness_checks=result.get("robustness_checks", []),
            summary=result.get("summary", ""),
        )

    def _step2_architecture_design(self, paper_text: str,
                                   strategy_extraction: dict,
                                   overall_plan: OverallPlan) -> ArchitectureDesign:
        """Design repository file structure."""
        prompt = self._load_prompt("architecture_design.txt", {
            "paper_analysis": paper_text[:20000],
            "strategy_extraction": json.dumps(strategy_extraction, default=str)[:8000],
            "overall_plan": json.dumps(self._plan_to_dict(overall_plan))[:5000],
        })

        from providers.base import GenerationConfig
        config = GenerationConfig(temperature=0.1, max_output_tokens=6144,
                                  response_format="json")

        try:
            result = self.provider.generate_structured(prompt, schema={
                "type": "object",
                "properties": {
                    "file_list": {"type": "array"},
                    "class_diagram_mermaid": {"type": "string"},
                    "sequence_diagram_mermaid": {"type": "string"},
                    "module_relationships": {"type": "object"},
                },
            }, config=config)
        except Exception:
            result_text = self.provider.generate(prompt, config=config)
            result = self._extract_json(result_text.text)

        return ArchitectureDesign(
            file_list=result.get("file_list", self._default_file_list()),
            class_diagram_mermaid=result.get("class_diagram_mermaid", ""),
            sequence_diagram_mermaid=result.get("sequence_diagram_mermaid", ""),
            module_relationships=result.get("module_relationships", {}),
        )

    def _step3_logic_design(self, paper_text: str,
                            strategy_extraction: dict,
                            overall_plan: OverallPlan,
                            arch_design: ArchitectureDesign) -> LogicDesign:
        """Determine execution order and per-file specifications."""
        prompt = self._load_prompt("signal_logic.txt", {
            "paper_analysis": paper_text[:20000],
            "strategy_extraction": json.dumps(strategy_extraction, default=str)[:8000],
            "architecture_design": json.dumps(self._arch_to_dict(arch_design))[:5000],
        })

        from providers.base import GenerationConfig
        config = GenerationConfig(temperature=0.1, max_output_tokens=6144,
                                  response_format="json")

        try:
            result = self.provider.generate_structured(prompt, schema={
                "type": "object",
                "properties": {
                    "execution_order": {"type": "array"},
                    "dependency_graph": {"type": "object"},
                    "file_specifications": {"type": "object"},
                },
            }, config=config)
        except Exception:
            result_text = self.provider.generate(prompt, config=config)
            result = self._extract_json(result_text.text)

        return LogicDesign(
            execution_order=result.get("execution_order",
                                       [f["path"] for f in arch_design.file_list]),
            dependency_graph=result.get("dependency_graph", {}),
            file_specifications=result.get("file_specifications", {}),
        )

    def _step4_config_generation(self, paper_text: str,
                                 strategy_extraction: dict,
                                 overall_plan: OverallPlan) -> str:
        """Generate strategy configuration YAML."""
        prompt = f"""Generate a Python configuration file (config.py) for the following
quantitative trading strategy. Include ALL hyperparameters from the paper as named constants.

Strategy: {json.dumps(strategy_extraction, default=str)[:5000]}
Plan: {json.dumps(self._plan_to_dict(overall_plan))[:3000]}

The config.py should include:
- Strategy name and description
- Asset universe definition (tickers or asset class)
- Date range (start_date, end_date)
- Signal parameters (lookback periods, formation periods, skip periods)
- Portfolio parameters (number of quantiles, weighting scheme, rebalancing frequency)
- Transaction cost assumptions
- Risk parameters
- Output settings

Use Python dataclasses or simple constants. Make every parameter from the paper configurable.
Return ONLY the Python code, no markdown."""

        from providers.base import GenerationConfig
        config = GenerationConfig(temperature=0.15, max_output_tokens=4096)
        result = self.provider.generate(prompt, config=config)
        return self._clean_code(result.text)

    def _to_architecture_plan(self, result: PlanningResult) -> ArchitecturePlan:
        """Convert to backward-compatible ArchitecturePlan."""
        files = []
        if result.architecture_design:
            for i, f in enumerate(result.architecture_design.file_list):
                files.append({
                    "path": f.get("path", f"file_{i}.py"),
                    "description": f.get("description", ""),
                    "priority": i,
                    "module": f.get("module", "core"),
                })

        if result.logic_design and result.logic_design.execution_order:
            path_to_priority = {
                path: i for i, path in enumerate(result.logic_design.execution_order)
            }
            for f in files:
                f["priority"] = path_to_priority.get(f["path"], f["priority"])
            files.sort(key=lambda f: f["priority"])

        return ArchitecturePlan(
            files=files,
            class_diagram=result.architecture_design.class_diagram_mermaid
            if result.architecture_design else "",
            sequence_diagram=result.architecture_design.sequence_diagram_mermaid
            if result.architecture_design else "",
            config_content=result.config_content,
            summary=result.overall_plan.summary if result.overall_plan else "",
        )

    def _default_file_list(self) -> list:
        """Default backtest repo file structure."""
        return [
            {"path": "config.py", "description": "Strategy parameters and configuration",
             "module": "config"},
            {"path": "data_loader.py", "description": "Data fetching and preprocessing",
             "module": "data"},
            {"path": "signals.py", "description": "Signal generation and ranking",
             "module": "signals"},
            {"path": "portfolio.py", "description": "Portfolio construction and rebalancing",
             "module": "portfolio"},
            {"path": "analysis.py", "description": "Performance metrics and factor analysis",
             "module": "analysis"},
            {"path": "visualization.py", "description": "Charts and report generation",
             "module": "visualization"},
            {"path": "main.py", "description": "CLI entry point and pipeline orchestrator",
             "module": "main"},
            {"path": "requirements.txt", "description": "Python dependencies",
             "module": "config"},
            {"path": "README.md", "description": "Documentation",
             "module": "docs"},
        ]

    def _load_prompt(self, filename: str, replacements: dict) -> str:
        """Load and fill a prompt template."""
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "prompts", filename
        )
        if os.path.exists(prompt_path):
            with open(prompt_path) as f:
                template = f.read()
        else:
            template = f"Analyze the following and return JSON:\n{{{{paper_analysis}}}}"

        for key, value in replacements.items():
            template = template.replace("{{" + key + "}}", str(value))
        return template

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from LLM response."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        return {}

    def _clean_code(self, text: str) -> str:
        """Clean code output from LLM."""
        match = re.search(r"```(?:python)?\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            return match.group(1)
        return text

    def _plan_to_dict(self, plan: OverallPlan) -> dict:
        if not plan:
            return {}
        return {
            "core_modules": plan.core_modules,
            "data_pipeline": plan.data_pipeline,
            "signal_generation": plan.signal_generation,
            "portfolio_rules": plan.portfolio_rules,
            "performance_evaluation": plan.performance_evaluation,
            "robustness_checks": plan.robustness_checks,
            "summary": plan.summary,
        }

    def _dict_to_plan(self, d: dict) -> OverallPlan:
        return OverallPlan(**{k: d.get(k, []) for k in [
            "core_modules", "data_pipeline", "signal_generation",
            "portfolio_rules", "performance_evaluation", "robustness_checks",
        ]}, summary=d.get("summary", ""))

    def _arch_to_dict(self, arch: ArchitectureDesign) -> dict:
        if not arch:
            return {}
        return {
            "file_list": arch.file_list,
            "class_diagram_mermaid": arch.class_diagram_mermaid,
            "sequence_diagram_mermaid": arch.sequence_diagram_mermaid,
            "module_relationships": arch.module_relationships,
        }

    def _dict_to_arch(self, d: dict) -> ArchitectureDesign:
        return ArchitectureDesign(
            file_list=d.get("file_list", []),
            class_diagram_mermaid=d.get("class_diagram_mermaid", ""),
            sequence_diagram_mermaid=d.get("sequence_diagram_mermaid", ""),
            module_relationships=d.get("module_relationships", {}),
        )
