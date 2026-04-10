"""Self-refiner — verify / refine loops for backtest artifacts.

Implements an iterative verify → refine → re-verify cycle.  Each artifact
(plan JSON, file analysis JSON, or generated Python code) is first
critiqued for quant-specific issues (look-ahead bias, missing signals,
hardcoded parameters, etc.) and then refined until the critique reports no
further issues or the maximum iteration count is reached.
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Keywords that signal refinement is needed when JSON parsing fails.
_REFINEMENT_KEYWORDS: List[str] = [
    "critical",
    "missing",
    "incorrect",
    "look-ahead bias",
    "not implemented",
    "hardcoded",
    "error",
]


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------

@dataclass
class RefinementResult:
    """Outcome of a full verify → refine loop.

    Attributes:
        original: The artifact as it was before refinement.
        refined: The artifact after zero or more refinement passes.
        critique: The last critique text produced by :meth:`SelfRefiner.verify`.
        improvements: Human-readable log of what changed per iteration.
        iterations: Number of refine passes actually executed.
        improved: ``True`` if the artifact was modified at all.
    """

    original: str = ""
    refined: str = ""
    critique: str = ""
    improvements: List[str] = field(default_factory=list)
    iterations: int = 0
    improved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_length": len(self.original),
            "refined_length": len(self.refined),
            "critique": self.critique[:500],
            "improvements": self.improvements,
            "iterations": self.iterations,
            "improved": self.improved,
        }


# ------------------------------------------------------------------
# Refiner
# ------------------------------------------------------------------

class SelfRefiner:
    """Self-refine loop: verify → refine → re-verify.

    The refiner is artifact-type agnostic: it can handle plans (JSON),
    file analyses (JSON), or generated source code.  Prompt templates are
    loaded from the ``prompts/`` directory when available; otherwise
    sensible inline defaults are used.

    Parameters:
        provider: An LLM provider instance (must expose ``generate``).
        config: Optional configuration dict.
        max_iterations: Maximum number of refine passes (default 2).
    """

    # Character budgets
    _ARTIFACT_BUDGET: int = 15_000
    _PAPER_BUDGET: int = 10_000
    _CRITIQUE_BUDGET: int = 5_000

    # Artifact types that should be round-tripped as JSON.
    _JSON_ARTIFACT_TYPES: frozenset = frozenset({
        "overall_plan",
        "architecture_design",
        "logic_design",
        "file_analysis",
    })

    def __init__(
        self,
        provider: Any,
        config: Optional[Dict[str, Any]] = None,
        max_iterations: int = 2,
    ) -> None:
        self.provider = provider
        self.config = config or {}
        self.max_iterations = max_iterations

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refine(
        self,
        artifact: str,
        artifact_type: str,
        paper_context: str,
    ) -> RefinementResult:
        """Execute the full verify → refine loop.

        Args:
            artifact: The textual artifact to refine (JSON string or
                Python source).
            artifact_type: A tag describing the artifact — one of
                ``"overall_plan"``, ``"architecture_design"``,
                ``"logic_design"``, ``"file_analysis"``, or ``"code"``.
            paper_context: Paper text to provide domain grounding.

        Returns:
            A :class:`RefinementResult` summarising what happened.
        """
        result = RefinementResult(original=artifact)
        current = artifact
        critique = ""

        for i in range(self.max_iterations):
            # --- Verify ------------------------------------------------
            critique = self.verify(current, artifact_type, paper_context)
            needs_refinement = self._needs_refinement(critique)

            if not needs_refinement:
                logger.info(
                    "Refine iteration %d: no issues found, stopping", i + 1
                )
                break

            # --- Refine ------------------------------------------------
            logger.info(
                "Refine iteration %d: issues found, refining", i + 1
            )
            refined = self.refine_artifact(
                current, artifact_type, critique, paper_context
            )

            if refined and refined != current:
                current = refined
                result.improved = True
                result.iterations = i + 1
                result.improvements.append(
                    f"Iteration {i + 1}: refined based on critique"
                )
            else:
                logger.info(
                    "Refine iteration %d: refine produced no change, stopping",
                    i + 1,
                )
                break

        result.refined = current
        result.critique = critique
        return result

    def verify(
        self,
        artifact: str,
        artifact_type: str,
        paper_context: str,
    ) -> str:
        """Critique an artifact for quant-specific issues.

        Returns the raw critique text (which may or may not be valid
        JSON depending on the LLM response).
        """
        prompt = self._build_verify_prompt(
            artifact, artifact_type, paper_context
        )

        from providers.base import GenerationConfig

        config = GenerationConfig(temperature=0.1, max_output_tokens=4096)
        result = self.provider.generate(prompt, config=config)
        return result.text

    def refine_artifact(
        self,
        artifact: str,
        artifact_type: str,
        critique: str,
        paper_context: str,
    ) -> str:
        """Produce a refined version of the artifact addressing the critique.

        For JSON artifact types the output is round-tripped through JSON
        to guarantee valid structure.  For code artifacts the output is
        cleaned of markdown fences.
        """
        prompt = self._build_refine_prompt(
            artifact, artifact_type, critique, paper_context
        )

        from providers.base import GenerationConfig

        config = GenerationConfig(temperature=0.15, max_output_tokens=8192)
        result = self.provider.generate(prompt, config=config)

        # JSON round-trip for plan/analysis artifacts
        if artifact_type in self._JSON_ARTIFACT_TYPES:
            try:
                refined_json = self._extract_json(result.text)
                return json.dumps(refined_json)
            except Exception:
                logger.debug(
                    "JSON round-trip failed for %s; returning raw text",
                    artifact_type,
                )

        # Code artifact — strip fences
        if artifact_type == "code":
            return self._clean_code(result.text)

        return result.text

    # ------------------------------------------------------------------
    # Decision helpers
    # ------------------------------------------------------------------

    def _needs_refinement(self, critique: str) -> bool:
        """Determine whether the critique indicates refinement is needed."""
        # Prefer a structured answer
        try:
            data = self._extract_json(critique)
            if "needs_refinement" in data:
                return bool(data["needs_refinement"])
        except Exception:
            pass

        # Heuristic keyword scan
        lower = critique.lower()
        return any(keyword in lower for keyword in _REFINEMENT_KEYWORDS)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_verify_prompt(
        self, artifact: str, artifact_type: str, paper_context: str
    ) -> str:
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts",
            "self_refine_verify.txt",
        )

        if os.path.exists(prompt_path):
            with open(prompt_path, encoding="utf-8") as fh:
                template = fh.read()
            template = template.replace("{{artifact_type}}", artifact_type)
            template = template.replace(
                "{{artifact_content}}", artifact[: self._ARTIFACT_BUDGET]
            )
            template = template.replace(
                "{{paper_context}}", paper_context[: self._PAPER_BUDGET]
            )
            return template

        # Fallback inline prompt
        return (
            f"Verify this {artifact_type} for a quantitative trading backtest.\n\n"
            f"ARTIFACT:\n{artifact[: self._ARTIFACT_BUDGET]}\n\n"
            f"PAPER CONTEXT:\n{paper_context[: self._PAPER_BUDGET]}\n\n"
            "Check for:\n"
            "- Signal construction completeness and correctness\n"
            "- Look-ahead bias risks\n"
            "- Missing paper methodology\n"
            "- Hardcoded parameters that should be configurable\n"
            "- Data handling issues\n\n"
            "Return JSON: "
            '{"issues": [...], "severity_assessment": "...", '
            '"needs_refinement": true/false}'
        )

    def _build_refine_prompt(
        self,
        artifact: str,
        artifact_type: str,
        critique: str,
        paper_context: str,
    ) -> str:
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts",
            "self_refine_refine.txt",
        )

        if os.path.exists(prompt_path):
            with open(prompt_path, encoding="utf-8") as fh:
                template = fh.read()
            template = template.replace("{{artifact_type}}", artifact_type)
            template = template.replace(
                "{{artifact_content}}", artifact[: self._ARTIFACT_BUDGET]
            )
            template = template.replace(
                "{{critique}}", critique[: self._CRITIQUE_BUDGET]
            )
            template = template.replace(
                "{{paper_context}}", paper_context[: self._PAPER_BUDGET]
            )
            return template

        # Fallback inline prompt
        return (
            f"Refine this {artifact_type} based on the critique below.\n\n"
            f"CURRENT ARTIFACT:\n{artifact[: self._ARTIFACT_BUDGET]}\n\n"
            f"CRITIQUE:\n{critique[: self._CRITIQUE_BUDGET]}\n\n"
            f"PAPER CONTEXT:\n{paper_context[: self._PAPER_BUDGET]}\n\n"
            "Address ALL identified issues while maintaining consistency "
            "with the paper methodology.\n"
            f"Return the complete refined {artifact_type}."
        )

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

        raise ValueError("No valid JSON found in text")

    @staticmethod
    def _clean_code(text: str) -> str:
        """Strip markdown fences from code output."""
        match = re.search(r"```(?:python)?\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()
