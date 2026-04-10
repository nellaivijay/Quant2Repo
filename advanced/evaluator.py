"""Reference evaluator — score backtest against paper results.

Evaluates a generated backtest codebase by comparing it to:
1. A known-good reference implementation (when available), or
2. The paper's text and reported performance numbers.

Multiple independent evaluations are run and aggregated to reduce
noise from any single LLM call.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────

@dataclass
class EvaluationScore:
    """Aggregated evaluation score for a generated backtest.

    Attributes:
        overall_score: 1–5 Likert-scale score (5 = perfect).
        component_scores: Per-component scores (e.g. ``{"signals": 4.2}``).
        coverage: Percentage of paper methodology implemented (0–100).
        missing_components: Components described in the paper but absent.
        extra_components: Components present but not in the paper.
        summary: Free-text evaluation summary.
        severity_breakdown: Counts of issues by severity level.
    """

    overall_score: float = 0.0
    component_scores: Dict[str, float] = field(default_factory=dict)
    coverage: float = 0.0
    missing_components: List[str] = field(default_factory=list)
    extra_components: List[str] = field(default_factory=list)
    summary: str = ""
    severity_breakdown: Dict[str, int] = field(default_factory=dict)

    @property
    def grade(self) -> str:
        """Letter grade derived from *overall_score*."""
        if self.overall_score >= 4.5:
            return "A"
        if self.overall_score >= 3.5:
            return "B"
        if self.overall_score >= 2.5:
            return "C"
        if self.overall_score >= 1.5:
            return "D"
        return "F"


# ──────────────────────────────────────────────────────────────────────
# Evaluator
# ──────────────────────────────────────────────────────────────────────

class ReferenceEvaluator:
    """Evaluate generated backtest against paper results or a reference.

    The evaluator runs *num_evaluations* independent LLM calls and
    aggregates the scores (mean) and missing-component lists (majority
    vote) to produce a single :class:`EvaluationScore`.

    Parameters:
        provider: An LLM provider instance.
        config: Optional :class:`Q2RConfig`.
        num_evaluations: How many independent evaluation calls to make.
    """

    # Dimensions to score on.
    _DIMENSIONS: List[str] = [
        "signal_construction",
        "portfolio_formation",
        "data_handling",
        "performance_metrics",
        "risk_management",
        "code_quality",
        "reproducibility",
    ]

    def __init__(
        self,
        provider: Any,
        config: Optional[Any] = None,
        num_evaluations: int = 3,
    ) -> None:
        self.provider = provider
        self.config = config
        self.num_evaluations = num_evaluations

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def evaluate_with_reference(
        self,
        generated_files: Dict[str, str],
        reference_dir: str,
        paper_text: str,
    ) -> EvaluationScore:
        """Compare generated code against a known-good reference.

        Args:
            generated_files: Mapping of relative path → source content.
            reference_dir: Path to a directory with reference Python files.
            paper_text: The full paper text.

        Returns:
            An aggregated :class:`EvaluationScore`.
        """
        reference_files = self._load_reference_files(reference_dir)
        scores = self._run_evaluations(
            generated_files, paper_text, reference_files=reference_files
        )
        return self._aggregate_scores(scores)

    def evaluate_without_reference(
        self,
        generated_files: Dict[str, str],
        paper_text: str,
        paper_results: Optional[dict] = None,
    ) -> EvaluationScore:
        """Evaluate using only paper text and reported results.

        Args:
            generated_files: Mapping of relative path → source content.
            paper_text: The full paper text.
            paper_results: Optional dict of reported performance numbers.

        Returns:
            An aggregated :class:`EvaluationScore`.
        """
        scores = self._run_evaluations(
            generated_files, paper_text, paper_results=paper_results
        )
        return self._aggregate_scores(scores)

    # ──────────────────────────────────────────────────────────────────
    # Reference file loading
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _load_reference_files(reference_dir: str) -> Dict[str, str]:
        """Recursively load ``*.py`` files from *reference_dir*."""
        files: Dict[str, str] = {}
        for root, _, filenames in os.walk(reference_dir):
            for fn in filenames:
                if fn.endswith(".py"):
                    path = os.path.join(root, fn)
                    rel = os.path.relpath(path, reference_dir)
                    with open(path) as f:
                        files[rel] = f.read()
        return files

    # ──────────────────────────────────────────────────────────────────
    # Evaluation loop
    # ──────────────────────────────────────────────────────────────────

    def _run_evaluations(
        self,
        generated_files: Dict[str, str],
        paper_text: str,
        reference_files: Optional[Dict[str, str]] = None,
        paper_results: Optional[dict] = None,
    ) -> List[EvaluationScore]:
        """Run *num_evaluations* independent evaluation calls."""
        scores: List[EvaluationScore] = []
        for i in range(self.num_evaluations):
            try:
                score = self._single_evaluation(
                    generated_files,
                    paper_text,
                    reference_files,
                    paper_results,
                )
                scores.append(score)
            except Exception as e:
                logger.warning("Evaluation %d failed: %s", i + 1, e)
        return scores

    def _single_evaluation(
        self,
        generated_files: Dict[str, str],
        paper_text: str,
        reference_files: Optional[Dict[str, str]] = None,
        paper_results: Optional[dict] = None,
    ) -> EvaluationScore:
        """Execute a single evaluation via the LLM."""
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts",
            "reference_eval.txt",
        )

        gen_text = self._format_files(generated_files, max_per_file=3000)
        ref_text = (
            self._format_files(reference_files, max_per_file=2000, prefix="REF: ")
            if reference_files
            else ""
        )

        if os.path.exists(prompt_path):
            with open(prompt_path) as f:
                template = f.read()
            template = template.replace("{{generated_files}}", gen_text[:25000])
            template = template.replace(
                "{{paper_results}}",
                json.dumps(paper_results or {}, default=str)[:3000],
            )
            template = template.replace("{{backtest_output}}", ref_text[:15000])
            prompt = template
        else:
            prompt = self._default_eval_prompt(
                gen_text, paper_text, ref_text, paper_results
            )

        from providers.base import GenerationConfig

        config = GenerationConfig(
            temperature=0.3,
            max_output_tokens=4096,
            response_format="json",
        )
        result = self.provider.generate(prompt, config=config)
        data = self._extract_json(result.text)

        return EvaluationScore(
            overall_score=data.get("overall_score", 3),
            component_scores=data.get("component_scores", {}),
            coverage=data.get("coverage", 50),
            missing_components=data.get("missing_components", []),
            extra_components=data.get("extra_components", []),
            summary=data.get("summary", ""),
            severity_breakdown=data.get("severity_breakdown", {}),
        )

    def _default_eval_prompt(
        self,
        gen_text: str,
        paper_text: str,
        ref_text: str,
        paper_results: Optional[dict],
    ) -> str:
        """Build fallback evaluation prompt."""
        dimensions_str = ", ".join(self._DIMENSIONS)
        return f"""Evaluate this generated backtest against the paper.

