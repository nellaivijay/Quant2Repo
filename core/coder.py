"""Code synthesizer — generates backtest code file by file.

Produces Python source (and supporting files such as ``requirements.txt``,
``README.md``, and ``config.py``) for a complete backtest repository by
iterating over the architecture plan in dependency order.  Each file is
generated with full context from the paper, strategy extraction, file
analyses, and previously generated files.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Token budgets keyed by file "category".
_MAX_TOKENS: Dict[str, int] = {
    "config": 4096,
    "requirements": 4096,
    "readme": 8192,
    "default": 16384,
}


class CodeSynthesizer:
    """Generates backtest code file by file in dependency order.

    Parameters:
        provider: An LLM provider instance (must expose ``generate``).
        config: Optional configuration dict for tuning behaviour.
    """

    # Common implicit dependency map for canonical backtest file names.
    _IMPLICIT_DEPS: Dict[str, List[str]] = {
        "signals.py": ["config.py", "data_loader.py"],
        "portfolio.py": ["config.py", "signals.py"],
        "analysis.py": ["config.py", "portfolio.py"],
        "visualization.py": ["config.py", "analysis.py"],
        "main.py": ["config.py", "data_loader.py", "signals.py"],
    }

    def __init__(self, provider: Any, config: Optional[Dict[str, Any]] = None) -> None:
        self.provider = provider
        self.config = config or {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_codebase(
        self,
        architecture_plan: Any,
        paper_text: str,
        strategy_extraction: dict,
        file_analyses: Optional[dict] = None,
        context_manager: Any = None,
    ) -> Dict[str, str]:
        """Generate all files in dependency order.

        Args:
            architecture_plan: ``ArchitecturePlan`` whose ``.files`` is a
                list of dicts (``path``, ``description``, ``priority``,
                ``dependencies``).
            paper_text: Full or abridged paper text.
            strategy_extraction: Dict from :class:`StrategyExtractor`.
            file_analyses: Optional mapping of path → :class:`FileAnalysis`.
            context_manager: Optional context-manager helper that builds
                rich prompts and records generated files.

        Returns:
            Mapping of file path → generated content string.
        """
        generated: Dict[str, str] = {}
        files = sorted(
            architecture_plan.files, key=lambda f: f.get("priority", 99)
        )

        for file_info in files:
            path = file_info.get("path", "")
            logger.info("Generating %s", path)

            if context_manager is not None:
                content = self._generate_with_context_manager(
                    file_info,
                    paper_text,
                    strategy_extraction,
                    file_analyses,
                    generated,
                    context_manager,
                )
            else:
                content = self._generate_single_file(
                    file_info,
                    paper_text,
                    strategy_extraction,
                    file_analyses,
                    generated,
                )

            generated[path] = content

            if context_manager is not None:
                context_manager.record_file(path, content)

        return generated

    # ------------------------------------------------------------------
    # Generation strategies
    # ------------------------------------------------------------------

    def _generate_single_file(
        self,
        file_info: Dict[str, Any],
        paper_text: str,
        strategy_extraction: dict,
        file_analyses: Optional[dict],
        generated: Dict[str, str],
    ) -> str:
        """Generate a single file using a self-contained prompt."""
        path = file_info.get("path", "")
        description = file_info.get("description", "")

        dep_code = self._get_dependency_context(file_info, generated)

        analysis_text = ""
        if file_analyses and path in file_analyses:
            fa = file_analyses[path]
            analysis_text = json.dumps(
                {
                    "classes": fa.classes,
                    "functions": fa.functions,
                    "imports": fa.imports,
                    "algorithms": fa.algorithms,
                },
                default=str,
            )[:4000]

        equations = ""
        if isinstance(strategy_extraction, dict):
            eqs = strategy_extraction.get("key_equations", [])
            if eqs:
                equations = "\n".join(f"- {eq}" for eq in eqs)

        prompt = self._build_prompt(
            path, description, paper_text, dep_code,
            analysis_text, equations, strategy_extraction,
        )

        max_tokens = self._max_tokens_for(path)

        from providers.base import GenerationConfig

        config = GenerationConfig(temperature=0.15, max_output_tokens=max_tokens)
        result = self.provider.generate(prompt, config=config)
        return self._clean_output(result.text, path)

    def _generate_with_context_manager(
        self,
        file_info: Dict[str, Any],
        paper_text: str,
        strategy_extraction: dict,
        file_analyses: Optional[dict],
        generated: Dict[str, str],
        context_manager: Any,
    ) -> str:
        """Generate a file using the external context manager."""
        context = context_manager.build_prompt(file_info)

        from providers.base import GenerationConfig

        config = GenerationConfig(temperature=0.15, max_output_tokens=16384)
        result = self.provider.generate(context.full_prompt(), config=config)
        return self._clean_output(result.text, file_info.get("path", ""))

    # ------------------------------------------------------------------
    # Dependency resolution
    # ------------------------------------------------------------------

    def _get_dependency_context(
        self,
        file_info: Dict[str, Any],
        generated: Dict[str, str],
        max_deps: int = 3,
    ) -> str:
        """Collect truncated source of dependency files for context."""
        deps: List[str] = file_info.get("dependencies", [])

        if not deps:
            path = file_info.get("path", "")
            base = os.path.basename(path)
            deps = self._IMPLICIT_DEPS.get(base, [])

        context_parts: List[str] = []
        for dep in deps[:max_deps]:
            if dep in generated:
                context_parts.append(
                    f"# === {dep} ===\n{generated[dep][:3000]}"
                )
        return "\n\n".join(context_parts)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        path: str,
        description: str,
        paper_text: str,
        dep_code: str,
        analysis_text: str,
        equations: str,
        strategy_extraction: dict,
    ) -> str:
        """Build the code-generation prompt, loading a template if available."""
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts",
            "coder.txt",
        )

        if os.path.exists(prompt_path):
            with open(prompt_path, encoding="utf-8") as fh:
                template = fh.read()
            replacements: Dict[str, str] = {
                "file_path": path,
                "file_description": description,
                "paper_analysis": paper_text[:20000],
                "architecture_plan": json.dumps(
                    strategy_extraction, default=str
                )[:5000],
                "dependency_code": dep_code[:8000],
                "equations": equations,
            }
            for key, value in replacements.items():
                template = template.replace("{{" + key + "}}", str(value))
            return template

        # Fallback inline prompt
        return (
            f"Generate the Python file '{path}' for a quantitative trading backtest.\n\n"
            f"DESCRIPTION: {description}\n\n"
            f"KEY EQUATIONS FROM PAPER:\n{equations}\n\n"
            f"STRATEGY DETAILS:\n"
            f"{json.dumps(strategy_extraction, default=str)[:5000]}\n\n"
            f"FILE ANALYSIS:\n{analysis_text}\n\n"
            f"DEPENDENCY CODE (already generated):\n{dep_code}\n\n"
            f"PAPER CONTEXT:\n{paper_text[:15000]}\n\n"
            "REQUIREMENTS:\n"
            "- Implement EXACTLY what the paper describes\n"
            "- Use pandas/numpy for vectorized operations\n"
            "- Include docstrings with paper equation references\n"
            "- Use config references for ALL hyperparameters (never hardcode)\n"
            "- NO look-ahead bias: signals must use only past data\n"
            "- Proper date alignment: signal computed at time t, trade at t+1\n"
            "- Handle missing data with forward-fill or drop as appropriate\n"
            "- Include type hints\n"
            "- Follow quantitative finance conventions\n\n"
            "Return ONLY the Python code. No markdown fences."
        )

    # ------------------------------------------------------------------
    # Output cleaning
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_output(text: str, path: str) -> str:
        """Strip markdown fences and validate Python syntax."""
        # Strip markdown code blocks
        match = re.search(
            r"```(?:python|txt|markdown|md)?\s*\n(.*?)```", text, re.DOTALL
        )
        if match:
            text = match.group(1)

        if path.endswith(".py"):
            try:
                compile(text, path, "exec")
            except SyntaxError as exc:
                logger.warning("Syntax error in %s: %s", path, exc)
                # Attempt basic recovery
                cleaned = text.replace("```", "").strip()
                try:
                    compile(cleaned, path, "exec")
                    text = cleaned
                except SyntaxError:
                    pass  # Return best-effort text

        return text.strip()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _max_tokens_for(path: str) -> int:
        """Return an appropriate max-output-token budget for *path*."""
        base = os.path.basename(path).lower()
        if base in ("config.py", "requirements.txt"):
            return _MAX_TOKENS["config"]
        if base == "readme.md":
            return _MAX_TOKENS["readme"]
        return _MAX_TOKENS["default"]
