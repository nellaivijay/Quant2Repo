"""Asset class definitions and default instrument universes.

Provides an :class:`AssetClass` enum, an :class:`AssetUniverse` dataclass
describing typical instruments per asset class, and the pre-built
:data:`UNIVERSES` dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Asset class enum
# ---------------------------------------------------------------------------


class AssetClass(str, Enum):
    """Supported asset classes in the strategy catalog."""

    EQUITIES = "equities"
    BONDS = "bonds"
    COMMODITIES = "commodities"
    CURRENCIES = "currencies"
    CRYPTO = "crypto"
    REITS = "reits"
    MULTI_ASSET = "multi_asset"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, s: str) -> "AssetClass":
        """Parse an asset class from a string (case-insensitive)."""
        normalised = s.strip().lower().replace("-", "_").replace(" ", "_")
        for member in cls:
            if normalised in (member.value, member.name.lower()):
                return member
        raise ValueError(f"Unknown asset class: {s!r}")


# ---------------------------------------------------------------------------
# Asset universe dataclass
# ---------------------------------------------------------------------------


@dataclass
class AssetUniverse:
    """Default universe configuration for an asset class.

    Attributes
    ----------
    asset_class : AssetClass
        The asset class this universe represents.
    typical_instruments : list[str]
        Broad instrument types (e.g. "individual stocks", "ETFs").
    data_sources : list[str]
        Recommended data sources for this asset class.
    typical_tickers : list[str]
        Default ticker symbols commonly used in backtests.
    description : str
        Brief description of the universe.
    exchanges : list[str]
        Relevant exchanges or markets.
    """

    asset_class: AssetClass
    typical_instruments: List[str] = field(default_factory=list)
    data_sources: List[str] = field(default_factory=list)
    typical_tickers: List[str] = field(default_factory=list)
    description: str = ""
    exchanges: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pre-built universes
# ---------------------------------------------------------------------------

UNIVERSES: Dict[AssetClass, AssetUniverse] = {
    AssetClass.EQUITIES: AssetUniverse(
        asset_class=AssetClass.EQUITIES,
        typical_instruments=[
            "individual stocks",
            "equity ETFs",
            "equity index futures",
            "equity options",
        ],
        data_sources=["yfinance", "alpha_vantage", "quandl", "custom_csv"],
        typical_tickers=[
            "SPY",   # S&P 500 ETF
            "QQQ",   # Nasdaq 100 ETF
            "IWM",   # Russell 2000 ETF
            "DIA",   # Dow Jones ETF
            "VTI",   # Total US Stock Market
            "EFA",   # MSCI EAFE (International Developed)
            "EEM",   # MSCI Emerging Markets
            "XLF",   # Financials Sector SPDR
            "XLK",   # Technology Sector SPDR
            "XLE",   # Energy Sector SPDR
            "XLV",   # Health Care Sector SPDR
            "XLI",   # Industrials Sector SPDR
            "XLP",   # Consumer Staples Sector SPDR
            "XLY",   # Consumer Discretionary Sector SPDR
            "XLU",   # Utilities Sector SPDR
            "XLB",   # Materials Sector SPDR
        ],
        description=(
            "Equity markets including individual stocks, broad market ETFs, "
            "sector ETFs, and equity index futures."
        ),
        exchanges=["NYSE", "NASDAQ", "LSE", "TSE", "HKEX"],
    ),
    AssetClass.BONDS: AssetUniverse(
        asset_class=AssetClass.BONDS,
        typical_instruments=[
            "government bond ETFs",
            "corporate bond ETFs",
            "Treasury futures",
            "TIPS ETFs",
        ],
        data_sources=["yfinance", "fred", "quandl"],
        typical_tickers=[
            "TLT",   # 20+ Year Treasury Bond ETF
            "IEF",   # 7-10 Year Treasury Bond ETF
            "SHY",   # 1-3 Year Treasury Bond ETF
            "AGG",   # US Aggregate Bond ETF
            "BND",   # Total Bond Market ETF
            "LQD",   # Investment Grade Corporate Bond ETF
            "HYG",   # High Yield Corporate Bond ETF
            "TIP",   # TIPS Bond ETF
            "EMB",   # Emerging Markets Bond ETF
            "MUB",   # Municipal Bond ETF
        ],
        description=(
            "Fixed income markets including Treasuries, corporates, TIPS, "
            "municipals, and emerging market sovereign debt."
        ),
        exchanges=["CBOT", "CME", "ICE"],
    ),
    AssetClass.COMMODITIES: AssetUniverse(
        asset_class=AssetClass.COMMODITIES,
        typical_instruments=[
            "commodity futures",
            "commodity ETFs",
            "commodity ETNs",
        ],
        data_sources=["yfinance", "quandl", "fred", "custom_csv"],
        typical_tickers=[
            "GLD",   # Gold ETF
            "SLV",   # Silver ETF
            "USO",   # United States Oil Fund
            "UNG",   # United States Natural Gas Fund
            "DBA",   # Agriculture ETF
            "DBC",   # Commodity Index Tracking Fund
            "PDBC",  # Optimum Yield Diversified Commodity
            "PPLT",  # Platinum ETF
            "PALL",  # Palladium ETF
            "WEAT",  # Wheat ETF
            "CORN",  # Corn ETF
            "SOYB",  # Soybean ETF
        ],
        description=(
            "Commodity markets including energy (oil, gas), precious metals "
            "(gold, silver), base metals, and agricultural commodities."
        ),
        exchanges=["CME", "NYMEX", "COMEX", "CBOT", "ICE", "LME"],
    ),
    AssetClass.CURRENCIES: AssetUniverse(
        asset_class=AssetClass.CURRENCIES,
        typical_instruments=[
            "spot FX",
            "FX futures",
            "currency ETFs",
        ],
        data_sources=["yfinance", "alpha_vantage", "fred", "custom_csv"],
        typical_tickers=[
            "EURUSD=X",   # Euro / US Dollar
            "GBPUSD=X",   # British Pound / US Dollar
            "USDJPY=X",   # US Dollar / Japanese Yen
            "USDCHF=X",   # US Dollar / Swiss Franc
            "AUDUSD=X",   # Australian Dollar / US Dollar
            "NZDUSD=X",   # New Zealand Dollar / US Dollar
            "USDCAD=X",   # US Dollar / Canadian Dollar
            "EURGBP=X",   # Euro / British Pound
            "EURJPY=X",   # Euro / Japanese Yen
            "FXE",        # Euro Currency Trust ETF
            "FXB",        # British Pound Sterling ETF
            "FXY",        # Japanese Yen ETF
            "FXA",        # Australian Dollar ETF
            "FXC",        # Canadian Dollar ETF
            "UUP",        # US Dollar Bullish ETF
        ],
        description=(
            "Foreign exchange markets including G10 and major emerging market "
            "currency pairs, as well as currency ETFs."
        ),
        exchanges=["FOREX", "CME"],
    ),
    AssetClass.CRYPTO: AssetUniverse(
        asset_class=AssetClass.CRYPTO,
        typical_instruments=[
            "spot crypto",
            "crypto futures",
            "crypto ETFs",
        ],
        data_sources=["yfinance", "custom_csv"],
        typical_tickers=[
            "BTC-USD",   # Bitcoin
            "ETH-USD",   # Ethereum
            "BNB-USD",   # Binance Coin
            "SOL-USD",   # Solana
            "ADA-USD",   # Cardano
            "XRP-USD",   # Ripple
            "DOT-USD",   # Polkadot
            "AVAX-USD",  # Avalanche
            "MATIC-USD", # Polygon
            "LINK-USD",  # Chainlink
        ],
        description=(
            "Cryptocurrency markets including major coins and altcoins, "
            "traded on centralised and decentralised exchanges."
        ),
        exchanges=["Binance", "Coinbase", "Kraken", "CME"],
    ),
    AssetClass.REITS: AssetUniverse(
        asset_class=AssetClass.REITS,
        typical_instruments=[
            "REIT ETFs",
            "individual REITs",
        ],
        data_sources=["yfinance", "quandl"],
        typical_tickers=[
            "VNQ",   # Vanguard Real Estate ETF
            "IYR",   # iShares US Real Estate ETF
            "SCHH",  # Schwab US REIT ETF
            "RWR",   # SPDR Dow Jones REIT ETF
            "XLRE",  # Real Estate Select Sector SPDR
            "REM",   # iShares Mortgage Real Estate ETF
            "VNQI",  # Vanguard Global ex-US Real Estate ETF
        ],
        description=(
            "Real estate investment trusts (REITs) providing exposure to "
            "commercial, residential, and specialty real estate sectors."
        ),
        exchanges=["NYSE", "NASDAQ"],
    ),
    AssetClass.MULTI_ASSET: AssetUniverse(
        asset_class=AssetClass.MULTI_ASSET,
        typical_instruments=[
            "ETFs across asset classes",
            "futures across asset classes",
        ],
        data_sources=["yfinance", "fred", "quandl", "alpha_vantage"],
        typical_tickers=[
            "SPY",   # Equities
            "TLT",   # Bonds
            "GLD",   # Commodities
            "VNQ",   # REITs
            "UUP",   # Currencies (USD)
            "BTC-USD",  # Crypto
        ],
        description=(
            "Multi-asset portfolios spanning equities, bonds, commodities, "
            "REITs, currencies, and crypto for diversified strategy execution."
        ),
        exchanges=["NYSE", "NASDAQ", "CME", "CBOT"],
    ),
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def get_universe(asset_class: AssetClass | str) -> Optional[AssetUniverse]:
    """Return the default universe for an asset class.

    Parameters
    ----------
    asset_class : AssetClass or str
        The asset class to look up.

    Returns
    -------
    AssetUniverse or None
    """
    if isinstance(asset_class, str):
        try:
            asset_class = AssetClass.from_string(asset_class)
        except ValueError:
            return None
    return UNIVERSES.get(asset_class)


def get_tickers(asset_class: AssetClass | str) -> List[str]:
    """Shortcut: return typical tickers for the given asset class."""
    universe = get_universe(asset_class)
    return list(universe.typical_tickers) if universe else []


def list_asset_classes() -> List[AssetClass]:
    """Return all defined asset classes."""
    return list(AssetClass)
