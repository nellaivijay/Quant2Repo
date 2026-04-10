"""Strategy catalog module for Quant2Repo.

Loads the strategy catalog from catalog/strategies.json and provides
search, filter, and lookup functions for typed access to strategy metadata.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


@dataclass(frozen=True)
class StrategyEntry:
    """Typed representation of a single strategy from the catalog."""

    id: str
    title: str
    asset_classes: Tuple[str, ...]
    signal_type: str
    sharpe_ratio: float
    volatility: float
    rebalancing: str
    paper_url: Optional[str] = None
    ssrn_id: Optional[str] = None
    authors: Tuple[str, ...] = field(default_factory=tuple)
    year: Optional[int] = None
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyEntry":
        """Create a StrategyEntry from a raw dict (e.g. parsed JSON)."""
        return cls(
            id=d["id"],
            title=d["title"],
            asset_classes=tuple(d.get("asset_classes", [])),
            signal_type=d.get("signal_type", ""),
            sharpe_ratio=float(d.get("sharpe_ratio", 0.0)),
            volatility=float(d.get("volatility", 0.0)),
            rebalancing=d.get("rebalancing", ""),
            paper_url=d.get("paper_url"),
            ssrn_id=d.get("ssrn_id"),
            authors=tuple(d.get("authors", [])),
            year=d.get("year"),
            description=d.get("description", ""),
        )

    def to_dict(self) -> dict:
        """Serialize back to a plain dict."""
        return {
            "id": self.id,
            "title": self.title,
            "asset_classes": list(self.asset_classes),
            "signal_type": self.signal_type,
            "sharpe_ratio": self.sharpe_ratio,
            "volatility": self.volatility,
            "rebalancing": self.rebalancing,
            "paper_url": self.paper_url,
            "ssrn_id": self.ssrn_id,
            "authors": list(self.authors),
            "year": self.year,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Catalog loading
# ---------------------------------------------------------------------------

_CATALOG_PATH: Optional[str] = None
_STRATEGIES: Optional[List[StrategyEntry]] = None
_INDEX: Optional[Dict[str, StrategyEntry]] = None


def _resolve_catalog_path() -> str:
    """Resolve the default path to catalog/strategies.json."""
    # Walk up from this file (quant/catalog.py) to repo root
    here = Path(__file__).resolve().parent
    repo_root = here.parent
    return str(repo_root / "catalog" / "strategies.json")


def _ensure_loaded() -> None:
    """Lazy-load the catalog on first access."""
    global _CATALOG_PATH, _STRATEGIES, _INDEX
    if _STRATEGIES is not None:
        return
    path = _CATALOG_PATH or _resolve_catalog_path()
    load_catalog(path)


def load_catalog(path: Optional[str] = None) -> List[StrategyEntry]:
    """Load (or reload) the strategy catalog from a JSON file.

    Parameters
    ----------
    path : str, optional
        Absolute or relative path to the strategies JSON file.
        Defaults to ``<repo_root>/catalog/strategies.json``.

    Returns
    -------
    list[StrategyEntry]
        All strategies in the catalog.
    """
    global _CATALOG_PATH, _STRATEGIES, _INDEX
    _CATALOG_PATH = path or _resolve_catalog_path()

    with open(_CATALOG_PATH, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    entries = [StrategyEntry.from_dict(s) for s in raw.get("strategies", [])]
    _STRATEGIES = entries
    _INDEX = {e.id: e for e in entries}
    return entries


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def list_strategies() -> List[StrategyEntry]:
    """Return all strategies in the catalog."""
    _ensure_loaded()
    assert _STRATEGIES is not None
    return list(_STRATEGIES)


def get_strategy(strategy_id: str) -> Optional[StrategyEntry]:
    """Look up a single strategy by its slug id.

    Parameters
    ----------
    strategy_id : str
        The unique slug, e.g. ``"time-series-momentum"``.

    Returns
    -------
    StrategyEntry or None
    """
    _ensure_loaded()
    assert _INDEX is not None
    return _INDEX.get(strategy_id)


# ---------------------------------------------------------------------------
# Filter functions
# ---------------------------------------------------------------------------


def by_asset_class(asset_class: str) -> List[StrategyEntry]:
    """Return strategies that include the given asset class.

    Parameters
    ----------
    asset_class : str
        One of: equities, bonds, commodities, currencies, crypto, reits.
    """
    _ensure_loaded()
    assert _STRATEGIES is not None
    ac = asset_class.lower().strip()
    return [s for s in _STRATEGIES if ac in s.asset_classes]


def by_signal_type(signal_type: str) -> List[StrategyEntry]:
    """Return strategies matching the given signal type.

    Parameters
    ----------
    signal_type : str
        One of: momentum, value, carry, mean_reversion, volatility,
        quality, sentiment, seasonal, trend_following, statistical_arbitrage.
    """
    _ensure_loaded()
    assert _STRATEGIES is not None
    st = signal_type.lower().strip()
    return [s for s in _STRATEGIES if s.signal_type == st]


def by_sharpe_range(
    low: float = float("-inf"),
    high: float = float("inf"),
) -> List[StrategyEntry]:
    """Return strategies whose Sharpe ratio falls within [low, high].

    Parameters
    ----------
    low : float
        Minimum Sharpe ratio (inclusive). Defaults to -inf.
    high : float
        Maximum Sharpe ratio (inclusive). Defaults to +inf.
    """
    _ensure_loaded()
    assert _STRATEGIES is not None
    return [s for s in _STRATEGIES if low <= s.sharpe_ratio <= high]


def by_rebalancing(frequency: str) -> List[StrategyEntry]:
    """Return strategies with the given rebalancing frequency.

    Parameters
    ----------
    frequency : str
        One of: daily, weekly, monthly, quarterly, yearly, intraday.
    """
    _ensure_loaded()
    assert _STRATEGIES is not None
    freq = frequency.lower().strip()
    return [s for s in _STRATEGIES if s.rebalancing == freq]


# ---------------------------------------------------------------------------
# Fuzzy search
# ---------------------------------------------------------------------------


def _similarity(a: str, b: str) -> float:
    """Compute similarity ratio between two strings (case-insensitive)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def search(
    query: str,
    *,
    threshold: float = 0.35,
    max_results: int = 10,
) -> List[Tuple[float, StrategyEntry]]:
    """Fuzzy-search strategies by title.

    Parameters
    ----------
    query : str
        Free-text search query.
    threshold : float
        Minimum similarity score (0-1) to include a result.
    max_results : int
        Maximum number of results to return.

    Returns
    -------
    list[tuple[float, StrategyEntry]]
        Results sorted by descending similarity, each item is
        ``(score, strategy)``.
    """
    _ensure_loaded()
    assert _STRATEGIES is not None

    query_lower = query.lower()
    scored: List[Tuple[float, StrategyEntry]] = []

    for s in _STRATEGIES:
        title_lower = s.title.lower()

        # Exact substring match gets a high boost
        if query_lower in title_lower:
            score = 0.9 + 0.1 * _similarity(query_lower, title_lower)
        else:
            # Check individual query words against title words
            query_words = query_lower.split()
            title_words = title_lower.split()
            word_scores = []
            for qw in query_words:
                best = max(
                    (_similarity(qw, tw) for tw in title_words),
                    default=0.0,
                )
                word_scores.append(best)
            score = sum(word_scores) / len(word_scores) if word_scores else 0.0

            # Also factor in whole-string similarity
            whole = _similarity(query_lower, title_lower)
            score = max(score, whole)

            # Bonus for description match
            if query_lower in s.description.lower():
                score = max(score, 0.7)

        if score >= threshold:
            scored.append((round(score, 4), s))

    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[:max_results]


# ---------------------------------------------------------------------------
# Convenience: combined filter
# ---------------------------------------------------------------------------


def filter_strategies(
    *,
    asset_class: Optional[str] = None,
    signal_type: Optional[str] = None,
    rebalancing: Optional[str] = None,
    min_sharpe: Optional[float] = None,
    max_sharpe: Optional[float] = None,
) -> List[StrategyEntry]:
    """Apply multiple filters at once.

    All filters that are not ``None`` are combined with AND logic.
    """
    _ensure_loaded()
    assert _STRATEGIES is not None
    results = list(_STRATEGIES)

    if asset_class is not None:
        ac = asset_class.lower().strip()
        results = [s for s in results if ac in s.asset_classes]

    if signal_type is not None:
        st = signal_type.lower().strip()
        results = [s for s in results if s.signal_type == st]

    if rebalancing is not None:
        freq = rebalancing.lower().strip()
        results = [s for s in results if s.rebalancing == freq]

    if min_sharpe is not None:
        results = [s for s in results if s.sharpe_ratio >= min_sharpe]

    if max_sharpe is not None:
        results = [s for s in results if s.sharpe_ratio <= max_sharpe]

    return results
