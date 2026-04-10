"""Clean-slate context management for file-by-file code generation.

Prevents context-window pollution by rebuilding the prompt from scratch
before each file.  After every generated file is recorded, a compact
LLM-produced summary is created so subsequent files receive only:

1. The architecture plan (compressed).
2. A cumulative code summary (one paragraph per prior file).
3. Full source of direct dependencies.
4. Optional reference code (from CodeRAG).

This approach yields higher quality than simply concatenating all
previously generated code into the prompt.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────

@dataclass
class FileSummary:
    """Compact summary of a single generated file.

    Attributes:
        path: Relative file path.
        summary: Short natural-language summary of the file's purpose and
            key classes/functions/APIs.
        exports: Public names exported by the file (class/function names).
        imports: Modules this file imports from other generated files.
        char_count: Length of the full source (for budget estimation).
    """

    path: str = ""
    summary: str = ""
    exports: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    char_count: int = 0


@dataclass
class GenerationContext:
    """Assembled context for generating a single file.

    The :meth:`full_prompt` method concatenates the sections in the
    correct order and trims to fit within the token budget.

    Attributes:
        target_path: Path of the file about to be generated.
        target_description: One-line description of the file's purpose.
        architecture_summary: Compressed plan / file list.
        cumulative_summary: Paragraph-per-file summaries of everything
            generated so far.
        dependency_code: Full source of direct dependency files.
        reference_code: Relevant reference snippets (CodeRAG).
        strategy_context: Key strategy details from the paper.
        generation_instructions: Instructions specific to this file.
        max_chars: Hard character limit for the assembled prompt.
    """

    target_path: str = ""
    target_description: str = ""
    architecture_summary: str = ""
    cumulative_summary: str = ""
    dependency_code: str = ""
    reference_code: str = ""
    strategy_context: str = ""
    generation_instructions: str = ""
    max_chars: int = 80000

    def full_prompt(self) -> str:
        """Assemble the complete generation prompt.

        Sections are appended in priority order and trimmed if the
        combined length exceeds :attr:`max_chars`.
        """
        sections: List[tuple[str, str, bool]] = [
            # (header, content, required)
            ("TASK", self._task_section(), True),
            ("ARCHITECTURE", self.architecture_summary, True),
            ("STRATEGY CONTEXT", self.strategy_context, True),
            ("PREVIOUSLY GENERATED FILES (summaries)", self.cumulative_summary, False),
            ("DEPENDENCY CODE (full source)", self.dependency_code, True),
            ("REFERENCE CODE", self.reference_code, False),
            ("INSTRUCTIONS", self.generation_instructions, True),
        ]

        parts: List[str] = []
        budget = self.max_chars
        required_size = 0

        # First pass: calculate required section sizes
        for header, content, required in sections:
            if required and content:
                required_size += len(header) + len(content) + 20

        # Second pass: assemble with trimming
        for header, content, required in sections:
            if not content:
                continue
            block = f"## {header}\n{content}\n\n"
            if len(block) > budget:
                # Trim content to fit remaining budget
                available = max(200, budget - len(header) - 20)
                block = f"## {header}\n{content[:available]}...\n\n"
            parts.append(block)
            budget -= len(block)
            if budget <= 0:
                break

        return "".join(parts)

    def estimated_tokens(self) -> int:
        """Rough token estimate (4 chars per token)."""
        return len(self.full_prompt()) // 4

    def _task_section(self) -> str:
        """Build the task description section."""
        return (
            f"Generate the Python file '{self.target_path}' for a "
            f"quantitative trading backtest.\n"
            f"Description: {self.target_description}\n\n"
            "REQUIREMENTS:\n"
            "- Implement EXACTLY what the paper describes\n"
            "- Use pandas/numpy for vectorized operations\n"
            "- Include docstrings with paper equation references\n"
            "- Use config references for ALL hyperparameters (never hardcode)\n"
            "- NO look-ahead bias: signals must use only past data\n"
            "- Proper date alignment: signal computed at time t, trade at t+1\n"
            "- Handle missing data with forward-fill or drop as appropriate\n"
            "- Include type hints\n"
            "- Follow quantitative finance conventions\n\n"
            "Return ONLY the Python code. No markdown fences."
        )


# ──────────────────────────────────────────────────────────────────────
# Context Manager
# ──────────────────────────────────────────────────────────────────────

class ContextManager:
    """Clean-slate context builder for file-by-file generation.

    After each file is generated, :meth:`record_file` creates a compact
    summary.  Before each new file, :meth:`build_prompt` assembles a
    fresh :class:`GenerationContext` from scratch.

    Parameters:
        provider: LLM provider (used to generate summaries).
        plan: Architecture plan with ``.files`` list.
        paper_text: Full or abridged paper text.
        strategy_extraction: Extracted strategy details.
        config: Optional :class:`Q2RConfig`.
        code_rag_index: Optional :class:`CodeRAGIndex` for reference code.
        max_prompt_chars: Maximum prompt length in characters.
        use_llm_summaries: Use LLM to generate file summaries (vs. heuristic).
    """

    # Implicit dependency map (same as CodeSynthesizer).
    _IMPLICIT_DEPS: Dict[str, List[str]] = {
        "signals.py": ["config.py", "data_loader.py"],
        "portfolio.py": ["config.py", "signals.py"],
        "analysis.py": ["config.py", "portfolio.py"],
        "visualization.py": ["config.py", "analysis.py"],
        "main.py": ["config.py", "data_loader.py", "signals.py"],
    }

    def __init__(
        self,
        provider: Any,
        plan: Any,
        paper_text: str,
        strategy_extraction: dict,
        config: Optional[Any] = None,
        code_rag_index: Optional[Any] = None,
        max_prompt_chars: int = 80000,
        use_llm_summaries: bool = True,
    ) -> None:
        self.provider = provider
        self.plan = plan
        self.paper_text = paper_text
        self.strategy_extraction = strategy_extraction
        self.config = config
        self.code_rag_index = code_rag_index
        self.max_prompt_chars = max_prompt_chars
        self.use_llm_summaries = use_llm_summaries

        # State
        self._file_summaries: Dict[str, FileSummary] = {}
        self._generated_files: Dict[str, str] = {}

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def build_prompt(self, file_info: dict) -> GenerationContext:
        """Build a clean-slate prompt for generating a file.

        Args:
            file_info: Dict with ``path``, ``description``, and optional
                ``dependencies`` list.

        Returns:
            A fully assembled :class:`GenerationContext`.
        """
        path = file_info.get("path", "")
        description = file_info.get("description", "")

        ctx = GenerationContext(
            target_path=path,
            target_description=description,
            max_chars=self.max_prompt_chars,
        )

        # 1. Architecture summary
        ctx.architecture_summary = self._build_architecture_summary()

        # 2. Strategy context
        ctx.strategy_context = self._build_strategy_context()

        # 3. Cumulative summaries of prior files
        ctx.cumulative_summary = self._build_cumulative_summary()

        # 4. Full source of direct dependencies
        deps = self._resolve_dependencies(file_info)
        ctx.dependency_code = self._build_dependency_code(deps)

        # 5. Reference code (CodeRAG)
        ctx.reference_code = self._build_reference_code(path)

        # 6. File-specific generation instructions
        ctx.generation_instructions = self._build_instructions(file_info)

        logger.debug(
            "Context for %s: ~%d tokens, %d deps, %d summaries",
            path,
            ctx.estimated_tokens(),
            len(deps),
            len(self._file_summaries),
        )

        return ctx

    def record_file(self, path: str, content: str) -> None:
        """Record a generated file and create its compact summary.

        This must be called after each file is generated so that
        subsequent files can reference it.

        Args:
            path: Relative path of the generated file.
            content: Full source content.
        """
        self._generated_files[path] = content

        if self.use_llm_summaries:
            summary = self._llm_summarize(path, content)
        else:
            summary = self._heuristic_summarize(path, content)

        self._file_summaries[path] = summary

        logger.debug(
            "Recorded %s (%d chars, summary: %d chars)",
            path,
            len(content),
            len(summary.summary),
        )

    @property
    def generated_files(self) -> Dict[str, str]:
        """Return all files recorded so far."""
        return dict(self._generated_files)

    # ──────────────────────────────────────────────────────────────────
    # Context section builders
    # ──────────────────────────────────────────────────────────────────

    def _build_architecture_summary(self) -> str:
        """Build a compressed architecture summary from the plan."""
        if not self.plan:
            return ""

        files = getattr(self.plan, "files", [])
        lines: List[str] = ["Repository structure:"]
        for f in files:
            if isinstance(f, dict):
                path = f.get("path", "")
                desc = f.get("description", "")
                status = (
                    "DONE" if path in self._generated_files else "pending"
                )
                lines.append(f"  {path}: {desc} [{status}]")
            else:
                lines.append(f"  {f}")

        summary = getattr(self.plan, "summary", "")
        if summary:
            lines.insert(1, f"Strategy: {summary[:300]}")

        return "\n".join(lines)

    def _build_strategy_context(self) -> str:
        """Build a compressed strategy context string."""
        if not self.strategy_extraction:
            return ""

        # Include only the most relevant fields
        key_fields = [
            "strategy_name", "signal_types", "signals",
            "portfolio_construction", "data_frequency",
            "key_equations", "universe_description",
        ]
        filtered: Dict[str, Any] = {}
        se = self.strategy_extraction
        if isinstance(se, dict):
            for k in key_fields:
                if k in se and se[k]:
                    filtered[k] = se[k]
        else:
            # Assume it's a dataclass-like object
            for k in key_fields:
                v = getattr(se, k, None)
                if v:
                    filtered[k] = v

        return json.dumps(filtered, default=str, indent=2)[:5000]

    def _build_cumulative_summary(self) -> str:
        """Build one-paragraph-per-file summaries of prior generated files."""
        if not self._file_summaries:
            return ""

        lines: List[str] = []
        for path, fs in self._file_summaries.items():
            exports_str = ", ".join(fs.exports[:10]) if fs.exports else "—"
            lines.append(
                f"**{path}** ({fs.char_count} chars): {fs.summary}\n"
                f"  Exports: {exports_str}"
            )

        return "\n\n".join(lines)

    def _build_dependency_code(self, deps: List[str]) -> str:
        """Build full source for dependency files."""
        parts: List[str] = []
        # Budget: reserve ~40% of max_chars for dependency code
        budget = int(self.max_prompt_chars * 0.4)
        used = 0

        for dep in deps:
            if dep in self._generated_files:
                code = self._generated_files[dep]
                block = f"# === {dep} ===\n{code}\n"
                if used + len(block) > budget:
                    # Truncate this dependency
                    remaining = max(500, budget - used)
                    block = f"# === {dep} (truncated) ===\n{code[:remaining]}\n"
                parts.append(block)
                used += len(block)

        return "\n".join(parts)

    def _build_reference_code(self, target_path: str) -> str:
        """Fetch reference code from the CodeRAG index."""
        if not self.code_rag_index:
            return ""

        # Use CodeRAG's get_reference_context if available
        try:
            from advanced.code_rag import CodeRAG
            rag = CodeRAG.__new__(CodeRAG)
            return rag.get_reference_context(
                target_path, self.code_rag_index, max_tokens=2000
            )
        except Exception:
            pass

        # Manual fallback
        mapping = getattr(self.code_rag_index, "get_mapping", lambda p: None)(
            target_path
        )
        if not mapping:
            return ""

        parts: List[str] = []
        for ref in mapping.top_k(2):
            parts.append(
                f"# Reference: {ref.repo}/{ref.path}\n{ref.content[:2000]}"
            )
        return "\n\n".join(parts)

    def _build_instructions(self, file_info: dict) -> str:
        """Build file-specific generation instructions."""
        path = file_info.get("path", "")
        instructions: List[str] = []

        # Add logic design spec if available
        if self.plan:
            logic = getattr(self.plan, "logic_design", None)
            if logic:
                specs = getattr(logic, "file_specifications", {})
                if path in specs:
                    instructions.append(
                        f"File specification:\n{json.dumps(specs[path], default=str)[:2000]}"
                    )

        # Add dependency imports hint
        deps = self._resolve_dependencies(file_info)
        if deps:
            dep_exports: List[str] = []
            for dep in deps:
                if dep in self._file_summaries:
                    fs = self._file_summaries[dep]
                    dep_exports.extend(
                        f"{dep}: {exp}" for exp in fs.exports[:5]
                    )
            if dep_exports:
                instructions.append(
                    "Available imports from dependencies:\n"
                    + "\n".join(f"  - {e}" for e in dep_exports)
                )

        return "\n\n".join(instructions) if instructions else ""

    # ──────────────────────────────────────────────────────────────────
    # Dependency resolution
    # ──────────────────────────────────────────────────────────────────

    def _resolve_dependencies(self, file_info: dict) -> List[str]:
        """Resolve the dependency list for a file."""
        deps: List[str] = file_info.get("dependencies", [])

        if not deps:
            path = file_info.get("path", "")
            base = os.path.basename(path)
            deps = self._IMPLICIT_DEPS.get(base, [])

        # Only include deps that have actually been generated
        return [d for d in deps if d in self._generated_files]

    # ──────────────────────────────────────────────────────────────────
    # File summarisation
    # ──────────────────────────────────────────────────────────────────

    def _llm_summarize(self, path: str, content: str) -> FileSummary:
        """Use the LLM to produce a compact summary of a generated file."""
        prompt = f"""Summarize this Python file for a backtest codebase in 2-3 sentences.
