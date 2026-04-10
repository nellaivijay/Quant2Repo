"""Signal type definitions for quant strategies.

Defines the canonical signal taxonomy, typical configurations for each
signal type, and helper utilities for classifying signals from paper text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Signal type enum
# ---------------------------------------------------------------------------


class SignalType(str, Enum):
    """Canonical signal types used across the strategy catalog."""

    MOMENTUM = "momentum"
    VALUE = "value"
    CARRY = "carry"
    MEAN_REVERSION = "mean_reversion"
    VOLATILITY = "volatility"
    QUALITY = "quality"
    SENTIMENT = "sentiment"
    SEASONAL = "seasonal"
    TREND_FOLLOWING = "trend_following"
    STATISTICAL_ARBITRAGE = "statistical_arbitrage"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, s: str) -> "SignalType":
        """Parse a signal type from a string (case-insensitive, tolerant).

        Accepts both enum names (``MOMENTUM``) and values
        (``momentum``, ``mean_reversion``).
        """
        normalised = s.strip().lower().replace("-", "_").replace(" ", "_")
        for member in cls:
            if normalised in (member.value, member.name.lower()):
                return member
        raise ValueError(f"Unknown signal type: {s!r}")


# ---------------------------------------------------------------------------
# Signal specification dataclass
# ---------------------------------------------------------------------------


@dataclass
class SignalSpec:
    """Specification for a trading signal.

    Attributes
    ----------
    type : SignalType
        The canonical signal category.
    lookback_period : int
        Number of periods used to compute the signal (e.g. 12 months).
    formation_period : int
        Number of periods over which the signal is formed / ranked.
    holding_period : int
        Target holding period in the same time unit as lookback.
    cross_sectional : bool
        ``True`` if the signal ranks assets relative to peers
        (cross-section), ``False`` if purely time-series.
    time_series : bool
        ``True`` if the signal is computed independently per asset
        (time-series).
    description : str
        Human-readable description of the signal.
    keywords : list[str]
        Keywords associated with this signal for text classification.
    """

    type: SignalType
    lookback_period: int = 0
    formation_period: int = 0
    holding_period: int = 0
    cross_sectional: bool = False
    time_series: bool = True
    description: str = ""
    keywords: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Known signal configurations
# ---------------------------------------------------------------------------

KNOWN_SIGNALS: Dict[str, SignalSpec] = {
    # --- Momentum family ---
    "time_series_momentum": SignalSpec(
        type=SignalType.MOMENTUM,
        lookback_period=12,
        formation_period=12,
        holding_period=1,
        cross_sectional=False,
        time_series=True,
        description=(
            "Classic time-series momentum: go long (short) assets with positive "
            "(negative) excess returns over the past 12 months."
        ),
        keywords=["momentum", "trend", "time series", "12-month", "tsmom"],
    ),
    "cross_sectional_momentum": SignalSpec(
        type=SignalType.MOMENTUM,
        lookback_period=12,
        formation_period=12,
        holding_period=1,
        cross_sectional=True,
        time_series=False,
        description=(
            "Cross-sectional momentum: rank assets by past returns and go "
            "long winners / short losers."
        ),
        keywords=["momentum", "cross-section", "winners", "losers", "relative strength"],
    ),
    "sector_rotation_momentum": SignalSpec(
        type=SignalType.MOMENTUM,
        lookback_period=6,
        formation_period=6,
        holding_period=1,
        cross_sectional=True,
        time_series=False,
        description="Rotate among sectors using 6-month momentum ranking.",
        keywords=["sector", "rotation", "momentum", "relative"],
    ),

    # --- Value family ---
    "book_to_market": SignalSpec(
        type=SignalType.VALUE,
        lookback_period=0,
        formation_period=0,
        holding_period=12,
        cross_sectional=True,
        time_series=False,
        description="Classic HML factor: rank stocks by book-to-market ratio.",
        keywords=["value", "book-to-market", "B/M", "HML", "cheap", "expensive"],
    ),
    "cape_value": SignalSpec(
        type=SignalType.VALUE,
        lookback_period=120,
        formation_period=0,
        holding_period=12,
        cross_sectional=True,
        time_series=False,
        description=(
            "Use cyclically adjusted P/E (CAPE) ratio for country or "
            "market-level value signals."
        ),
        keywords=["CAPE", "Shiller", "P/E", "value", "cyclically adjusted"],
    ),
    "ppp_value": SignalSpec(
        type=SignalType.VALUE,
        lookback_period=0,
        formation_period=0,
        holding_period=3,
        cross_sectional=True,
        time_series=False,
        description="Currency value based on purchasing power parity deviation.",
        keywords=["PPP", "purchasing power parity", "currency", "value", "undervalued"],
    ),

    # --- Carry family ---
    "fx_carry": SignalSpec(
        type=SignalType.CARRY,
        lookback_period=0,
        formation_period=0,
        holding_period=1,
        cross_sectional=True,
        time_series=False,
        description=(
            "Go long high-yield currencies and short low-yield currencies "
            "to capture interest rate differential."
        ),
        keywords=["carry", "yield", "interest rate", "forward", "FX"],
    ),
    "commodity_term_structure": SignalSpec(
        type=SignalType.CARRY,
        lookback_period=0,
        formation_period=0,
        holding_period=1,
        cross_sectional=True,
        time_series=False,
        description=(
            "Exploit roll yield by going long backwardated and short "
            "contango commodity futures."
        ),
        keywords=["carry", "term structure", "backwardation", "contango", "roll yield"],
    ),

    # --- Mean reversion family ---
    "short_term_reversal": SignalSpec(
        type=SignalType.MEAN_REVERSION,
        lookback_period=1,
        formation_period=1,
        holding_period=1,
        cross_sectional=True,
        time_series=False,
        description=(
            "Short-term reversal: buy recent losers and sell recent winners "
            "over weekly horizons."
        ),
        keywords=["reversal", "mean reversion", "contrarian", "short-term", "overreaction"],
    ),
    "pairs_reversion": SignalSpec(
        type=SignalType.MEAN_REVERSION,
        lookback_period=60,
        formation_period=60,
        holding_period=5,
        cross_sectional=False,
        time_series=True,
        description="Mean reversion in spread between cointegrated pairs.",
        keywords=["pairs", "cointegration", "spread", "mean reversion", "rebalancing"],
    ),

    # --- Volatility family ---
    "low_volatility": SignalSpec(
        type=SignalType.VOLATILITY,
        lookback_period=12,
        formation_period=12,
        holding_period=1,
        cross_sectional=True,
        time_series=False,
        description=(
            "Low-volatility anomaly: go long low-vol stocks and short "
            "high-vol stocks."
        ),
        keywords=["volatility", "low vol", "beta", "BAB", "risk", "anomaly"],
    ),
    "volatility_risk_premium": SignalSpec(
        type=SignalType.VOLATILITY,
        lookback_period=1,
        formation_period=1,
        holding_period=1,
        cross_sectional=False,
        time_series=True,
        description=(
            "Sell options or variance swaps to harvest the gap between "
            "implied and realised volatility."
        ),
        keywords=[
            "VRP", "implied", "realised", "variance", "options", "premium",
            "dispersion",
        ],
    ),

    # --- Quality family ---
    "asset_growth": SignalSpec(
        type=SignalType.QUALITY,
        lookback_period=12,
        formation_period=0,
        holding_period=12,
        cross_sectional=True,
        time_series=False,
        description="Firms with low asset growth outperform those with high asset growth.",
        keywords=["asset growth", "quality", "investment", "balance sheet"],
    ),
    "rd_intensity": SignalSpec(
        type=SignalType.QUALITY,
        lookback_period=12,
        formation_period=0,
        holding_period=12,
        cross_sectional=True,
        time_series=False,
        description="R&D-intensive firms earn a premium over low-R&D firms.",
        keywords=["R&D", "research", "development", "innovation", "quality"],
    ),

    # --- Sentiment family ---
    "lexical_density": SignalSpec(
        type=SignalType.SENTIMENT,
        lookback_period=0,
        formation_period=0,
        holding_period=1,
        cross_sectional=True,
        time_series=False,
        description="Use NLP-derived lexical density of company filings as a signal.",
        keywords=["NLP", "text", "lexical", "filings", "10-K", "sentiment", "readability"],
    ),
    "market_sentiment": SignalSpec(
        type=SignalType.SENTIMENT,
        lookback_period=1,
        formation_period=1,
        holding_period=1,
        cross_sectional=False,
        time_series=True,
        description="Use market-wide sentiment indicators to time overnight exposure.",
        keywords=["sentiment", "overnight", "VIX", "put-call", "fear", "greed"],
    ),

    # --- Seasonal family ---
    "january_barometer": SignalSpec(
        type=SignalType.SEASONAL,
        lookback_period=1,
        formation_period=1,
        holding_period=11,
        cross_sectional=False,
        time_series=True,
        description="Use January return as a predictor for full-year market direction.",
        keywords=["January", "barometer", "calendar", "seasonal", "annual"],
    ),
    "turn_of_month": SignalSpec(
        type=SignalType.SEASONAL,
        lookback_period=0,
        formation_period=0,
        holding_period=5,
        cross_sectional=False,
        time_series=True,
        description="Capture systematically higher returns around month-end / month-start.",
        keywords=["turn of month", "calendar", "month-end", "seasonal", "payday"],
    ),
    "options_expiration_week": SignalSpec(
        type=SignalType.SEASONAL,
        lookback_period=0,
        formation_period=0,
        holding_period=5,
        cross_sectional=False,
        time_series=True,
        description="Positive return anomaly during options expiration weeks.",
        keywords=["expiration", "options", "opex", "weekly", "seasonal"],
    ),
    "overnight_seasonality": SignalSpec(
        type=SignalType.SEASONAL,
        lookback_period=0,
        formation_period=0,
        holding_period=1,
        cross_sectional=False,
        time_series=True,
        description="Overnight return seasonality in crypto or equity markets.",
        keywords=["overnight", "intraday", "close-to-open", "seasonality"],
    ),

    # --- Trend following family ---
    "moving_average_trend": SignalSpec(
        type=SignalType.TREND_FOLLOWING,
        lookback_period=10,
        formation_period=10,
        holding_period=1,
        cross_sectional=False,
        time_series=True,
        description=(
            "Simple moving-average crossover: go long when price is above "
            "the moving average, otherwise move to cash."
        ),
        keywords=["trend", "moving average", "SMA", "breakout", "crossover"],
    ),

    # --- Statistical arbitrage family ---
    "pairs_trading": SignalSpec(
        type=SignalType.STATISTICAL_ARBITRAGE,
        lookback_period=252,
        formation_period=252,
        holding_period=20,
        cross_sectional=False,
        time_series=True,
        description=(
            "Identify cointegrated pairs and trade the spread when it "
            "deviates from equilibrium."
        ),
        keywords=["pairs", "cointegration", "spread", "arbitrage", "stat arb"],
    ),
    "spread_trading": SignalSpec(
        type=SignalType.STATISTICAL_ARBITRAGE,
        lookback_period=60,
        formation_period=60,
        holding_period=10,
        cross_sectional=False,
        time_series=True,
        description="Trade price spreads (e.g. WTI/Brent) using mean-reversion.",
        keywords=["spread", "relative value", "arbitrage", "mean reversion"],
    ),
}


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

# Keyword → SignalType mapping (ordered by priority for tie-breaking)
_KEYWORD_MAP: List[tuple] = [
    (SignalType.CARRY, [
        "carry", "roll yield", "interest rate differential", "backwardation",
        "contango", "term structure", "yield curve",
    ]),
    (SignalType.MEAN_REVERSION, [
        "reversal", "mean reversion", "contrarian", "rebalancing premium",
        "overreaction", "pairs reversion",
    ]),
    (SignalType.STATISTICAL_ARBITRAGE, [
        "pairs trading", "cointegration", "spread trading", "stat arb",
        "arbitrage", "relative value",
    ]),
    (SignalType.TREND_FOLLOWING, [
        "trend following", "trend-following", "moving average", "breakout",
        "crossover", "trend filter",
    ]),
    (SignalType.SEASONAL, [
        "seasonal", "january barometer", "turn of month", "calendar",
        "expiration week", "overnight seasonality", "payday", "anomaly",
        "day-of-week",
    ]),
    (SignalType.SENTIMENT, [
        "sentiment", "NLP", "lexical", "text mining", "filings",
        "readability", "news", "put-call ratio",
    ]),
    (SignalType.QUALITY, [
        "quality", "profitability", "asset growth", "accruals",
        "R&D", "earnings quality", "balance sheet",
    ]),
    (SignalType.VOLATILITY, [
        "volatility", "VRP", "low vol", "beta", "variance",
        "dispersion", "implied vol", "realized vol",
    ]),
    (SignalType.VALUE, [
        "value", "book-to-market", "CAPE", "P/E", "PPP",
        "earnings yield", "cheap", "undervalued", "FED model",
    ]),
    (SignalType.MOMENTUM, [
        "momentum", "winner", "loser", "relative strength",
        "12-month", "cross-sectional momentum",
    ]),
]


def classify_signal(text: str) -> List[tuple]:
    """Classify signal type(s) from free-form text (e.g. paper abstract).

    Parameters
    ----------
    text : str
        Free-form text such as a paper title, abstract, or description.

    Returns
    -------
    list[tuple[SignalType, float]]
        Candidate signal types with confidence scores (0-1),
        sorted descending by confidence.
    """
    text_lower = text.lower()
    scores: Dict[SignalType, float] = {}

    for signal_type, keywords in _KEYWORD_MAP:
        hits = 0
        for kw in keywords:
            if kw.lower() in text_lower:
                hits += 1
        if hits > 0:
            confidence = min(1.0, hits / max(2, len(keywords) * 0.4))
            scores[signal_type] = max(scores.get(signal_type, 0.0), confidence)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked


def classify_signal_best(text: str) -> Optional[SignalType]:
    """Return the single most likely signal type for the given text.

    Returns ``None`` if no keywords match.
    """
    ranked = classify_signal(text)
    return ranked[0][0] if ranked else None


def get_signal_spec(name: str) -> Optional[SignalSpec]:
    """Look up a known signal specification by canonical name.

    Parameters
    ----------
    name : str
        Key in :data:`KNOWN_SIGNALS`, e.g. ``"fx_carry"``.

    Returns
    -------
    SignalSpec or None
    """
    return KNOWN_SIGNALS.get(name)


def list_signal_types() -> List[SignalType]:
    """Return all canonical signal types."""
    return list(SignalType)
