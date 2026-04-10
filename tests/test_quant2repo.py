"""Tests for the Quant2Repo strategy catalog."""

import json
import os
import pytest
from pathlib import Path


CATALOG_PATH = Path(__file__).parent.parent / "catalog" / "strategies.json"


class TestCatalogData:
    """Test the raw strategies.json data."""

    @pytest.fixture
    def strategies(self):
        with open(CATALOG_PATH) as f:
            data = json.load(f)
        return data["strategies"]

    def test_catalog_file_exists(self):
        assert CATALOG_PATH.exists(), "catalog/strategies.json must exist"

    def test_has_strategies(self, strategies):
        assert len(strategies) >= 40, f"Expected 40+ strategies, got {len(strategies)}"

    def test_strategy_required_fields(self, strategies):
        required = ["id", "title", "asset_classes", "signal_type", "rebalancing"]
        for s in strategies:
            for field in required:
                assert field in s, f"Strategy {s.get('id', '?')} missing {field}"

    def test_unique_ids(self, strategies):
        ids = [s["id"] for s in strategies]
        assert len(ids) == len(set(ids)), "Strategy IDs must be unique"

    def test_valid_signal_types(self, strategies):
        valid = {
            "momentum", "value", "carry", "mean_reversion", "volatility",
            "quality", "sentiment", "seasonal", "trend_following",
            "statistical_arbitrage",
        }
        for s in strategies:
            assert s["signal_type"] in valid, (
                f"Strategy {s['id']} has invalid signal_type: {s['signal_type']}"
            )

    def test_valid_rebalancing(self, strategies):
        valid = {"daily", "weekly", "monthly", "quarterly", "semi_annual",
                 "annual", "intraday", "yearly", "6_months"}
        for s in strategies:
            assert s["rebalancing"] in valid, (
                f"Strategy {s['id']} has invalid rebalancing: {s['rebalancing']}"
            )

    def test_sharpe_ratios_reasonable(self, strategies):
        for s in strategies:
            sr = s.get("sharpe_ratio")
            if sr is not None:
                assert -2 < sr < 3, (
                    f"Strategy {s['id']} has unreasonable Sharpe: {sr}"
                )

    def test_asset_classes_are_lists(self, strategies):
        for s in strategies:
            assert isinstance(s["asset_classes"], list), (
                f"Strategy {s['id']} asset_classes must be a list"
            )
            assert len(s["asset_classes"]) > 0


class TestCatalogModule:
    """Test the quant.catalog module."""

    def test_import(self):
        from quant.catalog import load_catalog, list_strategies, get_strategy
        strategies = load_catalog()
        assert strategies is not None

    def test_list_strategies(self):
        from quant.catalog import list_strategies
        strategies = list_strategies()
        assert len(strategies) >= 40

    def test_get_strategy(self):
        from quant.catalog import get_strategy
        s = get_strategy("time-series-momentum")
        if s:
            assert s.title == "Time Series Momentum Effect"
            assert s.sharpe_ratio is not None

    def test_by_asset_class(self):
        from quant.catalog import by_asset_class
        equities = by_asset_class("equities")
        assert len(equities) > 20

    def test_by_signal_type(self):
        from quant.catalog import by_signal_type
        momentum = by_signal_type("momentum")
        assert len(momentum) >= 5

    def test_search(self):
        from quant.catalog import search
        results = search("momentum")
        assert len(results) > 0
        assert any("momentum" in s.title.lower() for _, s in results)

    def test_by_sharpe_range(self):
        from quant.catalog import by_sharpe_range
        high_sr = by_sharpe_range(low=0.5)
        assert all(s.sharpe_ratio >= 0.5 for s in high_sr)


class TestQuantModules:
    """Test quant domain modules."""

    def test_signals_import(self):
        from quant.signals import SignalType, KNOWN_SIGNALS
        assert len(SignalType) >= 10
        assert len(KNOWN_SIGNALS) > 0

    def test_asset_classes_import(self):
        from quant.asset_classes import AssetClass, UNIVERSES
        assert len(AssetClass) >= 6
        assert "equities" in UNIVERSES or AssetClass.EQUITIES in UNIVERSES

    def test_metrics_import(self):
        from quant.metrics import ALL_METRICS
        assert "sharpe_ratio" in ALL_METRICS
        assert "max_drawdown" in ALL_METRICS
        assert len(ALL_METRICS) >= 12

    def test_data_sources_import(self):
        from quant.data_sources import DataSource, SOURCES
        assert len(DataSource) >= 4
        assert len(SOURCES) >= 4


class TestConfig:
    """Test configuration module."""

    def test_config_defaults(self):
        from config import Q2RConfig
        config = Q2RConfig()
        assert config.default_provider == "auto"
        assert config.code_temperature == 0.15
        assert config.default_data_source == "yfinance"
        assert len(config.backtest_metrics) >= 10

    def test_config_from_env(self):
        from config import Q2RConfig
        os.environ["Q2R_VERBOSE"] = "true"
        config = Q2RConfig.from_env()
        assert config.verbose is True
        del os.environ["Q2R_VERBOSE"]

    def test_signal_constants(self):
        from config import SIGNAL_TYPES, ASSET_CLASSES
        assert "momentum" in SIGNAL_TYPES
        assert "equities" in ASSET_CLASSES


class TestProviders:
    """Test provider abstraction layer."""

    def test_base_provider_import(self):
        from providers.base import BaseProvider, ModelCapability, GenerationConfig
        assert ModelCapability.LONG_CONTEXT is not None
        config = GenerationConfig()
        assert config.temperature == 0.7

    def test_registry_import(self):
        from providers.registry import ProviderRegistry
        registry = ProviderRegistry()
        providers = registry.list_providers()
        assert "gemini" in providers
        assert "openai" in providers
        assert "anthropic" in providers
        assert "ollama" in providers

    def test_registry_detect(self):
        from providers.registry import ProviderRegistry
        registry = ProviderRegistry()
        # Should not crash even with no providers configured
        available = registry.detect_available()
        assert isinstance(available, list)


class TestCorePipeline:
    """Test core pipeline module imports."""

    def test_paper_parser_import(self):
        from core.paper_parser import PaperParser, ParsedPaper
        parser = PaperParser()
        assert parser is not None

    def test_strategy_extractor_import(self):
        from core.strategy_extractor import StrategyExtractor, StrategyExtraction
        extraction = StrategyExtraction()
        assert extraction.strategy_name == ""

    def test_planner_import(self):
        from core.planner import DecomposedPlanner, PlanningResult
        result = PlanningResult()
        assert result.combined_plan is None

    def test_validator_import(self):
        from core.validator import CodeValidator, ValidationReport
        report = ValidationReport()
        assert report.score == 100
        assert report.passed is True

    def test_refiner_import(self):
        from core.refiner import SelfRefiner, RefinementResult
        result = RefinementResult()
        assert result.improved is False


class TestAgents:
    """Test agent layer imports."""

    def test_base_agent_import(self):
        from agents.base import BaseAgent, AgentMessage
        msg = AgentMessage(role="test", content="hello")
        assert str(msg).startswith("[test]")

    def test_orchestrator_import(self):
        from agents.orchestrator import AgentOrchestrator, PipelineResult
        result = PipelineResult()
        assert isinstance(result.files, dict)


class TestMainCLI:
    """Test main.py CLI entry point."""

    def test_main_import(self):
        import main
        assert hasattr(main, "main")
        assert hasattr(main, "run_classic")
        assert hasattr(main, "run_agent")
        assert hasattr(main, "list_catalog")
        assert hasattr(main, "search_catalog")
