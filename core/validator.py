"""Code validator — self-review + auto-fix for backtest code.

Validates generated backtest code against the original paper methodology,
checking for signal fidelity, look-ahead bias, rebalancing correctness,
transaction-cost handling, and configurable hyperparameters.  Critical
issues can be auto-fixed via :meth:`CodeValidator.fix_issues`.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------

@dataclass
class ValidationIssue:
    """A single validation finding.

    Attributes:
        severity: One of ``"critical"``, ``"warning"``, or ``"info"``.
        file_path: File the issue was found in.
        line_hint: Approximate line reference or code snippet.
        description: Human-readable description of the problem.
        suggestion: Recommended fix.
        category: Domain tag such as ``signal_fidelity``,
            ``look_ahead_bias``, ``data_handling``, ``config``, etc.
    """

    severity: str = "warning"
    file_path: str = ""
    line_hint: str = ""
    description: str = ""
    suggestion: str = ""
    category: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "severity": self.severity,
            "file_path": self.file_path,
            "line_hint": self.line_hint,
            "description": self.description,
            "suggestion": self.suggestion,
            "category": self.category,
        }


@dataclass
class ValidationReport:
    """Aggregate validation result for the full codebase.

    Attributes:
        issues: All discovered :class:`ValidationIssue` objects.
        score: 0–100 overall quality score.
        signal_coverage: Fraction of paper signals implemented (0–1).
        data_coverage: Fraction of required data sources handled (0–1).
        passed: ``True`` when *score* ≥ 80 **and** there are zero
            critical issues.
    """

    issues: List[ValidationIssue] = field(default_factory=list)
    score: int = 100
    signal_coverage: float = 0.0
    data_coverage: float = 0.0
    passed: bool = True

    @property
    def critical_count(self) -> int:
        """Number of critical-severity issues."""
        return sum(1 for i in self.issues if i.severity == "critical")

    @property
    def warning_count(self) -> int:
        """Number of warning-severity issues."""
        return sum(1 for i in self.issues if i.severity == "warning")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issues": [i.to_dict() for i in self.issues],
            "score": self.score,
            "signal_coverage": self.signal_coverage,
            "data_coverage": self.data_coverage,
            "passed": self.passed,
            "critical_count": self.critical_count,
            "warning_count": self.warning_count,
        }


# ------------------------------------------------------------------
# Validator
# ------------------------------------------------------------------

class CodeValidator:
    """Validates generated backtest code against the paper.

    Parameters:
        provider: An LLM provider instance.
        config: Optional configuration dict.
    """

    # Character budgets
    _FILES_BUDGET: int = 30_000
    _PAPER_BUDGET: int = 15_000
    _STRATEGY_BUDGET: int = 8_000
    _FIX_CODE_BUDGET: int = 12_000
    _FIX_PAPER_BUDGET: int = 8_000

    def __init__(self, provider: Any, config: Optional[Dict[str, Any]] = None) -> None:
        self.provider = provider
        self.config = config or {}
        self._last_fixed_paths: set = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(
        self,
        generated_files: Dict[str, str],
        paper_text: str,
        strategy_extraction: dict,
    ) -> ValidationReport:
        """Run full validation and return a :class:`ValidationReport`.

        Args:
            generated_files: Mapping of path → source code.
            paper_text: Full or abridged paper text.
            strategy_extraction: Strategy extraction dict.

        Returns:
            A :class:`ValidationReport` with issues, scores, and a
            pass/fail verdict.
        """
        prompt = self._build_validation_prompt(
            generated_files, paper_text, strategy_extraction
        )

        from providers.base import GenerationConfig

        config = GenerationConfig(
            temperature=0.1,
            max_output_tokens=6144,
            response_format="json",
        )

        result = self._call_provider(prompt, config)

        issues: List[ValidationIssue] = []
        for issue_data in result.get("issues", []):
            issues.append(
                ValidationIssue(
                    severity=issue_data.get("severity", "warning"),
                    file_path=issue_data.get("file_path", ""),
                    line_hint=issue_data.get("line_hint", ""),
                    description=issue_data.get("description", ""),
                    suggestion=issue_data.get("suggestion", ""),
                    category=issue_data.get("category", ""),
                )
            )

        score = result.get("score", 80)
        n_critical = sum(1 for i in issues if i.severity == "critical")

        report = ValidationReport(
            issues=issues,
            score=score,
            signal_coverage=result.get("signal_coverage", 0),
            data_coverage=result.get("data_coverage", 0),
            passed=(score >= 80 and n_critical == 0),
        )

        logger.info(
            "Validation complete: score=%d, critical=%d, warnings=%d, passed=%s",
            report.score,
            report.critical_count,
            report.warning_count,
            report.passed,
        )

        return report

    def fix_issues(
        self,
        generated_files: Dict[str, str],
        report: ValidationReport,
        paper_text: str,
    ) -> Dict[str, str]:
        """Attempt auto-fix of critical issues.

        Only files that have at least one *critical* issue are
        re-generated.  Non-critical issues are left for manual review.
        Sets ``self._last_fixed_paths`` to the set of file paths whose
        content was actually changed during this call.

        Args:
            generated_files: Current mapping of path → source.
            report: The :class:`ValidationReport` to act on.
            paper_text: Paper text for context.

        Returns:
            A *new* mapping of path → source with fixes applied.
        """
        self._last_fixed_paths = set()

        critical_issues = [
            i for i in report.issues if i.severity == "critical"
        ]
        if not critical_issues:
            return generated_files

        # Group issues by file
        files_to_fix: Dict[str, List[ValidationIssue]] = {}
        for issue in critical_issues:
            if issue.file_path:
                files_to_fix.setdefault(issue.file_path, []).append(issue)

        fixed_files = dict(generated_files)

        for file_path, issues in files_to_fix.items():
            if file_path not in fixed_files:
                logger.warning(
                    "Cannot fix %s: not in generated files", file_path
                )
                continue

            original_content = fixed_files[file_path]

            logger.info(
                "Auto-fixing %d critical issue(s) in %s",
                len(issues),
                file_path,
            )
            fixed_code = self._fix_single_file(
                file_path, original_content, issues, paper_text
            )
            if fixed_code:
                fixed_files[file_path] = fixed_code
                if fixed_code != original_content:
                    self._last_fixed_paths.add(file_path)

        return fixed_files

    # ------------------------------------------------------------------
    # Provider helpers
    # ------------------------------------------------------------------

    def _call_provider(self, prompt: str, config: Any) -> Dict[str, Any]:
        """Call provider with structured output, falling back to free text."""
        schema = {
            "type": "object",
            "properties": {
                "issues": {"type": "array"},
                "score": {"type": "integer"},
                "signal_coverage": {"type": "number"},
                "data_coverage": {"type": "number"},
                "passed": {"type": "boolean"},
            },
        }

        try:
            return self.provider.generate_structured(
                prompt, schema=schema, config=config
            )
        except Exception:
            logger.debug(
                "Structured generation unavailable; falling back to free-text"
            )

        gen_result = self.provider.generate(prompt, config=config)
        return self._extract_json(gen_result.text)

    # ------------------------------------------------------------------
    # Fix helpers
    # ------------------------------------------------------------------

    def _fix_single_file(
        self,
        file_path: str,
        current_code: str,
        issues: List[ValidationIssue],
        paper_text: str,
    ) -> Optional[str]:
        """Re-generate a file to fix critical issues."""
        issues_text = "\n".join(
            f"- [{i.category}] {i.description} (suggestion: {i.suggestion})"
            for i in issues
        )

        prompt = (
            f"Fix the following critical issues in the backtest code file "
            f"'{file_path}'.\n\n"
            f"CURRENT CODE:\n{current_code[: self._FIX_CODE_BUDGET]}\n\n"
            f"CRITICAL ISSUES TO FIX:\n{issues_text}\n\n"
            f"PAPER CONTEXT:\n{paper_text[: self._FIX_PAPER_BUDGET]}\n\n"
            "Return ONLY the complete fixed Python code. No markdown fences."
        )

        from providers.base import GenerationConfig

        config = GenerationConfig(temperature=0.15, max_output_tokens=16384)
        result = self.provider.generate(prompt, config=config)
        return self._clean_code(result.text)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_validation_prompt(
        self,
        generated_files: Dict[str, str],
        paper_text: str,
        strategy_extraction: dict,
    ) -> str:
        """Build the validation prompt, loading a template if available."""
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts",
            "validator.txt",
        )

        files_text = self._format_files(generated_files)

        if os.path.exists(prompt_path):
            with open(prompt_path, encoding="utf-8") as fh:
                template = fh.read()
            template = template.replace(
                "{{generated_files}}", files_text[: self._FILES_BUDGET]
            )
            template = template.replace(
                "{{paper_analysis}}", paper_text[: self._PAPER_BUDGET]
            )
            template = template.replace(
                "{{strategy_extraction}}",
                json.dumps(strategy_extraction, default=str)[
                    : self._STRATEGY_BUDGET
                ],
            )
            return template

        # Fallback inline prompt
        return (
            "Validate this backtest code against the paper methodology.\n\n"
            f"GENERATED FILES:\n{files_text[: self._FILES_BUDGET]}\n\n"
            f"STRATEGY:\n"
            f"{json.dumps(strategy_extraction, default=str)[: self._STRATEGY_BUDGET]}\n\n"
            f"PAPER:\n{paper_text[: self._PAPER_BUDGET]}\n\n"
            "Check for:\n"
            "1. Signal fidelity (every formula implemented correctly)\n"
            "2. No look-ahead bias (signals only use past data)\n"
            "3. Proper rebalancing lag\n"
            "4. Transaction cost handling\n"
            "5. Universe selection matches paper\n"
            "6. All hyperparameters configurable\n\n"
            'Return JSON: {"issues": [...], "score": 0-100, '
            '"signal_coverage": 0-1, "data_coverage": 0-1, '
            '"passed": true/false}'
        )

    @staticmethod
    def _format_files(generated_files: Dict[str, str]) -> str:
        """Format generated files into a single string for the prompt."""
        parts: List[str] = []
        for path, content in generated_files.items():
            if path.endswith(".py"):
                parts.append(f"\n# === {path} ===\n{content[:4000]}\n")
        return "".join(parts)

    # ------------------------------------------------------------------
    # JSON / code extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """Best-effort JSON extraction from free-form LLM output."""
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        logger.warning(
            "Could not extract JSON from validator response; returning defaults"
        )
        return {"issues": [], "score": 50, "passed": False}

    @staticmethod
    def _clean_code(text: str) -> str:
        """Strip markdown fences from code output."""
        match = re.search(r"```(?:python)?\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()
