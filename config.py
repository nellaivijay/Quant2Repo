"""Global configuration for Quant2Repo."""

from dataclasses import dataclass, field
from typing import Optional
import os


@dataclass
class Q2RConfig:
    """Central configuration for the Quant2Repo pipeline."""

    # Provider defaults
    default_provider: str = "auto"
    default_model: str = ""

    # Pipeline toggles
    enable_validation: bool = True
    enable_test_generation: bool = True
    enable_backtest_validation: bool = True
    enable_caching: bool = True
    max_fix_iterations: int = 2

    # Download settings
    pdf_timeout: int = 120
    pdf_max_size_mb: int = 100

    # Generation settings
    code_temperature: float = 0.15
    analysis_temperature: float = 0.1
    max_code_tokens: int = 16384
    max_analysis_tokens: int = 8192

    # Vision settings
    max_diagram_pages: int = 30
    diagram_dpi: int = 150
    vision_batch_size: int = 4

    # CodeRAG settings
    enable_code_rag: bool = False
    code_rag_max_repos: int = 3
    code_rag_max_files: int = 20

    # Document segmentation
    enable_segmentation: bool = True
    segmentation_max_chars: int = 12000
    segmentation_overlap: int = 500

    # Context management
    enable_context_manager: bool = True
    context_max_chars: int = 80000
    context_use_llm_summaries: bool = True

    # Backtest-specific settings
    default_start_date: str = "2000-01-01"
    default_end_date: str = "2023-12-31"
    default_initial_capital: float = 1_000_000.0
    default_transaction_cost_bps: float = 10.0
    default_data_source: str = "yfinance"
    backtest_metrics: list = field(default_factory=lambda: [
        "annual_return", "annual_volatility", "sharpe_ratio",
        "max_drawdown", "calmar_ratio", "sortino_ratio",
        "turnover", "hit_rate", "profit_factor",
        "var_95", "cvar_95", "information_ratio",
    ])

    # Cache settings
    cache_dir: str = ".q2r_cache"

    # Output settings
    verbose: bool = False

    @classmethod
    def from_env(cls) -> "Q2RConfig":
        """Create config from environment variables."""
        config = cls()
        if os.environ.get("Q2R_PROVIDER"):
            config.default_provider = os.environ["Q2R_PROVIDER"]
        if os.environ.get("Q2R_MODEL"):
            config.default_model = os.environ["Q2R_MODEL"]
        if os.environ.get("Q2R_CACHE_DIR"):
            config.cache_dir = os.environ["Q2R_CACHE_DIR"]
        if os.environ.get("Q2R_VERBOSE"):
            config.verbose = os.environ["Q2R_VERBOSE"].lower() in ("1", "true", "yes")
        if os.environ.get("Q2R_DATA_SOURCE"):
            config.default_data_source = os.environ["Q2R_DATA_SOURCE"]
        return config


# Signal type constants
SIGNAL_MOMENTUM = "momentum"
SIGNAL_VALUE = "value"
SIGNAL_CARRY = "carry"
SIGNAL_MEAN_REVERSION = "mean_reversion"
SIGNAL_VOLATILITY = "volatility"
SIGNAL_QUALITY = "quality"
SIGNAL_SENTIMENT = "sentiment"
SIGNAL_SEASONAL = "seasonal"
SIGNAL_TREND = "trend_following"
SIGNAL_STATISTICAL_ARBITRAGE = "statistical_arbitrage"

SIGNAL_TYPES = [
    SIGNAL_MOMENTUM, SIGNAL_VALUE, SIGNAL_CARRY, SIGNAL_MEAN_REVERSION,
    SIGNAL_VOLATILITY, SIGNAL_QUALITY, SIGNAL_SENTIMENT, SIGNAL_SEASONAL,
    SIGNAL_TREND, SIGNAL_STATISTICAL_ARBITRAGE,
]

# Asset class constants
ASSET_EQUITIES = "equities"
ASSET_BONDS = "bonds"
ASSET_COMMODITIES = "commodities"
ASSET_CURRENCIES = "currencies"
ASSET_CRYPTO = "crypto"
ASSET_REITS = "reits"
ASSET_MULTI = "multi_asset"

ASSET_CLASSES = [
    ASSET_EQUITIES, ASSET_BONDS, ASSET_COMMODITIES,
    ASSET_CURRENCIES, ASSET_CRYPTO, ASSET_REITS, ASSET_MULTI,
]

# Rebalancing frequency constants
REBAL_DAILY = "daily"
REBAL_WEEKLY = "weekly"
REBAL_MONTHLY = "monthly"
REBAL_QUARTERLY = "quarterly"
REBAL_SEMI_ANNUAL = "semi_annual"
REBAL_ANNUAL = "annual"
REBAL_INTRADAY = "intraday"
