"""Performance metrics definitions and validation utilities.

Provides :class:`MetricSpec` dataclasses for every standard backtest metric,
a registry of all metrics in :data:`ALL_METRICS`, and a :func:`compare`
function that validates paper-reported metrics against computed values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# MetricSpec dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricSpec:
    """Specification for a single performance metric.

    Attributes
    ----------
    name : str
        Canonical short name (e.g. ``"sharpe_ratio"``).
    display_name : str
        Human-friendly label.
    formula : str
        LaTeX-style formula string.
    description : str
        Plain-English description of the metric and its interpretation.
    unit : str
        Unit of the metric (e.g. ``"%"``, ``"ratio"``, ``"bps"``).
    higher_is_better : bool
        ``True`` if larger values indicate better performance.
    typical_range : tuple[float, float]
        Typical (low, high) range for the metric in practice.
    requires : list[str]
        Names of input series needed to compute (e.g. ``["returns"]``).
    """

    name: str
    display_name: str
    formula: str
    description: str
    unit: str = "ratio"
    higher_is_better: bool = True
    typical_range: Tuple[float, float] = (float("-inf"), float("inf"))
    requires: Tuple[str, ...] = ("returns",)


# ---------------------------------------------------------------------------
# Standard metric definitions
# ---------------------------------------------------------------------------

ANNUAL_RETURN = MetricSpec(
    name="annual_return",
    display_name="Annualized Return",
    formula=r"R_a = (1 + R_{total})^{252/N} - 1",
    description=(
        "Compound annual growth rate (CAGR) of the strategy. Converts the "
        "total cumulative return into an equivalent constant annual return "
        "assuming 252 trading days per year."
    ),
    unit="%",
    higher_is_better=True,
    typical_range=(-0.50, 1.00),
    requires=("returns",),
)

ANNUAL_VOLATILITY = MetricSpec(
    name="annual_volatility",
    display_name="Annualized Volatility",
    formula=r"\sigma_a = \sigma_{daily} \times \sqrt{252}",
    description=(
        "Annualized standard deviation of daily returns. Measures the total "
        "risk (both upside and downside) of the strategy on an annual basis."
    ),
    unit="%",
    higher_is_better=False,
    typical_range=(0.0, 1.00),
    requires=("returns",),
)

SHARPE_RATIO = MetricSpec(
    name="sharpe_ratio",
    display_name="Sharpe Ratio",
    formula=r"SR = \frac{R_a - R_f}{\sigma_a}",
    description=(
        "Ratio of excess annualized return over the risk-free rate to "
        "annualized volatility. The gold-standard risk-adjusted return "
        "measure. A Sharpe > 1.0 is generally considered strong."
    ),
    unit="ratio",
    higher_is_better=True,
    typical_range=(-2.0, 4.0),
    requires=("returns", "risk_free_rate"),
)

SORTINO_RATIO = MetricSpec(
    name="sortino_ratio",
    display_name="Sortino Ratio",
    formula=r"Sortino = \frac{R_a - R_f}{\sigma_{downside}}",
    description=(
        "Like the Sharpe ratio but penalises only downside volatility. Uses "
        "the standard deviation of negative returns (downside deviation) in "
        "the denominator, giving a clearer picture for asymmetric return "
        "distributions."
    ),
    unit="ratio",
    higher_is_better=True,
    typical_range=(-3.0, 6.0),
    requires=("returns", "risk_free_rate"),
)

MAX_DRAWDOWN = MetricSpec(
    name="max_drawdown",
    display_name="Maximum Drawdown",
    formula=r"MDD = \max_{t} \left( \frac{Peak_t - Trough_t}{Peak_t} \right)",
    description=(
        "Largest peak-to-trough decline in cumulative returns before a new "
        "high is reached. Measures the worst-case loss an investor would "
        "have experienced."
    ),
    unit="%",
    higher_is_better=False,
    typical_range=(0.0, 1.0),
    requires=("returns",),
)

CALMAR_RATIO = MetricSpec(
    name="calmar_ratio",
    display_name="Calmar Ratio",
    formula=r"Calmar = \frac{R_a}{|MDD|}",
    description=(
        "Annualized return divided by the absolute maximum drawdown. "
        "Measures return per unit of drawdown risk. Higher values indicate "
        "better risk-adjusted performance relative to worst-case losses."
    ),
    unit="ratio",
    higher_is_better=True,
    typical_range=(0.0, 10.0),
    requires=("returns",),
)

INFORMATION_RATIO = MetricSpec(
    name="information_ratio",
    display_name="Information Ratio",
    formula=r"IR = \frac{R_p - R_b}{\sigma_{R_p - R_b}}",
    description=(
        "Excess return of the strategy over its benchmark divided by the "
        "tracking error (standard deviation of excess returns). Measures "
        "consistency of alpha generation."
    ),
    unit="ratio",
    higher_is_better=True,
    typical_range=(-2.0, 3.0),
    requires=("returns", "benchmark_returns"),
)

HIT_RATE = MetricSpec(
    name="hit_rate",
    display_name="Hit Rate (Win Rate)",
    formula=r"HitRate = \frac{\text{# winning trades}}{\text{# total trades}}",
    description=(
        "Fraction of trades that are profitable. A hit rate above 50% is "
        "desirable, though strategies with low hit rate can still be "
        "profitable if average win >> average loss."
    ),
    unit="%",
    higher_is_better=True,
    typical_range=(0.0, 1.0),
    requires=("trade_returns",),
)

PROFIT_FACTOR = MetricSpec(
    name="profit_factor",
    display_name="Profit Factor",
    formula=r"PF = \frac{\sum \text{gross profits}}{\sum |\text{gross losses}|}",
    description=(
        "Ratio of total gross profits to total gross losses across all "
        "trades. A profit factor > 1.0 means the strategy is net profitable."
    ),
    unit="ratio",
    higher_is_better=True,
    typical_range=(0.0, 5.0),
    requires=("trade_returns",),
)

VAR_95 = MetricSpec(
    name="var_95",
    display_name="Value at Risk (95%)",
    formula=r"VaR_{0.95} = -Q_{0.05}(R)",
    description=(
        "The 5th percentile of the return distribution (negated). "
        "Represents the maximum expected loss over one period with 95% "
        "confidence under normal market conditions."
    ),
    unit="%",
    higher_is_better=False,
    typical_range=(0.0, 0.20),
    requires=("returns",),
)

CVAR_95 = MetricSpec(
    name="cvar_95",
    display_name="Conditional VaR (95%)",
    formula=r"CVaR_{0.95} = -E[R \mid R \leq -VaR_{0.95}]",
    description=(
        "Expected loss given that the loss exceeds the 95% VaR threshold. "
        "Also called Expected Shortfall (ES). Captures tail risk better "
        "than VaR alone."
    ),
    unit="%",
    higher_is_better=False,
    typical_range=(0.0, 0.30),
    requires=("returns",),
)

TURNOVER = MetricSpec(
    name="turnover",
    display_name="Portfolio Turnover",
    formula=r"Turnover = \frac{1}{T} \sum_t \sum_i |w_{i,t} - w_{i,t-1}|",
    description=(
        "Average absolute change in portfolio weights per rebalancing "
        "period. Higher turnover means higher transaction costs and tax "
        "drag."
    ),
    unit="ratio",
    higher_is_better=False,
    typical_range=(0.0, 20.0),
    requires=("weights",),
)

TRACKING_ERROR = MetricSpec(
    name="tracking_error",
    display_name="Tracking Error",
    formula=r"TE = \sigma(R_p - R_b) \times \sqrt{252}",
    description=(
        "Annualized standard deviation of excess returns relative to a "
        "benchmark. Measures how closely the strategy tracks its benchmark."
    ),
    unit="%",
    higher_is_better=False,
    typical_range=(0.0, 0.30),
    requires=("returns", "benchmark_returns"),
)

BETA = MetricSpec(
    name="beta",
    display_name="Beta",
    formula=r"\beta = \frac{Cov(R_p, R_b)}{Var(R_b)}",
    description=(
        "Sensitivity of the strategy returns to benchmark (market) returns. "
        "A beta of 1.0 means the strategy moves one-for-one with the market."
    ),
    unit="ratio",
    higher_is_better=False,  # context-dependent; lower = more market-neutral
    typical_range=(-1.0, 2.0),
    requires=("returns", "benchmark_returns"),
)

ALPHA = MetricSpec(
    name="alpha",
    display_name="Alpha (Jensen's)",
    formula=r"\alpha = R_p - [R_f + \beta (R_b - R_f)]",
    description=(
        "Jensen's alpha: the excess return of the strategy beyond what is "
        "explained by its market beta. Positive alpha indicates skill-based "
        "outperformance."
    ),
    unit="%",
    higher_is_better=True,
    typical_range=(-0.20, 0.20),
    requires=("returns", "benchmark_returns", "risk_free_rate"),
)

T_STATISTIC = MetricSpec(
    name="t_statistic",
    display_name="t-Statistic of Returns",
    formula=r"t = \frac{\bar{R}}{\sigma_R / \sqrt{N}}",
    description=(
        "Statistical significance of the mean return. A t-stat above ~2.0 "
        "is typically considered significant at the 5% level, suggesting "
        "the strategy's returns are unlikely due to chance."
    ),
    unit="ratio",
    higher_is_better=True,
    typical_range=(-4.0, 6.0),
    requires=("returns",),
)


# ---------------------------------------------------------------------------
# Registry of all metrics
# ---------------------------------------------------------------------------

ALL_METRICS: Dict[str, MetricSpec] = {
    m.name: m
    for m in [
        ANNUAL_RETURN,
        ANNUAL_VOLATILITY,
        SHARPE_RATIO,
        SORTINO_RATIO,
        MAX_DRAWDOWN,
        CALMAR_RATIO,
        INFORMATION_RATIO,
        HIT_RATE,
        PROFIT_FACTOR,
        VAR_95,
        CVAR_95,
        TURNOVER,
        TRACKING_ERROR,
        BETA,
        ALPHA,
        T_STATISTIC,
    ]
}


def get_metric(name: str) -> Optional[MetricSpec]:
    """Look up a metric specification by canonical name."""
    return ALL_METRICS.get(name)


def list_metrics() -> List[MetricSpec]:
    """Return all registered metric specifications."""
    return list(ALL_METRICS.values())


# ---------------------------------------------------------------------------
# Validation / comparison
# ---------------------------------------------------------------------------


@dataclass
class MetricValidationResult:
    """Result of comparing a single paper-reported vs. computed metric."""

    metric_name: str
    paper_value: float
    computed_value: float
    absolute_error: float
    relative_error: Optional[float]  # None if paper_value == 0
    within_tolerance: bool
    tolerance_used: float
    note: str = ""


@dataclass
class ValidationReport:
    """Full validation report comparing paper and computed metrics."""

    results: List[MetricValidationResult] = field(default_factory=list)
    total_metrics: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def pass_rate(self) -> float:
        """Fraction of metrics that pass validation."""
        if self.total_metrics == 0:
            return 0.0
        return self.passed / self.total_metrics

    @property
    def summary(self) -> str:
        """One-line summary string."""
        return (
            f"Validation: {self.passed}/{self.total_metrics} passed "
            f"({self.pass_rate:.0%}), {self.failed} failed, "
            f"{self.skipped} skipped"
        )


# Default tolerances per metric (absolute)
_DEFAULT_TOLERANCES: Dict[str, float] = {
    "annual_return": 0.03,       # 3 pp
    "annual_volatility": 0.03,   # 3 pp
    "sharpe_ratio": 0.20,        # 0.20 units
    "sortino_ratio": 0.30,
    "max_drawdown": 0.05,        # 5 pp
    "calmar_ratio": 0.30,
    "information_ratio": 0.20,
    "hit_rate": 0.05,
    "profit_factor": 0.30,
    "var_95": 0.02,
    "cvar_95": 0.03,
    "turnover": 1.0,
    "tracking_error": 0.03,
    "beta": 0.15,
    "alpha": 0.03,
    "t_statistic": 0.50,
}


def compare(
    paper_metrics: Dict[str, float],
    computed_metrics: Dict[str, float],
    *,
    tolerances: Optional[Dict[str, float]] = None,
    default_tolerance: float = 0.25,
) -> ValidationReport:
    """Compare paper-reported metrics with computed metrics.

    Parameters
    ----------
    paper_metrics : dict[str, float]
        Metrics as reported in the original paper.
    computed_metrics : dict[str, float]
        Metrics computed from a backtest.
    tolerances : dict[str, float], optional
        Per-metric absolute tolerance overrides.
    default_tolerance : float
        Fallback tolerance for metrics not in *tolerances*.

    Returns
    -------
    ValidationReport
        Detailed comparison results.

    Examples
    --------
    >>> report = compare(
    ...     {"sharpe_ratio": 0.576, "annual_volatility": 0.205},
    ...     {"sharpe_ratio": 0.61, "annual_volatility": 0.198},
    ... )
    >>> print(report.summary)
    Validation: 2/2 passed (100%), 0 failed, 0 skipped
    """
    tols = {**_DEFAULT_TOLERANCES, **(tolerances or {})}
    report = ValidationReport()

    all_keys = set(paper_metrics) | set(computed_metrics)
    for key in sorted(all_keys):
        report.total_metrics += 1

        if key not in paper_metrics or key not in computed_metrics:
            report.skipped += 1
            report.results.append(
                MetricValidationResult(
                    metric_name=key,
                    paper_value=paper_metrics.get(key, float("nan")),
                    computed_value=computed_metrics.get(key, float("nan")),
                    absolute_error=float("nan"),
                    relative_error=None,
                    within_tolerance=False,
                    tolerance_used=0.0,
                    note="Missing from one side",
                )
            )
            continue

        pv = paper_metrics[key]
        cv = computed_metrics[key]
        abs_err = abs(pv - cv)
        rel_err = abs_err / abs(pv) if pv != 0.0 else None
        tol = tols.get(key, default_tolerance)
        passed = abs_err <= tol

        if passed:
            report.passed += 1
        else:
            report.failed += 1

        report.results.append(
            MetricValidationResult(
                metric_name=key,
                paper_value=pv,
                computed_value=cv,
                absolute_error=round(abs_err, 6),
                relative_error=round(rel_err, 6) if rel_err is not None else None,
                within_tolerance=passed,
                tolerance_used=tol,
            )
        )

    return report
