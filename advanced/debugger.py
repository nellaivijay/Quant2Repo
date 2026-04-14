"""Auto-debugger — iterative error fixing for backtest code.

Analyses execution failures, generates targeted fixes via the LLM
provider, applies them, and re-executes until the backtest succeeds or
the iteration budget is exhausted.  Pairs naturally with
:class:`~advanced.executor.ExecutionSandbox`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────

@dataclass
class DebugFix:
    """A single file-level fix produced by the debugger."""

    file_path: str = ""
    original_content: str = ""
    fixed_content: str = ""
    error_description: str = ""
    fix_description: str = ""


@dataclass
class DebugReport:
    """Report for one debug iteration."""

    iteration: int = 0
    error_message: str = ""
    error_type: str = ""
    fixes: List[DebugFix] = field(default_factory=list)
    resolved: bool = False

    @property
    def files_changed(self) -> List[str]:
        """Paths of files that were modified in this iteration."""
        return [f.file_path for f in self.fixes]


# ──────────────────────────────────────────────────────────────────────
# Debugger
# ──────────────────────────────────────────────────────────────────────

class AutoDebugger:
    """Iterative error analysis and fixing for generated backtests.

    The debug loop:

    1. Analyse the execution failure (error type, traceback, root cause).
    2. Ask the LLM to produce corrected file contents.
    3. Write fixes back to the repo directory.
    4. Re-run via the supplied executor.
    5. Repeat until success or *max_iterations* is reached.

    Parameters:
        provider: An LLM provider instance.
        config: Optional :class:`Q2RConfig`.
        max_iterations: Maximum number of fix-and-retry cycles.
    """

    # Common error → hint mapping for enriching the analysis prompt.
    _ERROR_HINTS: Dict[str, str] = {
        "ImportError": (
            "A required package is missing or the import path is wrong. "
            "Check requirements.txt and relative imports."
        ),
        "ModuleNotFoundError": (
            "A required package is missing. Add it to requirements.txt "
            "or fix the import statement."
        ),
        "NameError": (
            "A variable or function is used before definition. "
            "Check import statements and spelling."
        ),
        "TypeError": (
            "A function received the wrong argument type or count. "
            "Check API signatures and data types."
        ),
        "KeyError": (
            "A dictionary or DataFrame is missing an expected key/column. "
            "Verify column names and data schema."
        ),
        "FileNotFoundError": (
            "A file path is incorrect or the file does not exist. "
            "Check data paths and working directory assumptions."
        ),
        "SyntaxError": (
            "There is a Python syntax error. Check for missing colons, "
            "parentheses, or incorrect indentation."
        ),
        "ValueError": (
            "An operation received an argument with the right type but "
            "inappropriate value. Check array shapes, date formats, etc."
        ),
        "AttributeError": (
            "An object does not have the expected attribute or method. "
            "Check the API and ensure correct object types."
        ),
    }

    def __init__(
        self,
        provider: Any,
        config: Optional[Any] = None,
        max_iterations: int = 3,
    ) -> None:
        self.provider = provider
        self.config = config
        self.max_iterations = max_iterations

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def debug(
        self,
        repo_dir: str,
        execution_result: Any,
        generated_files: Dict[str, str],
        executor: Optional[Any] = None,
    ) -> Tuple[Dict[str, str], List[DebugReport]]:
        """Debug failed execution iteratively.

        Args:
            repo_dir: Path to the generated repository on disk.
            execution_result: The failed :class:`ExecutionResult`.
            generated_files: Current mapping of path → source content.
            executor: Optional :class:`ExecutionSandbox` for re-running.

        Returns:
            A tuple of (updated files dict, list of debug reports).
        """
        debug_reports: List[DebugReport] = []
        current_files = dict(generated_files)

        for i in range(self.max_iterations):
            if execution_result.success:
                break

            logger.info(
                "Debug iteration %d/%d: %s",
                i + 1,
                self.max_iterations,
                execution_result.error_type,
            )

            # Analyse the error
            analysis = self._analyze_error(execution_result, current_files)

            # Generate fixes
            fixes = self._generate_fixes(
                analysis, current_files, execution_result
            )

            report = DebugReport(
                iteration=i + 1,
                error_message=execution_result.stderr[:500],
                error_type=execution_result.error_type,
                fixes=fixes,
            )

            # Apply fixes to in-memory file dict
            for fix in fixes:
                if fix.file_path and fix.fixed_content:
                    fix.original_content = current_files.get(fix.file_path, "")
                    current_files[fix.file_path] = fix.fixed_content

            # Write only modified files to disk and re-execute
            if executor and fixes:
                for fix in fixes:
                    if fix.file_path and fix.fixed_content:
                        full_path = os.path.join(repo_dir, fix.file_path)
                        os.makedirs(os.path.dirname(full_path), exist_ok=True)
                        with open(full_path, "w") as f:
                            f.write(fix.fixed_content)
                execution_result = executor.execute(repo_dir)
                report.resolved = execution_result.success

            debug_reports.append(report)

            if report.resolved:
                logger.info("Debug resolved after %d iteration(s)", i + 1)
                break

        return current_files, debug_reports

    # ──────────────────────────────────────────────────────────────────
    # Error analysis
    # ──────────────────────────────────────────────────────────────────

    def _analyze_error(
        self,
        execution_result: Any,
        files: Dict[str, str],
    ) -> str:
        """Ask the LLM to analyse the root cause of the failure."""
        hint = self._ERROR_HINTS.get(execution_result.error_type, "")
        prompt = self._build_analysis_prompt(execution_result, files, hint)

        from providers.base import GenerationConfig

        config = GenerationConfig(temperature=0.1, max_output_tokens=2048)
        try:
            result = self.provider.generate(prompt, config=config)
            return result.text
        except Exception as e:
            logger.warning("Error analysis failed: %s", e)
            return f"Analysis unavailable: {e}"

    def _build_analysis_prompt(
        self,
        execution_result: Any,
        files: Dict[str, str],
        hint: str = "",
    ) -> str:
        """Construct the analysis prompt."""
        # Identify the file most likely responsible from the traceback
        suspect_files = self._extract_suspect_files(
            execution_result.stderr, files
        )

        suspect_code = ""
        for sf in suspect_files[:3]:
            if sf in files:
                suspect_code += f"\n# === {sf} ===\n{files[sf][:2000]}\n"

        return f"""Analyze this backtest execution error.

