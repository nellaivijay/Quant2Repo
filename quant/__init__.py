"""Quant domain modules for Quant2Repo.

This package exposes the core quant building blocks:

* **catalog** -- Strategy catalog (load, search, filter 47 strategies)
* **signals** -- Signal type taxonomy and specifications
* **asset_classes** -- Asset class enum and default universes
* **metrics** -- Performance metric definitions and validation
* **data_sources** -- Data source registry and recommendation
"""

# --- catalog ---
from quant.catalog import (
    StrategyEntry,
    load_catalog,
    list_strategies,
    get_strategy,
    by_asset_class,
    by_signal_type,
    by_sharpe_range,
    by_rebalancing,
    search,
    filter_strategies,
)

# --- signals ---
from quant.signals import (
    SignalType,
    SignalSpec,
    KNOWN_SIGNALS,
    classify_signal,
    classify_signal_best,
    get_signal_spec,
    list_signal_types,
)

# --- asset_classes ---
from quant.asset_classes import (
    AssetClass,
    AssetUniverse,
    UNIVERSES,
    get_universe,
    get_tickers,
    list_asset_classes,
)

# --- metrics ---
from quant.metrics import (
    MetricSpec,
    MetricValidationResult,
    ValidationReport,
    ALL_METRICS,
    get_metric,
    list_metrics,
    compare,
    # Individual metric constants
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
)

# --- data_sources ---
from quant.data_sources import (
    DataSource,
    DataSourceSpec,
    SOURCES,
    get_recommended_source,
    get_all_recommendations,
    get_source_spec,
    list_sources,
)

__all__ = [
    # catalog
    "StrategyEntry",
    "load_catalog",
    "list_strategies",
    "get_strategy",
    "by_asset_class",
    "by_signal_type",
    "by_sharpe_range",
    "by_rebalancing",
    "search",
    "filter_strategies",
    # signals
    "SignalType",
    "SignalSpec",
    "KNOWN_SIGNALS",
    "classify_signal",
    "classify_signal_best",
    "get_signal_spec",
    "list_signal_types",
    # asset_classes
    "AssetClass",
    "AssetUniverse",
    "UNIVERSES",
    "get_universe",
    "get_tickers",
    "list_asset_classes",
    # metrics
    "MetricSpec",
    "MetricValidationResult",
    "ValidationReport",
    "ALL_METRICS",
    "get_metric",
    "list_metrics",
    "compare",
    "ANNUAL_RETURN",
    "ANNUAL_VOLATILITY",
    "SHARPE_RATIO",
    "SORTINO_RATIO",
    "MAX_DRAWDOWN",
    "CALMAR_RATIO",
    "INFORMATION_RATIO",
    "HIT_RATE",
    "PROFIT_FACTOR",
    "VAR_95",
    "CVAR_95",
    "TURNOVER",
    "TRACKING_ERROR",
    "BETA",
    "ALPHA",
    "T_STATISTIC",
    # data_sources
    "DataSource",
    "DataSourceSpec",
    "SOURCES",
    "get_recommended_source",
    "get_all_recommendations",
    "get_source_spec",
    "list_sources",
]
