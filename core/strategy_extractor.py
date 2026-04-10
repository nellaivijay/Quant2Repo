"""Strategy extractor — extracts trading strategy components from quant papers.

This is the quant-specific equivalent of Research2Repo's PaperAnalyzer.
Instead of extracting ML architecture, it extracts:
- Signal construction methodology
- Portfolio formation rules
- Rebalancing frequency
- Asset universe
- Reported performance metrics
"""

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SignalConstruction:
    """How a trading signal is constructed."""
    signal_type: str = ""  # momentum, value, carry, etc.
    formula: str = ""  # LaTeX or text formula
    lookback_period: str = ""  # e.g., "12 months"
    formation_period: str = ""
    skip_period: str = ""  # e.g., "1 month" for 12-1 momentum
    normalization: str = ""  # cross-sectional rank, z-score, etc.
    is_cross_sectional: bool = True
    is_time_series: bool = False
    combination_weights: dict = field(default_factory=dict)
    detailed_steps: list = field(default_factory=list)


@dataclass
class PortfolioConstruction:
    """How portfolios are formed from signals."""
    method: str = ""  # quartile, decile, long-short, long-only, threshold
    long_leg: str = ""  # e.g., "top quartile"
    short_leg: str = ""  # e.g., "bottom quartile"
    weighting: str = ""  # equal-weight, value-weight, signal-weight
    rebalancing_frequency: str = ""
    rebalancing_lag: str = ""  # e.g., "1 month"
    max_positions: int = 0
    turnover_constraints: str = ""


@dataclass
class ReportedResults:
    """Performance metrics as reported in the paper."""
    annual_return: Optional[float] = None
    annual_volatility: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    t_statistic: Optional[float] = None
    sample_period: str = ""
    benchmark: str = ""
    additional_metrics: dict = field(default_factory=dict)


@dataclass
class StrategyExtraction:
    """Complete extraction of a trading strategy from a paper."""
    strategy_name: str = ""
    authors: list = field(default_factory=list)
    publication_year: Optional[int] = None
    abstract_summary: str = ""

    # Asset universe
    asset_classes: list = field(default_factory=list)
    instrument_types: list = field(default_factory=list)
    universe_description: str = ""
    universe_filters: list = field(default_factory=list)

    # Signal
    signals: list = field(default_factory=list)  # list[SignalConstruction]
    signal_combination: str = ""

    # Portfolio
    portfolio: Optional[PortfolioConstruction] = None

    # Data requirements
    data_requirements: list = field(default_factory=list)
    data_frequency: str = ""
    data_sources_mentioned: list = field(default_factory=list)

    # Results
    reported_results: Optional[ReportedResults] = None
    robustness_tests: list = field(default_factory=list)
    transaction_cost_assumptions: str = ""

    # Key equations
    key_equations: list = field(default_factory=list)

    # Risk model
    risk_model: str = ""

    # Raw analysis text
    raw_analysis: str = ""


