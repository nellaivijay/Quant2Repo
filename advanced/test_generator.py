"""Test generator for backtest repositories.

Generates ``pytest``-based test files that validate:

- Signal calculation correctness and no look-ahead bias.
- Portfolio construction logic.
- Performance metric calculations.
- Config parameter usage (no hardcoded magic numbers).
- Data loading and preprocessing.
- Edge cases (empty data, missing values, single-asset universe).

The generated tests use synthetic data so they run without external
market-data dependencies.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TestGenerator:
    """Generates pytest test files for a generated backtest.

    Parameters:
        provider: An LLM provider instance.
        config: Optional :class:`Q2RConfig`.
    """

    # Canonical test files and what they cover.
    _TEST_SPECS: List[Dict[str, str]] = [
        {
            "path": "tests/test_signals.py",
            "focus": "signal_correctness",
            "description": (
                "Test signal calculations: correct formula implementation, "
                "no look-ahead bias (signal at time t uses data <= t), "
                "proper handling of NaN/missing values, cross-sectional "
                "ranking when applicable."
            ),
        },
        {
            "path": "tests/test_portfolio.py",
            "focus": "portfolio_construction",
            "description": (
                "Test portfolio formation: correct sorting into quantiles, "
                "weight normalisation (sum to 1 or net-zero for long-short), "
                "rebalancing frequency matches config, transaction cost "
                "application."
            ),
        },
        {
            "path": "tests/test_metrics.py",
            "focus": "performance_metrics",
            "description": (
                "Test metric calculations: Sharpe ratio, max drawdown, "
                "annual return, volatility, turnover.  Use known synthetic "
                "return series with hand-computed expected values."
            ),
        },
        {
            "path": "tests/test_data.py",
            "focus": "data_loading",
            "description": (
                "Test data loading: column names, date parsing, handling "
                "of missing tickers, forward-fill logic, proper date "
                "alignment between price and signal data."
            ),
        },
        {
            "path": "tests/test_config.py",
            "focus": "config_usage",
            "description": (
                "Test that all tunable parameters come from config.py, "
                "verify default values are sensible, ensure config "
                "overrides propagate to signal/portfolio modules."
            ),
        },
    ]

    def __init__(
        self,
        provider: Any,
        config: Optional[Any] = None,
    ) -> None:
        self.provider = provider
        self.config = config

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def generate(
        self,
        generated_files: Dict[str, str],
        paper_text: str,
        strategy_extraction: dict,
    ) -> Dict[str, str]:
        """Generate pytest test files for the backtest.

        Args:
            generated_files: Current mapping of path → source content.
            paper_text: Full paper text (used for context).
            strategy_extraction: Extracted strategy details.

        Returns:
            Mapping of test file path → test source code.
        """
        test_files: Dict[str, str] = {}

        # Ensure tests/ directory has an __init__.py
        test_files["tests/__init__.py"] = ""

        # Generate a conftest.py with shared fixtures
        test_files["tests/conftest.py"] = self._generate_conftest(
            generated_files, strategy_extraction
        )

        # Generate each test module
        for spec in self._TEST_SPECS:
            # Only generate tests for files that actually exist
            if not self._has_relevant_source(spec["focus"], generated_files):
                continue

            try:
                content = self._generate_test_file(
                    spec, generated_files, paper_text, strategy_extraction
                )
                test_files[spec["path"]] = content
            except Exception as e:
                logger.warning("Failed to generate %s: %s", spec["path"], e)

        return test_files

    # ──────────────────────────────────────────────────────────────────
    # conftest.py generation
    # ──────────────────────────────────────────────────────────────────

    def _generate_conftest(
        self,
        generated_files: Dict[str, str],
        strategy_extraction: dict,
    ) -> str:
        """Generate a conftest.py with shared fixtures."""
        data_freq = "D"
        if isinstance(strategy_extraction, dict):
            freq = strategy_extraction.get("data_frequency", "daily")
            freq_map = {
                "daily": "D", "weekly": "W", "monthly": "ME",
                "quarterly": "QE", "annual": "YE",
            }
            data_freq = freq_map.get(freq.lower(), "D")

        n_assets = 10
        n_periods = 252

        return f'''"""Shared pytest fixtures for backtest tests."""

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def rng():
    """Seeded random number generator for reproducibility."""
    return np.random.default_rng(42)


@pytest.fixture
def synthetic_prices(rng):
    """Generate synthetic price data for {n_assets} assets over {n_periods} periods."""
    dates = pd.date_range("2020-01-01", periods={n_periods}, freq="{data_freq}")
    tickers = [f"ASSET_{{i:02d}}" for i in range({n_assets})]

    # Geometric Brownian Motion
    mu = 0.0005  # daily drift
    sigma = 0.02  # daily vol
    log_returns = rng.normal(mu, sigma, size=({n_periods}, {n_assets}))
    prices = 100 * np.exp(np.cumsum(log_returns, axis=0))

    return pd.DataFrame(prices, index=dates, columns=tickers)


@pytest.fixture
def synthetic_returns(synthetic_prices):
    """Daily returns derived from synthetic prices."""
    return synthetic_prices.pct_change().dropna()


@pytest.fixture
def sample_config():
    """Minimal config dict for testing."""
    return {{
        "start_date": "2020-01-01",
        "end_date": "2021-12-31",
        "initial_capital": 1_000_000,
        "transaction_cost_bps": 10,
        "rebalancing_frequency": "monthly",
        "num_quantiles": 5,
        "lookback_period": 12,
    }}


@pytest.fixture
def flat_returns():
    """Returns series that is exactly zero — useful for edge-case tests."""
    dates = pd.date_range("2020-01-01", periods=252, freq="D")
    return pd.Series(0.0, index=dates, name="flat")


@pytest.fixture
def known_sharpe_returns():
    """Returns series with a known Sharpe ratio of ~1.0 (annualised).

    Daily mean=0.0004, daily std=0.01 → annualised ≈ 0.10/0.16 ≈ 0.63
    """
    dates = pd.date_range("2020-01-01", periods=252, freq="D")
    rng_local = np.random.default_rng(99)
    rets = rng_local.normal(0.0004, 0.01, size=252)
    return pd.Series(rets, index=dates, name="known")
'''

    # ──────────────────────────────────────────────────────────────────
    # Per-file generation
    # ──────────────────────────────────────────────────────────────────

    def _generate_test_file(
        self,
        spec: Dict[str, str],
        generated_files: Dict[str, str],
        paper_text: str,
        strategy_extraction: dict,
    ) -> str:
        """Generate a single test file via the LLM."""
        # Gather relevant source files
        relevant = self._get_relevant_sources(spec["focus"], generated_files)
        source_text = ""
        for path, content in relevant.items():
            source_text += f"\n# === {path} ===\n{content[:4000]}\n"

        prompt = self._build_prompt(spec, source_text, strategy_extraction)

        from providers.base import GenerationConfig

        config = GenerationConfig(temperature=0.15, max_output_tokens=8192)

        try:
            result = self.provider.generate(prompt, config=config)
            return self._clean_output(result.text)
        except Exception as e:
            logger.warning("LLM test generation failed for %s: %s", spec["path"], e)
            return self._fallback_test(spec)

    def _build_prompt(
        self,
        spec: Dict[str, str],
        source_text: str,
        strategy_extraction: dict,
    ) -> str:
        """Build the test-generation prompt."""
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts",
            "test_generator.txt",
        )

        strategy_json = json.dumps(strategy_extraction, default=str)[:5000]

        if os.path.exists(prompt_path):
            with open(prompt_path) as f:
                template = f.read()
            template = template.replace("{{test_focus}}", spec["focus"])
            template = template.replace("{{test_description}}", spec["description"])
            template = template.replace("{{source_code}}", source_text[:20000])
            template = template.replace("{{strategy_extraction}}", strategy_json)
            return template

        return f"""Generate a pytest test file for: {spec['description']}

