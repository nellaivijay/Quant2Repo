"""Data source definitions and recommendation helpers.

Provides a :class:`DataSource` enum, :class:`DataSourceSpec` dataclass,
the pre-built :data:`SOURCES` registry, and a :func:`get_recommended_source`
utility that picks the best data source for a given asset class.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

from quant.asset_classes import AssetClass


# ---------------------------------------------------------------------------
# Data source enum
# ---------------------------------------------------------------------------


class DataSource(str, Enum):
    """Supported data sources for market data retrieval."""

    YFINANCE = "yfinance"
    FRED = "fred"
    QUANDL = "quandl"
    ALPHA_VANTAGE = "alpha_vantage"
    CUSTOM_CSV = "custom_csv"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, s: str) -> "DataSource":
        """Parse a data source from a string (case-insensitive)."""
        normalised = s.strip().lower().replace("-", "_").replace(" ", "_")
        for member in cls:
            if normalised in (member.value, member.name.lower()):
                return member
        raise ValueError(f"Unknown data source: {s!r}")


# ---------------------------------------------------------------------------
# Data source specification
# ---------------------------------------------------------------------------


@dataclass
class DataSourceSpec:
    """Full specification for a data source.

    Attributes
    ----------
    source : DataSource
        Enum member identifying the source.
    asset_classes_supported : list[AssetClass]
        Asset classes this source can provide data for.
    requires_api_key : bool
        Whether an API key / account is required.
    base_url : str
        Primary URL or endpoint for the data source.
    description : str
        Human-readable description of the source.
    rate_limit : str
        Rate-limit information (human-readable).
    python_package : str
        Python package to install (pip name).
    env_var : str
        Name of the environment variable for the API key (if needed).
    """

    source: DataSource
    asset_classes_supported: List[AssetClass] = field(default_factory=list)
    requires_api_key: bool = False
    base_url: str = ""
    description: str = ""
    rate_limit: str = ""
    python_package: str = ""
    env_var: str = ""


# ---------------------------------------------------------------------------
# Pre-built source registry
# ---------------------------------------------------------------------------

SOURCES: Dict[DataSource, DataSourceSpec] = {
    DataSource.YFINANCE: DataSourceSpec(
        source=DataSource.YFINANCE,
        asset_classes_supported=[
            AssetClass.EQUITIES,
            AssetClass.BONDS,
            AssetClass.COMMODITIES,
            AssetClass.CURRENCIES,
            AssetClass.CRYPTO,
            AssetClass.REITS,
            AssetClass.MULTI_ASSET,
        ],
        requires_api_key=False,
        base_url="https://finance.yahoo.com",
        description=(
            "Free, open-source Python library to download historical market "
            "data from Yahoo Finance. Supports equities, ETFs, mutual funds, "
            "options, futures, currencies, and crypto. Best for quick "
            "prototyping and backtesting."
        ),
        rate_limit="Unofficial; ~2000 requests/hour typical",
        python_package="yfinance",
        env_var="",
    ),
    DataSource.FRED: DataSourceSpec(
        source=DataSource.FRED,
        asset_classes_supported=[
            AssetClass.BONDS,
            AssetClass.CURRENCIES,
            AssetClass.MULTI_ASSET,
        ],
        requires_api_key=True,
        base_url="https://fred.stlouisfed.org",
        description=(
            "Federal Reserve Economic Data (FRED) provides free access to "
            "over 800,000 economic time series from 100+ sources. Excellent "
            "for interest rates, Treasury yields, macro indicators, and "
            "FX rates."
        ),
        rate_limit="120 requests/minute with API key",
        python_package="fredapi",
        env_var="FRED_API_KEY",
    ),
    DataSource.QUANDL: DataSourceSpec(
        source=DataSource.QUANDL,
        asset_classes_supported=[
            AssetClass.EQUITIES,
            AssetClass.BONDS,
            AssetClass.COMMODITIES,
            AssetClass.REITS,
            AssetClass.MULTI_ASSET,
        ],
        requires_api_key=True,
        base_url="https://data.nasdaq.com",
        description=(
            "Nasdaq Data Link (formerly Quandl) offers curated financial "
            "and economic datasets. Includes futures continuous contracts, "
            "fundamental data, and alternative data. Some datasets are "
            "premium (paid)."
        ),
        rate_limit="300 requests/10 seconds; 2000/10 min (free tier)",
        python_package="nasdaq-data-link",
        env_var="QUANDL_API_KEY",
    ),
    DataSource.ALPHA_VANTAGE: DataSourceSpec(
        source=DataSource.ALPHA_VANTAGE,
        asset_classes_supported=[
            AssetClass.EQUITIES,
            AssetClass.CURRENCIES,
            AssetClass.CRYPTO,
            AssetClass.MULTI_ASSET,
        ],
        requires_api_key=True,
        base_url="https://www.alphavantage.co",
        description=(
            "Alpha Vantage provides free and premium APIs for real-time and "
            "historical stock, forex, and crypto data, as well as technical "
            "indicators and fundamental data."
        ),
        rate_limit="5 requests/minute; 500/day (free tier)",
        python_package="alpha_vantage",
        env_var="ALPHA_VANTAGE_API_KEY",
    ),
    DataSource.CUSTOM_CSV: DataSourceSpec(
        source=DataSource.CUSTOM_CSV,
        asset_classes_supported=[
            AssetClass.EQUITIES,
            AssetClass.BONDS,
            AssetClass.COMMODITIES,
            AssetClass.CURRENCIES,
            AssetClass.CRYPTO,
            AssetClass.REITS,
            AssetClass.MULTI_ASSET,
        ],
        requires_api_key=False,
        base_url="",
        description=(
            "User-provided CSV files for custom or proprietary datasets. "
            "Expected format: date column + OHLCV columns. Useful when "
            "data is not available from standard providers or for "
            "proprietary/cleaned datasets."
        ),
        rate_limit="N/A (local files)",
        python_package="pandas",
        env_var="",
    ),
}


# ---------------------------------------------------------------------------
# Recommendation logic
# ---------------------------------------------------------------------------

# Priority order per asset class (first = most recommended)
_RECOMMENDATIONS: Dict[AssetClass, List[DataSource]] = {
    AssetClass.EQUITIES: [
        DataSource.YFINANCE,
        DataSource.ALPHA_VANTAGE,
        DataSource.QUANDL,
        DataSource.CUSTOM_CSV,
    ],
    AssetClass.BONDS: [
        DataSource.FRED,
        DataSource.YFINANCE,
        DataSource.QUANDL,
        DataSource.CUSTOM_CSV,
    ],
    AssetClass.COMMODITIES: [
        DataSource.YFINANCE,
        DataSource.QUANDL,
        DataSource.CUSTOM_CSV,
    ],
    AssetClass.CURRENCIES: [
        DataSource.YFINANCE,
        DataSource.FRED,
        DataSource.ALPHA_VANTAGE,
        DataSource.CUSTOM_CSV,
    ],
    AssetClass.CRYPTO: [
        DataSource.YFINANCE,
        DataSource.ALPHA_VANTAGE,
        DataSource.CUSTOM_CSV,
    ],
    AssetClass.REITS: [
        DataSource.YFINANCE,
        DataSource.QUANDL,
        DataSource.CUSTOM_CSV,
    ],
    AssetClass.MULTI_ASSET: [
        DataSource.YFINANCE,
        DataSource.FRED,
        DataSource.QUANDL,
        DataSource.ALPHA_VANTAGE,
        DataSource.CUSTOM_CSV,
    ],
}


def get_recommended_source(
    asset_class: AssetClass | str,
    *,
    allow_api_key: bool = True,
) -> Optional[DataSource]:
    """Return the most recommended data source for an asset class.

    Parameters
    ----------
    asset_class : AssetClass or str
        The asset class to get a recommendation for.
    allow_api_key : bool
        If ``False``, skip sources that require an API key and return the
        first free option.

    Returns
    -------
    DataSource or None
        The best data source, or ``None`` if no match is found.
    """
    if isinstance(asset_class, str):
        try:
            asset_class = AssetClass.from_string(asset_class)
        except ValueError:
            return None

    candidates = _RECOMMENDATIONS.get(asset_class, [])
    for src in candidates:
        spec = SOURCES.get(src)
        if spec is None:
            continue
        if not allow_api_key and spec.requires_api_key:
            continue
        return src
    return None


def get_all_recommendations(
    asset_class: AssetClass | str,
) -> List[DataSource]:
    """Return all recommended data sources for an asset class, in priority order."""
    if isinstance(asset_class, str):
        try:
            asset_class = AssetClass.from_string(asset_class)
        except ValueError:
            return []
    return list(_RECOMMENDATIONS.get(asset_class, []))


def get_source_spec(source: DataSource | str) -> Optional[DataSourceSpec]:
    """Look up a data source specification."""
    if isinstance(source, str):
        try:
            source = DataSource.from_string(source)
        except ValueError:
            return None
    return SOURCES.get(source)


def list_sources() -> List[DataSource]:
    """Return all supported data sources."""
    return list(DataSource)