class StrategyExtractor:
    """Extracts trading strategy components from a quant paper using LLM."""

    def __init__(self, provider, config=None):
        self.provider = provider
        self.config = config
        self._prompt_template = self._load_prompt()

    def _load_prompt(self) -> str:
        """Load the strategy extractor prompt template."""
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "prompts", "strategy_extractor.txt"
        )
        if os.path.exists(prompt_path):
            with open(prompt_path) as f:
                return f.read()
        return self._default_prompt()

    def _default_prompt(self) -> str:
        """Default prompt if template file not found."""
        return """You are a quantitative finance expert analyzing a research paper.
Extract ALL trading strategy components from the following paper.

PAPER TEXT:
{{paper_text}}

Return a JSON object with these fields:
{
    "strategy_name": "Name of the strategy",
    "authors": ["Author1", "Author2"],
    "publication_year": 2020,
    "asset_classes": ["equities", "bonds", ...],
    "signal_types": ["momentum", "value", ...],
    "signals": [
        {
            "signal_type": "momentum",
            "formula": "r_{t-12,t-1}",
            "lookback_period": "12 months",
            "formation_period": "12 months",
            "skip_period": "1 month",
            "normalization": "cross-sectional rank",
            "is_cross_sectional": true,
            "is_time_series": false,
            "detailed_steps": ["Step 1: ...", "Step 2: ..."]
        }
    ],
    "signal_combination": "Description of how signals are combined",
    "portfolio_construction": {
        "method": "quartile sort",
        "long_leg": "top quartile",
        "short_leg": "bottom quartile",
        "weighting": "equal-weight",
        "rebalancing_frequency": "monthly",
        "rebalancing_lag": "1 month",
        "max_positions": 0
    },
    "universe_description": "Description of the investment universe",
    "universe_filters": ["Filter 1", "Filter 2"],
    "data_requirements": ["monthly returns", "book-to-market ratio", ...],
    "data_frequency": "monthly",
    "reported_results": {
        "annual_return": 0.12,
        "annual_volatility": 0.15,
        "sharpe_ratio": 0.8,
        "max_drawdown": -0.25,
        "t_statistic": 3.2,
        "sample_period": "1990-2020",
        "benchmark": "equal-weighted market"
    },
    "robustness_tests": ["subperiod analysis", "transaction costs", ...],
    "transaction_cost_assumptions": "10 bps per trade",
    "key_equations": ["r_{i,t} = ...", "signal_{i,t} = ..."],
    "risk_model": "Description of risk management approach"
}

Extract EVERY equation, parameter, and methodological detail.
Missing a single signal construction step will produce incorrect backtest results."""

    def extract(self, paper_text: str,
                paper_title: str = "",
                uploaded_file=None) -> StrategyExtraction:
        """Extract strategy components from paper text."""
        from providers.base import GenerationConfig

        prompt = self._prompt_template.replace("{{paper_text}}", paper_text)
        if paper_title:
            prompt = prompt.replace("{{paper_title}}", paper_title)

        config = GenerationConfig(
            temperature=0.1,
            max_output_tokens=8192,
            response_format="json",
        )

        if uploaded_file is not None:
            result = self.provider.generate_with_file(
                uploaded_file, prompt, config=config
            )
        else:
            result = self.provider.generate(prompt, config=config)

        return self._parse_response(result.text)

    def _parse_response(self, text: str) -> StrategyExtraction:
        """Parse LLM response into StrategyExtraction."""
        # Try JSON parsing first
        try:
            data = self._extract_json(text)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Failed to parse JSON, attempting text extraction")
            return StrategyExtraction(raw_analysis=text)

        extraction = StrategyExtraction()
        extraction.raw_analysis = text

        extraction.strategy_name = data.get("strategy_name", "")
        extraction.authors = data.get("authors", [])
        extraction.publication_year = data.get("publication_year")
        extraction.asset_classes = data.get("asset_classes", [])

        # Parse signals
        for sig_data in data.get("signals", []):
            sig = SignalConstruction(
                signal_type=sig_data.get("signal_type", ""),
                formula=sig_data.get("formula", ""),
                lookback_period=sig_data.get("lookback_period", ""),
                formation_period=sig_data.get("formation_period", ""),
                skip_period=sig_data.get("skip_period", ""),
                normalization=sig_data.get("normalization", ""),
                is_cross_sectional=sig_data.get("is_cross_sectional", True),
                is_time_series=sig_data.get("is_time_series", False),
                combination_weights=sig_data.get("combination_weights", {}),
                detailed_steps=sig_data.get("detailed_steps", []),
            )
            extraction.signals.append(sig)

        extraction.signal_combination = data.get("signal_combination", "")

        # Parse portfolio construction
        pc_data = data.get("portfolio_construction", {})
        if pc_data:
            extraction.portfolio = PortfolioConstruction(
                method=pc_data.get("method", ""),
                long_leg=pc_data.get("long_leg", ""),
                short_leg=pc_data.get("short_leg", ""),
                weighting=pc_data.get("weighting", ""),
                rebalancing_frequency=pc_data.get("rebalancing_frequency", ""),
                rebalancing_lag=pc_data.get("rebalancing_lag", ""),
                max_positions=pc_data.get("max_positions", 0),
                turnover_constraints=pc_data.get("turnover_constraints", ""),
            )

        extraction.universe_description = data.get("universe_description", "")
        extraction.universe_filters = data.get("universe_filters", [])
        extraction.data_requirements = data.get("data_requirements", [])
        extraction.data_frequency = data.get("data_frequency", "")

        # Parse reported results
        rr_data = data.get("reported_results", {})
        if rr_data:
            extraction.reported_results = ReportedResults(
                annual_return=rr_data.get("annual_return"),
                annual_volatility=rr_data.get("annual_volatility"),
                sharpe_ratio=rr_data.get("sharpe_ratio"),
                max_drawdown=rr_data.get("max_drawdown"),
                t_statistic=rr_data.get("t_statistic"),
                sample_period=rr_data.get("sample_period", ""),
                benchmark=rr_data.get("benchmark", ""),
                additional_metrics=rr_data.get("additional_metrics", {}),
            )

        extraction.robustness_tests = data.get("robustness_tests", [])
        extraction.transaction_cost_assumptions = data.get("transaction_cost_assumptions", "")
        extraction.key_equations = data.get("key_equations", [])
        extraction.risk_model = data.get("risk_model", "")

        return extraction

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from LLM response text."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))

        # Try finding JSON object
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            return json.loads(text[brace_start:brace_end + 1])

        raise ValueError("No JSON found in response")
