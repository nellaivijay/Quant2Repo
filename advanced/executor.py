"""Execution sandbox — Docker/local runner for generated backtests.

Provides a sandboxed execution environment for running generated backtest
code.  Prefers Docker for isolation (if available), falling back to a
direct local subprocess.  Captures stdout/stderr, classifies errors, and
reports execution duration.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────

@dataclass
class ExecutionResult:
    """Result of a single backtest execution attempt.

    Attributes:
        success: ``True`` if the process exited with code 0.
        stdout: Captured standard output.
        stderr: Captured standard error.
        exit_code: Process exit code (``-1`` if never launched).
        duration_seconds: Wall-clock execution time.
        error_type: Classified error name (empty when successful).
        modified_files: List of files created or modified during execution.
    """

    success: bool = False
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    duration_seconds: float = 0.0
    error_type: str = ""
    modified_files: List[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────
# Sandbox
# ──────────────────────────────────────────────────────────────────────

class ExecutionSandbox:
    """Runs generated backtest in Docker or local sandbox.

    The sandbox first checks whether Docker is available.  If so it
    builds an image from the repo directory and runs the entrypoint
    inside a container.  Otherwise it falls back to a plain
    ``subprocess.run`` with the repo dir on ``PYTHONPATH``.

    Parameters:
        prefer_docker: Try Docker first if ``True`` (default).
        timeout: Maximum execution time in seconds.
        python_cmd: Python interpreter command (e.g. ``"python3"``).
    """

    def __init__(
        self,
        prefer_docker: bool = True,
        timeout: int = 300,
        python_cmd: str = "python",
    ) -> None:
        self.prefer_docker = prefer_docker
        self.timeout = timeout
        self.python_cmd = python_cmd

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def execute(
        self,
        repo_dir: str,
        entrypoint: str = "main.py",
        args: Optional[List[str]] = None,
    ) -> ExecutionResult:
        """Execute the backtest.

        Args:
            repo_dir: Path to the generated repository.
            entrypoint: Python file to run (relative to *repo_dir*).
            args: Extra CLI arguments forwarded to the entrypoint.

        Returns:
            An :class:`ExecutionResult` with captured output.
        """
        if self.prefer_docker and self._docker_available():
            return self._run_in_docker(repo_dir, entrypoint, args)
        return self._run_locally(repo_dir, entrypoint, args)

    def execute_command(
        self,
        repo_dir: str,
        command: List[str],
    ) -> ExecutionResult:
        """Run an arbitrary command inside the repo directory.

        Args:
            repo_dir: Working directory.
            command: Command and arguments as a list.

        Returns:
            An :class:`ExecutionResult`.
        """
        start = time.time()
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=repo_dir,
                env={**os.environ, "PYTHONPATH": repo_dir},
            )
            duration = time.time() - start
            return ExecutionResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_seconds=duration,
                error_type=(
                    self._classify_error(result.stderr)
                    if result.returncode != 0
                    else ""
                ),
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                stderr="Execution timed out",
                error_type="TimeoutError",
                duration_seconds=self.timeout,
            )
        except FileNotFoundError as exc:
            return ExecutionResult(
                success=False,
                stderr=str(exc),
                error_type="FileNotFoundError",
            )

    # ──────────────────────────────────────────────────────────────────
    # Docker execution
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _docker_available() -> bool:
        """Return ``True`` if Docker is installed and responsive."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _run_in_docker(
        self,
        repo_dir: str,
        entrypoint: str,
        args: Optional[List[str]],
    ) -> ExecutionResult:
        """Build and run the backtest inside a Docker container."""
        dockerfile_path = os.path.join(repo_dir, "Dockerfile")
        if not os.path.exists(dockerfile_path):
            self._generate_dockerfile(repo_dir)

        tag = f"q2r-backtest-{os.path.basename(repo_dir).lower()}"

        # Build image
        try:
            build_result = subprocess.run(
                ["docker", "build", "-t", tag, "."],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Docker build timed out, falling back to local")
            return self._run_locally(repo_dir, entrypoint, args)

        if build_result.returncode != 0:
            logger.warning(
                "Docker build failed, falling back to local: %s",
                build_result.stderr[:500],
            )
            return self._run_locally(repo_dir, entrypoint, args)

        # Run container
        abs_repo = os.path.abspath(repo_dir)
        cmd: List[str] = [
            "docker", "run", "--rm",
            "--network=host",
            "-v", f"{abs_repo}:/app/output",
            tag,
            "python", entrypoint,
        ]
        if args:
            cmd.extend(args)

        start = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=repo_dir,
            )
            duration = time.time() - start

            return ExecutionResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_seconds=duration,
                error_type=(
                    self._classify_error(result.stderr)
                    if result.returncode != 0
                    else ""
                ),
            )
        except subprocess.TimeoutExpired:
            # Attempt to kill the container
            try:
                subprocess.run(
                    ["docker", "kill", tag],
                    capture_output=True,
                    timeout=10,
                )
            except Exception:
                pass
            return ExecutionResult(
                success=False,
                stderr="Execution timed out",
                error_type="TimeoutError",
                duration_seconds=self.timeout,
            )

    # ──────────────────────────────────────────────────────────────────
    # Local execution
    # ──────────────────────────────────────────────────────────────────

    def _run_locally(
        self,
        repo_dir: str,
        entrypoint: str,
        args: Optional[List[str]],
    ) -> ExecutionResult:
        """Run the backtest directly as a subprocess."""
        # Install requirements if present
        req_path = os.path.join(repo_dir, "requirements.txt")
        if os.path.exists(req_path):
            try:
                subprocess.run(
                    [self.python_cmd, "-m", "pip", "install", "-q", "-r", req_path],
                    capture_output=True,
                    timeout=120,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
                logger.warning("pip install failed: %s", exc)

        cmd: List[str] = [self.python_cmd, entrypoint]
        if args:
            cmd.extend(args)

        start = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=repo_dir,
                env={**os.environ, "PYTHONPATH": repo_dir},
            )
            duration = time.time() - start

            return ExecutionResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_seconds=duration,
                error_type=(
                    self._classify_error(result.stderr)
                    if result.returncode != 0
                    else ""
                ),
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                stderr="Execution timed out",
                error_type="TimeoutError",
                duration_seconds=self.timeout,
            )

    # ──────────────────────────────────────────────────────────────────
    # Dockerfile generation
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _generate_dockerfile(repo_dir: str) -> None:
        """Generate a minimal Dockerfile for the backtest repo."""
        dockerfile = """\
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for common quant packages
RUN apt-get update && apt-get install -y --no-install-recommends \\
    gcc g++ && \\
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
"""
        with open(os.path.join(repo_dir, "Dockerfile"), "w") as f:
            f.write(dockerfile)

    # ──────────────────────────────────────────────────────────────────
    # Error classification
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _classify_error(stderr: str) -> str:
        """Classify the Python error from stderr output.

        Returns the first matching Python exception type, or
        ``"UnknownError"`` if none is found.
        """
        error_types = [
            "SyntaxError",
            "ImportError",
            "ModuleNotFoundError",
            "NameError",
            "TypeError",
            "ValueError",
            "KeyError",
            "IndexError",
            "AttributeError",
            "FileNotFoundError",
            "PermissionError",
            "ConnectionError",
            "TimeoutError",
            "MemoryError",
            "ZeroDivisionError",
            "RuntimeError",
            "StopIteration",
            "OSError",
            "RecursionError",
        ]
        for error_type in error_types:
            if error_type in stderr:
                return error_type
        return "UnknownError"
