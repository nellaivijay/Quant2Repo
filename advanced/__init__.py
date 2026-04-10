"""Advanced capabilities for Quant2Repo."""

from .backtest_validator import BacktestValidator, BacktestValidationReport
from .cache import PipelineCache
from .executor import ExecutionSandbox, ExecutionResult
from .debugger import AutoDebugger, DebugReport
from .evaluator import ReferenceEvaluator, EvaluationScore
from .devops import DevOpsGenerator
from .test_generator import TestGenerator
from .code_rag import CodeRAG, CodeRAGIndex
from .context_manager import ContextManager, GenerationContext

__all__ = [
    "BacktestValidator", "BacktestValidationReport",
    "PipelineCache",
    "ExecutionSandbox", "ExecutionResult",
    "AutoDebugger", "DebugReport",
    "ReferenceEvaluator", "EvaluationScore",
    "DevOpsGenerator",
    "TestGenerator",
    "CodeRAG", "CodeRAGIndex",
    "ContextManager", "GenerationContext",
]
