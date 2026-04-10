"""Base agent class and message passing for Quant2Repo."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class AgentMessage:
    """Message passed between agents."""
    role: str = ""
    content: str = ""
    metadata: dict = field(default_factory=dict)

    def __str__(self):
        return f"[{self.role}] {self.content[:100]}..."


class BaseAgent(ABC):
    """Abstract base class for all pipeline agents."""

    def __init__(self, provider=None, config: dict = None):
        self._provider = provider
        self._config = config or {}
        self._messages: list = []

    @property
    def name(self) -> str:
        """Agent name (defaults to class name)."""
        return self.__class__.__name__

    @property
    def provider(self):
        """LLM provider."""
        return self._provider

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Execute agent's task. Subclasses must override."""
        raise NotImplementedError

    def log(self, message: str):
        """Log with agent prefix."""
        logger.info(f"[{self.name}] {message}")
        print(f"  [{self.name}] {message}")

    def communicate(self, target_agent: "BaseAgent", message: AgentMessage):
        """Send a synchronous message to another agent."""
        target_agent.receive(message)
        return True

    def receive(self, message: AgentMessage):
        """Receive a message from another agent."""
        self._messages.append(message)

    def get_messages(self, role: Optional[str] = None) -> list:
        """Get received messages, optionally filtered by role."""
        if role:
            return [m for m in self._messages if m.role == role]
        return list(self._messages)


class PaperAnalysisAgent(BaseAgent):
    """Agent that wraps the paper parser + strategy extractor."""

    def execute(self, pdf_path: str = "", paper_text: str = "", **kwargs):
        from core.paper_parser import PaperParser
        from core.strategy_extractor import StrategyExtractor

        self.log("Parsing paper")
        parser = PaperParser()

        if pdf_path:
            parsed = parser.parse(pdf_path)
            paper_text = parsed.get_text_for_analysis()
        elif not paper_text:
            raise ValueError("Either pdf_path or paper_text required")

        self.log("Extracting strategy")
        extractor = StrategyExtractor(self.provider)
        extraction = extractor.extract(paper_text)

        return {"paper_text": paper_text, "extraction": extraction}


class PlanningAgent(BaseAgent):
    """Agent that wraps the decomposed planner."""

    def execute(self, paper_text: str = "", strategy_extraction: dict = None,
                refiner=None, **kwargs):
        from core.planner import DecomposedPlanner

        self.log("Running decomposed planning")
        planner = DecomposedPlanner(self.provider)
        result = planner.plan(paper_text, strategy_extraction or {}, refiner=refiner)

        return {"planning_result": result}


class FileAnalysisAgent(BaseAgent):
    """Agent that wraps per-file analysis."""

    def execute(self, architecture_plan=None, paper_text: str = "",
                strategy_extraction: dict = None, **kwargs):
        from core.file_analyzer import FileAnalyzer

        self.log("Analyzing files")
        analyzer = FileAnalyzer(self.provider)
        analyses = analyzer.analyze_all(architecture_plan, paper_text,
                                        strategy_extraction or {})

        return {"file_analyses": analyses}


class CodeGenerationAgent(BaseAgent):
    """Agent that wraps code synthesis."""

    def execute(self, architecture_plan=None, paper_text: str = "",
                strategy_extraction: dict = None, file_analyses: dict = None,
                context_manager=None, **kwargs):
        from core.coder import CodeSynthesizer

        self.log("Generating code")
        coder = CodeSynthesizer(self.provider)
        files = coder.generate_codebase(
            architecture_plan, paper_text,
            strategy_extraction or {},
            file_analyses=file_analyses,
            context_manager=context_manager,
        )

        return {"generated_files": files}


class ValidationAgent(BaseAgent):
    """Agent that wraps code validation."""

    def execute(self, generated_files: dict = None, paper_text: str = "",
                strategy_extraction: dict = None, **kwargs):
        from core.validator import CodeValidator

        self.log("Validating code")
        validator = CodeValidator(self.provider)
        report = validator.validate(generated_files or {}, paper_text,
                                    strategy_extraction or {})

        if not report.passed:
            self.log(f"Validation failed (score={report.score}), attempting fixes")
            fixed = validator.fix_issues(generated_files, report, paper_text)
            report2 = validator.validate(fixed, paper_text, strategy_extraction or {})
            return {"validation_report": report2, "generated_files": fixed}

        return {"validation_report": report, "generated_files": generated_files}