List the key classes, functions, and constants it exports.

File: {path}
```python
{content[:6000]}
```

Return JSON:
{{
  "summary": "2-3 sentence summary",
  "exports": ["ClassName", "function_name", "CONSTANT"],
  "imports_from_project": ["config", "data_loader"]
}}"""

        from providers.base import GenerationConfig

        config = GenerationConfig(
            temperature=0.0,
            max_output_tokens=512,
            response_format="json",
        )

        try:
            result = self.provider.generate(prompt, config=config)
            data = self._extract_json(result.text)
            return FileSummary(
                path=path,
                summary=data.get("summary", ""),
                exports=data.get("exports", []),
                imports=data.get("imports_from_project", []),
                char_count=len(content),
            )
        except Exception as e:
            logger.debug("LLM summary failed for %s: %s", path, e)
            return self._heuristic_summarize(path, content)

    @staticmethod
    def _heuristic_summarize(path: str, content: str) -> FileSummary:
        """Fast regex-based file summary (no LLM call)."""
        import re

        # Extract class names
        classes = re.findall(r"^class\s+(\w+)", content, re.MULTILINE)

        # Extract top-level function names
        functions = re.findall(
            r"^def\s+(\w+)", content, re.MULTILINE
        )
        # Filter out private functions for exports
        public_functions = [f for f in functions if not f.startswith("_")]

        # Extract UPPER_CASE constants
        constants = re.findall(
            r"^([A-Z][A-Z_0-9]+)\s*=", content, re.MULTILINE
        )

        # Extract imports from project files
        project_imports = re.findall(
            r"from\s+(\w+)\s+import", content
        )

        exports = classes + public_functions + constants[:5]

        # Build a simple summary
        parts: List[str] = []
        if classes:
            parts.append(f"Defines classes: {', '.join(classes[:5])}")
        if public_functions:
            parts.append(
                f"Functions: {', '.join(public_functions[:5])}"
            )
        summary = ". ".join(parts) if parts else f"Module at {path}"

        return FileSummary(
            path=path,
            summary=summary,
            exports=exports[:15],
            imports=project_imports,
            char_count=len(content),
        )

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extract JSON from LLM response text."""
        import re as _re

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = _re.search(r"```(?:json)?\s*\n(.*?)\n```", text, _re.DOTALL)
        if match:
            return json.loads(match.group(1))
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        return {}
