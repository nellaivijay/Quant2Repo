"""Per-file deep analysis for backtest code generation.

Analyzes each file in the planned architecture before code generation,
producing detailed specifications including classes, functions, imports,
algorithms, I/O specs, test criteria, and quant-specific metadata.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FileAnalysis:
    """Detailed specification for a single generated file.

    Attributes:
        file_path: Path of the file within the generated repository.
        classes: List of class specs, each a dict with keys:
            name, attributes, methods, base_classes.
        functions: List of function specs, each a dict with keys:
            name, args, return_type, description.
        imports: Required import statements.
        dependencies: Other project files this file depends on.
        algorithms: Ordered algorithmic steps derived from the paper.
        input_output_spec: Dict describing expected inputs and outputs
            (e.g. DataFrame columns, config keys, return types).
        test_criteria: List of conditions that should be tested.
        quant_specific: Quant-domain metadata such as signal_type,
            lookback_period, rebalance_frequency, etc.
    """

    file_path: str = ""
    classes: List[Dict[str, Any]] = field(default_factory=list)
    functions: List[Dict[str, Any]] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    algorithms: List[str] = field(default_factory=list)
    input_output_spec: Dict[str, Any] = field(default_factory=dict)
    test_criteria: List[str] = field(default_factory=list)
    quant_specific: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "file_path": self.file_path,
            "classes": self.classes,
            "functions": self.functions,
            "imports": self.imports,
            "dependencies": self.dependencies,
            "algorithms": self.algorithms,
            "input_output_spec": self.input_output_spec,
            "test_criteria": self.test_criteria,
            "quant_specific": self.quant_specific,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FileAnalysis":
        """Construct a ``FileAnalysis`` from a plain dictionary."""
        return cls(
            file_path=data.get("file_path", ""),
            classes=data.get("classes", []),
            functions=data.get("functions", []),
            imports=data.get("imports", []),
            dependencies=data.get("dependencies", []),
            algorithms=data.get("algorithms", []),
            input_output_spec=data.get("input_output_spec", {}),
            test_criteria=data.get("test_criteria", []),
            quant_specific=data.get("quant_specific", {}),
        )


class FileAnalyzer:
    """Analyzes each file in the backtest plan before code generation.

    For every ``.py`` file in the architecture plan the analyzer calls the
    LLM provider once and produces a :class:`FileAnalysis` containing
    classes, functions, algorithms, and quant-specific metadata.  Earlier
    analyses are fed as context to later ones so that interfaces remain
    consistent across the repository.

    Parameters:
        provider: An LLM provider instance (must expose ``generate`` and
            optionally ``generate_structured``).
        config: Optional configuration dict for tuning behaviour.
    """

    # Maximum number of prior analyses to include as context.
    _MAX_PRIOR_CONTEXT: int = 5
    # Maximum character budget for the paper excerpt.
    _PAPER_BUDGET: int = 15_000
    # Maximum character budget for prior-analysis context.
    _PRIOR_BUDGET: int = 5_000

    def __init__(self, provider: Any, config: Optional[Dict[str, Any]] = None) -> None:
        self.provider = provider
        self.config = config or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_all(
        self,
        architecture_plan: Any,
        paper_text: str,
        strategy_extraction: dict,
    ) -> Dict[str, FileAnalysis]:
        """Analyze every ``.py`` file in *architecture_plan*.

        Files are processed in plan order so that each analysis can
        reference the results of previously analyzed files.

        Args:
            architecture_plan: An ``ArchitecturePlan`` (or duck-typed
                object) whose ``.files`` attribute is a list of dicts
                with at least ``path`` and ``description`` keys.
            paper_text: Full or abridged text extracted from the paper.
            strategy_extraction: Dict produced by
                :class:`StrategyExtractor`.

        Returns:
            Mapping of file path → :class:`FileAnalysis`.
        """
        analyses: Dict[str, FileAnalysis] = {}
        prior_analyses: List[FileAnalysis] = []

        for file_info in architecture_plan.files:
            path = file_info.get("path", "")
            if not path.endswith(".py"):
                continue

            logger.info("Analyzing %s", path)
            analysis = self.analyze_file(
                file_info, paper_text, strategy_extraction, prior_analyses
            )
            analyses[path] = analysis
            prior_analyses.append(analysis)

        return analyses

    def analyze_file(
        self,
        file_info: Dict[str, Any],
        paper_text: str,
        strategy_extraction: dict,
        prior_analyses: List[FileAnalysis],
    ) -> FileAnalysis:
        """Produce a :class:`FileAnalysis` for a single file.

        Args:
            file_info: Dict describing the file (``path``,
                ``description``, …).
            paper_text: Paper text excerpt.
            strategy_extraction: Strategy extraction dict.
            prior_analyses: Analyses of previously processed files (used
                as context to maintain interface consistency).

        Returns:
            A fully populated :class:`FileAnalysis`.
        """
        prompt = self._build_prompt(
            file_info, paper_text, strategy_extraction, prior_analyses
        )

        from providers.base import GenerationConfig

        config = GenerationConfig(
            temperature=0.1,
            max_output_tokens=4096,
            response_format="json",
        )

        result = self._call_provider(prompt, config)

        return FileAnalysis(
            file_path=file_info.get("path", ""),
            classes=result.get("classes", []),
            functions=result.get("functions", []),
            imports=result.get("imports", []),
            dependencies=result.get("dependencies", []),
            algorithms=result.get("algorithms", []),
            input_output_spec=result.get("input_output_spec", {}),
            test_criteria=result.get("test_criteria", []),
            quant_specific=result.get("quant_specific", {}),
        )

    # ------------------------------------------------------------------
    # Provider helpers
    # ------------------------------------------------------------------

    def _call_provider(self, prompt: str, config: Any) -> Dict[str, Any]:
        """Call provider with structured output, falling back to free text."""
        schema = {
            "type": "object",
            "properties": {
                "classes": {"type": "array"},
                "functions": {"type": "array"},
                "imports": {"type": "array"},
                "dependencies": {"type": "array"},
                "algorithms": {"type": "array"},
                "input_output_spec": {"type": "object"},
                "test_criteria": {"type": "array"},
                "quant_specific": {"type": "object"},
            },
        }

        try:
            return self.provider.generate_structured(
                prompt, schema=schema, config=config
            )
        except Exception:
            logger.debug("Structured generation unavailable; falling back to free-text")

        gen_result = self.provider.generate(prompt, config=config)
        return self._extract_json(gen_result.text)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        file_info: Dict[str, Any],
        paper_text: str,
        strategy_extraction: dict,
        prior_analyses: List[FileAnalysis],
    ) -> str:
        """Build the analysis prompt, loading a template if available."""
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts",
            "file_analysis.txt",
        )

        if os.path.exists(prompt_path):
            with open(prompt_path, encoding="utf-8") as fh:
                template = fh.read()
        else:
            template = self._default_prompt()

        prior_text = self._summarize_prior_analyses(prior_analyses)

        strategy_text = ""
        if isinstance(strategy_extraction, dict):
            strategy_text = json.dumps(strategy_extraction, default=str)[
                : self._PAPER_BUDGET
            ]

        replacements: Dict[str, str] = {
            "file_path": file_info.get("path", ""),
            "file_description": file_info.get("description", ""),
            "paper_analysis": paper_text[: self._PAPER_BUDGET],
            "prior_analyses": prior_text[: self._PRIOR_BUDGET],
            "strategy_extraction": strategy_text,
        }

        for key, value in replacements.items():
            template = template.replace("{{" + key + "}}", str(value))

        return template

    def _summarize_prior_analyses(
        self, prior_analyses: List[FileAnalysis]
    ) -> str:
        """Create a compact textual summary of prior analyses."""
        parts: List[str] = []
        for pa in prior_analyses[-self._MAX_PRIOR_CONTEXT :]:
            func_names = [
                f.get("name", "") if isinstance(f, dict) else str(f)
                for f in pa.functions[:10]
            ]
            class_names = [
                c.get("name", "") if isinstance(c, dict) else str(c)
                for c in pa.classes[:5]
            ]
            parts.append(
                f"\n--- {pa.file_path} ---\n"
                f"Functions: {func_names}\n"
                f"Classes: {class_names}\n"
            )
        return "".join(parts)

    @staticmethod
    def _default_prompt() -> str:
        """Fallback prompt when no template file is present."""
        return (
            "Analyze the following file for a quantitative trading backtest "
            "repository.\n\n"
            "File: {{file_path}}\n"
            "Description: {{file_description}}\n\n"
            "Paper context:\n{{paper_analysis}}\n\n"
            "Strategy extraction:\n{{strategy_extraction}}\n\n"
            "Previously analyzed files:\n{{prior_analyses}}\n\n"
            "Return JSON with the following top-level keys:\n"
            "  classes      — list of {name, attributes, methods, base_classes}\n"
            "  functions    — list of {name, args, return_type, description}\n"
            "  imports      — list of import strings\n"
            "  dependencies — list of other project file paths this file needs\n"
            "  algorithms   — ordered list of algorithmic steps from the paper\n"
            "  input_output_spec — {inputs: ..., outputs: ...}\n"
            "  test_criteria     — list of testable conditions\n"
            "  quant_specific    — {signal_type, lookback, rebalance_freq, ...}\n"
        )

    # ------------------------------------------------------------------
    # JSON extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """Best-effort JSON extraction from free-form LLM output."""
        # 1. Direct parse
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        # 2. Fenced code block
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 3. Outermost braces
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        logger.warning("Could not extract JSON from LLM response; returning empty dict")
        return {}