Error type: {execution_result.error_type}
{f"Hint: {hint}" if hint else ""}

Error output:
{execution_result.stderr[:2000]}

Stdout:
{execution_result.stdout[:1000]}

Suspect file(s):
{suspect_code}

What is the root cause? Which file(s) need fixing? Be specific about the
exact line or construct that caused the failure."""

    @staticmethod
    def _extract_suspect_files(
        stderr: str, files: Dict[str, str]
    ) -> List[str]:
        """Extract filenames mentioned in a Python traceback."""
        # Match 'File "some_file.py"' in traceback
        matches = re.findall(r'File "([^"]+\.py)"', stderr)
        suspects: List[str] = []
        basenames = {os.path.basename(p): p for p in files}
        for m in matches:
            base = os.path.basename(m)
            if base in basenames:
                suspects.append(basenames[base])
        return list(dict.fromkeys(suspects))  # deduplicate, preserve order

    # ──────────────────────────────────────────────────────────────────
    # Fix generation
    # ──────────────────────────────────────────────────────────────────

    def _generate_fixes(
        self,
        analysis: str,
        files: Dict[str, str],
        execution_result: Any,
    ) -> List[DebugFix]:
        """Ask the LLM to produce corrected file contents."""
        prompt_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "prompts",
            "auto_debug.txt",
        )

        files_text = self._format_files(files)

        if os.path.exists(prompt_path):
            with open(prompt_path) as f:
                template = f.read()
            template = template.replace(
                "{{error_message}}", execution_result.stderr[:2000]
            )
            template = template.replace(
                "{{error_type}}", execution_result.error_type
            )
            template = template.replace(
                "{{file_contents}}", files_text[:20000]
            )
            template = template.replace(
                "{{traceback}}", execution_result.stderr[:3000]
            )
            prompt = template
        else:
            prompt = self._default_fix_prompt(
                execution_result, files_text, analysis
            )

        from providers.base import GenerationConfig

        config = GenerationConfig(
            temperature=0.15,
            max_output_tokens=16384,
            response_format="json",
        )

        try:
            result = self.provider.generate(prompt, config=config)
            data = self._extract_json(result.text)
        except Exception as e:
            logger.warning("Fix generation failed: %s", e)
            return []

        fixes: List[DebugFix] = []
        for fix_data in data.get("fixes", []):
            path = fix_data.get("file_path", "")
            # Validate that the fix targets a known file
            if path and (path in files or path.endswith(".txt")):
                fixes.append(DebugFix(
                    file_path=path,
                    fixed_content=fix_data.get("fixed_content", ""),
                    error_description=execution_result.stderr[:200],
                    fix_description=fix_data.get("description", ""),
                ))
        return fixes

    def _default_fix_prompt(
        self,
        execution_result: Any,
        files_text: str,
        analysis: str,
    ) -> str:
        """Fallback prompt when the template file is missing."""
        return f"""Fix this backtest execution error.

ERROR ({execution_result.error_type}):
{execution_result.stderr[:2000]}

FILES:
{files_text[:20000]}

ANALYSIS:
{analysis[:2000]}

Return JSON with this exact schema:
{{
  "fixes": [
    {{
      "file_path": "filename.py",
      "description": "What was wrong and what was changed",
      "fixed_content": "COMPLETE corrected file content (not a diff)"
    }}
  ]
}}

IMPORTANT:
- Return the COMPLETE file content for each fix, not just the changed lines.
- Fix the root cause, not just the symptom.
- Maintain all existing functionality."""

    # ──────────────────────────────────────────────────────────────────
    # File I/O
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _write_files(repo_dir: str, files: Dict[str, str]) -> None:
        """Write the current file dict back to disk."""
        for path, content in files.items():
            full_path = os.path.join(repo_dir, path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)

    @staticmethod
    def _format_files(
        files: Dict[str, str], max_per_file: int = 3000
    ) -> str:
        """Format files dict into a single text block for the prompt."""
        parts: List[str] = []
        for path, content in files.items():
            if path.endswith(".py"):
                parts.append(f"\n# === {path} ===\n{content[:max_per_file]}")
        return "\n".join(parts)

    # ──────────────────────────────────────────────────────────────────
    # JSON extraction
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extract JSON from LLM response text."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        return {"fixes": []}
