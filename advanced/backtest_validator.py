"""Backtest-specific validation — checks for common pitfalls.

Validates generated backtest code for quantitative finance anti-patterns
including look-ahead bias, survivorship bias, data snooping, and more.
Combines static analysis (regex/AST-based) with LLM-powered deep validation.
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
class BiasCheck:
    """A single bias/pitfall check result."""

    name: str = ""
    passed: bool = True
    severity: str = "info"  # critical, warning, info
    description: str = ""
    recommendation: str = ""
    file_path: str = ""


@dataclass
class BacktestValidationReport:
    """Complete backtest validation report."""

    checks: List[BiasCheck] = field(default_factory=list)
    bias_risk_score: int = 0  # 0 (no risk) to 100 (extreme risk)
    recommendations: List[str] = field(default_factory=list)
    passed: bool = True

    @property
    def critical_count(self) -> int:
        """Number of failed critical checks."""
        return sum(1 for c in self.checks if c.severity == "critical" and not c.passed)

    @property
    def warning_count(self) -> int:
        """Number of failed warning checks."""
        return sum(1 for c in self.checks if c.severity == "warning" and not c.passed)

    @property
    def info_count(self) -> int:
        """Number of failed info-level checks."""
        return sum(1 for c in self.checks if c.severity == "info" and not c.passed)

    def summary(self) -> str:
        """Human-readable summary of the validation report."""
        total = len(self.checks)
        failed = sum(1 for c in self.checks if not c.passed)
        status = "PASSED" if self.passed else "FAILED"
        return (
            f"Backtest Validation: {status} "
            f"({failed}/{total} checks failed, "
            f"bias risk score: {self.bias_risk_score}/100)"
        )


# ──────────────────────────────────────────────────────────────────────
# Validator
# ──────────────────────────────────────────────────────────────────────

class BacktestValidator:
    """Validates backtest code for common quantitative pitfalls.

    Performs two kinds of analysis:

    1. **Static checks** — regex-based pattern matching for known anti-patterns
       such as negative ``shift()`` calls, hardcoded dates, and missing
       transaction-cost configuration.
    2. **LLM checks** — deep semantic validation powered by the configured
       LLM provider, checking for survivorship bias, look-ahead bias,
       point-in-time data issues, and more.

    Parameters:
        provider: An LLM provider instance (must expose ``generate``).
        config: Optional :class:`Q2RConfig` for tuning behaviour.
    """

    BIAS_CHECKS: List[str] = [
        "look_ahead_bias",
        "survivorship_bias",
        "point_in_time_data",
        "rebalancing_timing",
        "transaction_costs",
        "data_snooping",
        "sample_period_sensitivity",
        "capacity_constraints",
    ]

    def __init__(self, provider: Any, config: Optional[Any] = None) -> None:
        self.provider = provider
        self.config = config

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def validate(
        self,
        generated_files: Dict[str, str],
        strategy_extraction: dict,
        backtest_results: Optional[dict] = None,
    ) -> BacktestValidationReport:
        """Run backtest-specific validation.

        Args:
            generated_files: Mapping of relative path → source code.
            strategy_extraction: Strategy details extracted from the paper.
            backtest_results: Optional dict of actual backtest run results.

        Returns:
            A :class:`BacktestValidationReport` with all check results.
        """
        # First do static analysis checks
        static_checks = self._static_checks(generated_files)

        # Then do LLM-based deep validation
        llm_checks = self._llm_validate(
            generated_files, strategy_extraction, backtest_results
        )

        all_checks = static_checks + llm_checks
        critical_fails = sum(
            1 for c in all_checks if c.severity == "critical" and not c.passed
        )
        warning_fails = sum(
            1 for c in all_checks if c.severity == "warning" and not c.passed
        )

        bias_risk = min(100, critical_fails * 25 + warning_fails * 10)

        recommendations: List[str] = []
        for check in all_checks:
            if not check.passed and check.recommendation:
                recommendations.append(check.recommendation)

        return BacktestValidationReport(
            checks=all_checks,
            bias_risk_score=bias_risk,
            recommendations=recommendations,
            passed=critical_fails == 0,
        )

    # ──────────────────────────────────────────────────────────────────
    # Static analysis
    # ──────────────────────────────────────────────────────────────────

    def _static_checks(self, generated_files: Dict[str, str]) -> List[BiasCheck]:
        """Run static analysis for common backtest issues."""
        checks: List[BiasCheck] = []

        for path, content in generated_files.items():
            if not path.endswith(".py"):
                continue

            checks.extend(self._check_look_ahead_shift(path, content))
            checks.extend(self._check_hardcoded_dates(path, content))
            checks.extend(self._check_iloc_last_in_signal(path, content))
            checks.extend(self._check_hardcoded_transaction_costs(path, content))
            checks.extend(self._check_future_merge(path, content))
            checks.extend(self._check_no_lag_in_signal(path, content))
            checks.extend(self._check_random_seed(path, content))

        return checks

    def _check_look_ahead_shift(
        self, path: str, content: str
    ) -> List[BiasCheck]:
        """Check for negative shift values that may indicate look-ahead bias."""
        checks: List[BiasCheck] = []
        if re.search(r"\.shift\(\s*-\s*\d", content):
            checks.append(BiasCheck(
                name="potential_future_shift",
                passed=False,
                severity="warning",
                description=(
                    f"Negative shift detected in {path} — "
                    "may indicate look-ahead bias"
                ),
                recommendation=(
                    "Verify all shift() calls use positive values for lagging"
                ),
                file_path=path,
            ))
        return checks

    def _check_hardcoded_dates(
        self, path: str, content: str
    ) -> List[BiasCheck]:
        """Check for excessive hardcoded dates that may indicate data snooping."""
        checks: List[BiasCheck] = []
        date_patterns = re.findall(r"\d{4}-\d{2}-\d{2}", content)
        if len(date_patterns) > 5 and os.path.basename(path) != "config.py":
            checks.append(BiasCheck(
                name="hardcoded_dates",
                passed=False,
                severity="warning",
                description=(
                    f"Many hardcoded dates in {path} — move to config"
                ),
                recommendation="Move all date parameters to config.py",
                file_path=path,
            ))
        return checks

    def _check_iloc_last_in_signal(
        self, path: str, content: str
    ) -> List[BiasCheck]:
        """Check for .iloc[-1] in signal files that might access future data."""
        checks: List[BiasCheck] = []
        if ".iloc[-1]" in content and "signal" in path.lower():
            checks.append(BiasCheck(
                name="iloc_last_in_signal",
                passed=False,
                severity="warning",
                description=(
                    f"Using .iloc[-1] in signal file {path} — "
                    "verify no future data access"
                ),
                recommendation=(
                    "Ensure .iloc[-1] refers to most recent available data, "
                    "not future"
                ),
                file_path=path,
            ))
        return checks

    def _check_hardcoded_transaction_costs(
        self, path: str, content: str
    ) -> List[BiasCheck]:
        """Check that transaction costs are configurable, not hardcoded."""
        checks: List[BiasCheck] = []
        has_cost_ref = (
            "transaction" in content.lower() or "cost" in content.lower()
        )
        if has_cost_ref and "config" not in content.lower():
            if os.path.basename(path) != "config.py":
                checks.append(BiasCheck(
                    name="hardcoded_transaction_costs",
                    passed=False,
                    severity="warning",
                    description=(
                        f"Transaction costs may be hardcoded in {path}"
                    ),
                    recommendation=(
                        "Use config parameter for transaction costs"
                    ),
                    file_path=path,
                ))
        return checks

    def _check_future_merge(
        self, path: str, content: str
    ) -> List[BiasCheck]:
        """Check for merge/join patterns that may introduce look-ahead bias."""
        checks: List[BiasCheck] = []
        # Pattern: merge on date without explicit how='left' or suffixes
        if re.search(r"\.merge\(", content) and "signal" in path.lower():
            if "how=" not in content:
                checks.append(BiasCheck(
                    name="ambiguous_merge_in_signal",
                    passed=False,
                    severity="info",
                    description=(
                        f"Merge without explicit join type in {path} — "
                        "verify no future data leakage"
                    ),
                    recommendation=(
                        "Specify explicit how='left' and validate date alignment"
                    ),
                    file_path=path,
                ))
        return checks

    def _check_no_lag_in_signal(
        self, path: str, content: str
    ) -> List[BiasCheck]:
        """Check that signal files include some form of lagging."""
        checks: List[BiasCheck] = []
        if "signal" in path.lower() and path.endswith(".py"):
            has_lag = any(
                kw in content
                for kw in [".shift(", "lag", "delay", "t-1", "t - 1"]
            )
            if not has_lag and len(content) > 200:
                checks.append(BiasCheck(
                    name="no_lag_in_signal",
                    passed=False,
                    severity="critical",
                    description=(
                        f"No lag/shift found in signal file {path} — "
                        "signals must use only past data"
                    ),
                    recommendation=(
                        "Add .shift(1) to ensure signals use only past data "
                        "for trading decisions"
                    ),
                    file_path=path,
                ))
        return checks

    def _check_random_seed(
        self, path: str, content: str
    ) -> List[BiasCheck]:
        """Check that random operations have fixed seeds for reproducibility."""
        checks: List[BiasCheck] = []
        uses_random = any(
            kw in content
            for kw in ["np.random.", "random.", "torch.manual_seed"]
        )
        if uses_random and "seed" not in content.lower():
            checks.append(BiasCheck(
                name="missing_random_seed",
                passed=False,
                severity="info",
                description=(
                    f"Random operations without fixed seed in {path}"
                ),
                recommendation=(
                    "Set random seed for reproducibility: "
                    "np.random.seed() or random.seed()"
                ),
                file_path=path,
            ))
        return checks

    # ──────────────────────────────────────────────────────────────────
    # LLM-based validation
    # ──────────────────────────────────────────────────────────────────

    def _llm_validate(
        self,
        generated_files: Dict[str, str],
        strategy_extraction: dict,
        backtest_results: Optional[dict],
    ) -> List[BiasCheck]:
        """Use LLM for deep backtest validation."""
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts",
            "backtest_validator.txt",
        )

        files_text = ""
        for path, content in generated_files.items():
            if path.endswith(".py"):
                files_text += f"\n# === {path} ===\n{content[:3000]}\n"

        if os.path.exists(prompt_path):
            with open(prompt_path) as f:
                template = f.read()
            template = template.replace("{{generated_files}}", files_text[:25000])
            template = template.replace(
                "{{strategy_extraction}}",
                json.dumps(strategy_extraction, default=str)[:8000],
            )
            template = template.replace(
                "{{backtest_results}}",
                json.dumps(backtest_results or {}, default=str)[:3000],
            )
            prompt = template
        else:
            prompt = self._default_llm_prompt(
                files_text, strategy_extraction, backtest_results
            )

        from providers.base import GenerationConfig

        config = GenerationConfig(
            temperature=0.1,
            max_output_tokens=4096,
            response_format="json",
        )

        try:
            result = self.provider.generate(prompt, config=config)
            data = self._extract_json(result.text)
        except Exception as e:
            logger.warning("LLM backtest validation failed: %s", e)
            return []

        checks: List[BiasCheck] = []
        for check_data in data.get("checks", []):
            checks.append(BiasCheck(
                name=check_data.get("name", ""),
                passed=check_data.get("passed", True),
                severity=check_data.get("severity", "info"),
                description=check_data.get("description", ""),
                recommendation=check_data.get("recommendation", ""),
            ))
        return checks

    def _default_llm_prompt(
        self,
        files_text: str,
        strategy_extraction: dict,
        backtest_results: Optional[dict],
    ) -> str:
        """Build fallback prompt when template file is missing."""
        return f"""Validate this backtest for common pitfalls.

FILES:
{files_text[:25000]}

STRATEGY:
{json.dumps(strategy_extraction, default=str)[:8000]}

BACKTEST RESULTS:
{json.dumps(backtest_results or {}, default=str)[:3000]}

Check for: survivorship bias, look-ahead bias, point-in-time data issues,
rebalancing timing, transaction costs, data snooping, capacity constraints.

Return JSON: {{"checks": [{{"name": "...", "passed": true/false, "severity": "critical/warning/info", "description": "...", "recommendation": "..."}}], "bias_risk_score": 0-100}}"""

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

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
        return {"checks": []}