PAPER (abridged):
{paper_text[:12000]}

GENERATED CODE:
{gen_text[:20000]}

{f"REFERENCE IMPLEMENTATION:{chr(10)}{ref_text[:10000]}" if ref_text else ""}

REPORTED PAPER RESULTS:
{json.dumps(paper_results or {}, default=str)[:3000]}

Score on a 1-5 scale for each dimension: {dimensions_str}.
Also provide an overall_score (1-5) and coverage (0-100%).

Return JSON:
{{
  "overall_score": 1-5,
  "component_scores": {{
    "signal_construction": 1-5,
    "portfolio_formation": 1-5,
    "data_handling": 1-5,
    "performance_metrics": 1-5,
    "risk_management": 1-5,
    "code_quality": 1-5,
    "reproducibility": 1-5
  }},
  "coverage": 0-100,
  "missing_components": ["list of missing items"],
  "extra_components": ["list of extra items"],
  "summary": "free text summary",
  "severity_breakdown": {{"critical": 0, "warning": 0, "info": 0}}
}}"""

    # ──────────────────────────────────────────────────────────────────
    # Score aggregation
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _aggregate_scores(scores: List[EvaluationScore]) -> EvaluationScore:
        """Aggregate multiple evaluation scores into one.

        - Numeric values are averaged.
        - Missing components use majority vote (≥ 50% agreement).
        - The first non-empty summary is used.
        """
        if not scores:
            return EvaluationScore(summary="No evaluations completed")

        avg_overall = sum(s.overall_score for s in scores) / len(scores)
        avg_coverage = sum(s.coverage for s in scores) / len(scores)

        # Merge component scores
        all_components: Dict[str, List[float]] = {}
        for s in scores:
            for k, v in s.component_scores.items():
                all_components.setdefault(k, []).append(v)
        avg_components = {
            k: round(sum(v) / len(v), 2) for k, v in all_components.items()
        }

        # Missing components — majority vote
        missing_counts: Dict[str, int] = {}
        for s in scores:
            for m in s.missing_components:
                missing_counts[m] = missing_counts.get(m, 0) + 1
        threshold = len(scores) / 2
        missing = [m for m, c in missing_counts.items() if c >= threshold]

        # Extra components — majority vote
        extra_counts: Dict[str, int] = {}
        for s in scores:
            for e in s.extra_components:
                extra_counts[e] = extra_counts.get(e, 0) + 1
        extra = [e for e, c in extra_counts.items() if c >= threshold]

        # Severity breakdown — average
        all_severities: Dict[str, List[int]] = {}
        for s in scores:
            for k, v in s.severity_breakdown.items():
                all_severities.setdefault(k, []).append(v)
        avg_severities = {
            k: round(sum(v) / len(v)) for k, v in all_severities.items()
        }

        summaries = [s.summary for s in scores if s.summary]

        return EvaluationScore(
            overall_score=round(avg_overall, 2),
            component_scores=avg_components,
            coverage=round(avg_coverage, 1),
            missing_components=missing,
            extra_components=extra,
            summary=summaries[0] if summaries else "",
            severity_breakdown=avg_severities,
        )

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _format_files(
        files: Dict[str, str],
        max_per_file: int = 3000,
        prefix: str = "",
    ) -> str:
        """Format a files dict into a single prompt-ready text block."""
        parts: List[str] = []
        for path, content in files.items():
            if path.endswith(".py"):
                parts.append(
                    f"\n# === {prefix}{path} ===\n{content[:max_per_file]}"
                )
        return "\n".join(parts)

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extract JSON from LLM response text."""
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
            return json.loads(text[start : end + 1])
        return {}