SOURCE CODE UNDER TEST:
{source_text[:20000]}

STRATEGY DETAILS:
{strategy_json}

REQUIREMENTS:
- Use synthetic data (numpy/pandas) — NO external API calls.
- Test edge cases: empty data, single asset, all NaN column.
- For signal tests: verify no look-ahead bias by checking that
  signal[t] depends only on data[<=t].
- For portfolio tests: verify weights sum correctly.
- For metric tests: use hand-computed expected values.
- Include docstrings on every test function.
- Import the module under test at the top.
- Use fixtures from conftest.py where appropriate.

Return ONLY the Python test code. No markdown fences."""

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _has_relevant_source(focus: str, files: Dict[str, str]) -> bool:
        """Check whether there is source code relevant to the test focus."""
        focus_map: Dict[str, List[str]] = {
            "signal_correctness": ["signal", "factor", "alpha"],
            "portfolio_construction": ["portfolio", "position", "weight"],
            "performance_metrics": ["analysis", "metric", "performance", "evaluation"],
            "data_loading": ["data", "loader", "fetch"],
            "config_usage": ["config"],
        }
        keywords = focus_map.get(focus, [])
        for path in files:
            if any(kw in path.lower() for kw in keywords):
                return True
        return bool(files)  # fallback: always True if there are any files

    @staticmethod
    def _get_relevant_sources(
        focus: str, files: Dict[str, str]
    ) -> Dict[str, str]:
        """Return source files most relevant to the test focus."""
        focus_map: Dict[str, List[str]] = {
            "signal_correctness": ["signal", "factor", "alpha", "config"],
            "portfolio_construction": ["portfolio", "position", "weight", "config"],
            "performance_metrics": ["analysis", "metric", "performance", "config"],
            "data_loading": ["data", "loader", "fetch", "config"],
            "config_usage": ["config"],
        }
        keywords = focus_map.get(focus, [])
        relevant: Dict[str, str] = {}
        for path, content in files.items():
            if not path.endswith(".py"):
                continue
            if any(kw in path.lower() for kw in keywords):
                relevant[path] = content
        # Always include config.py if present
        if "config.py" in files and "config.py" not in relevant:
            relevant["config.py"] = files["config.py"]
        return relevant

    @staticmethod
    def _clean_output(text: str) -> str:
        """Strip markdown fences from LLM output."""
        match = re.search(
            r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL
        )
        if match:
            text = match.group(1)
        return text.strip()

    @staticmethod
    def _fallback_test(spec: Dict[str, str]) -> str:
        """Return a minimal placeholder test when LLM generation fails."""
        return f'''"""Auto-generated placeholder tests for {spec["focus"]}."""

import pytest


class Test{spec["focus"].title().replace("_", "")}:
    """Placeholder — LLM generation failed; fill in manually."""

    def test_placeholder(self):
        """Remove this and add real tests."""
        pytest.skip("Auto-generation failed — implement manually")
'''
