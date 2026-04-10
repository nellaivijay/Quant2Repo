"""DevOps file generator for backtest repositories.

Generates infrastructure and CI/CD files for a generated backtest repo:

- ``Dockerfile`` — Python 3.11 slim image with pandas/numpy/yfinance.
- ``docker-compose.yml`` — backtest + report services.
- ``Makefile`` — install, backtest, test, report, clean targets.
- ``.github/workflows/ci.yml`` — lint, test, backtest GitHub Actions.
- ``setup.py`` — minimal packaging for editable installs.

All files are returned as a ``dict[str, str]`` mapping relative paths to
content, ready to be merged into the generated file set.
"""

from __future__ import annotations

import json
import logging
import os
import textwrap
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DevOpsGenerator:
    """Generates DevOps / infrastructure files for a backtest repository.

    Parameters:
        config: Optional :class:`Q2RConfig` for customisation.
    """

    # Packages that every generated backtest is likely to need.
    _BASE_REQUIREMENTS: List[str] = [
        "pandas>=2.0",
        "numpy>=1.24",
        "yfinance>=0.2",
        "matplotlib>=3.7",
        "scipy>=1.10",
    ]

    def __init__(self, config: Optional[Any] = None) -> None:
        self.config = config

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def generate_all(
        self,
        plan: Any,
        strategy_extraction: dict,
        generated_files: Dict[str, str],
    ) -> Dict[str, str]:
        """Generate every DevOps file at once.

        Args:
            plan: An :class:`ArchitecturePlan` (or compatible) object.
            strategy_extraction: Strategy details extracted from the paper.
            generated_files: Already-generated source files (used to
                detect entry points and dependency requirements).

        Returns:
            A mapping of ``relative_path → content`` for all DevOps files.
        """
        strategy_name = self._safe_name(
            strategy_extraction.get("strategy_name", "backtest")
            if isinstance(strategy_extraction, dict)
            else "backtest"
        )
        entrypoint = self._detect_entrypoint(generated_files)
        extra_deps = self._detect_extra_deps(generated_files)
        python_files = [
            p for p in generated_files if p.endswith(".py")
        ]

        files: Dict[str, str] = {}
        files["Dockerfile"] = self._generate_dockerfile(entrypoint)
        files["docker-compose.yml"] = self._generate_docker_compose(
            strategy_name, entrypoint
        )
        files["Makefile"] = self._generate_makefile(
            entrypoint, python_files
        )
        files[".github/workflows/ci.yml"] = self._generate_ci_workflow(
            entrypoint, python_files
        )
        files["setup.py"] = self._generate_setup_py(
            strategy_name, strategy_extraction, extra_deps
        )

        return files

    # ──────────────────────────────────────────────────────────────────
    # Dockerfile
    # ──────────────────────────────────────────────────────────────────

    def _generate_dockerfile(self, entrypoint: str) -> str:
        """Generate a production-ready Dockerfile."""
        return textwrap.dedent(f"""\
            # ── Backtest Dockerfile ──────────────────────────────────
            FROM python:3.11-slim

            # System deps for numpy/scipy wheel builds
            RUN apt-get update && apt-get install -y --no-install-recommends \\
                gcc g++ gfortran libopenblas-dev && \\
                rm -rf /var/lib/apt/lists/*

            WORKDIR /app

            # Cache-friendly: copy requirements first
            COPY requirements.txt .
            RUN pip install --no-cache-dir -r requirements.txt

            COPY . .

            # Default command
            CMD ["python", "{entrypoint}"]
        """)

    # ──────────────────────────────────────────────────────────────────
    # docker-compose.yml
    # ──────────────────────────────────────────────────────────────────

    def _generate_docker_compose(
        self, strategy_name: str, entrypoint: str
    ) -> str:
        """Generate a docker-compose.yml with backtest and report services."""
        return textwrap.dedent(f"""\
            # ── docker-compose for {strategy_name} ──────────────────
            version: "3.9"

            services:
              backtest:
                build: .
                container_name: {strategy_name}-backtest
                volumes:
                  - ./output:/app/output
                  - ./data:/app/data
                command: ["python", "{entrypoint}"]
                environment:
                  - PYTHONUNBUFFERED=1

              report:
                build: .
                container_name: {strategy_name}-report
                volumes:
                  - ./output:/app/output
                depends_on:
                  backtest:
                    condition: service_completed_successfully
                command: ["python", "-c", "from visualization import *; generate_report()"]
                environment:
                  - PYTHONUNBUFFERED=1

              test:
                build: .
                container_name: {strategy_name}-test
                command: ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]
                environment:
                  - PYTHONUNBUFFERED=1
        """)

    # ──────────────────────────────────────────────────────────────────
    # Makefile
    # ──────────────────────────────────────────────────────────────────

    def _generate_makefile(
        self, entrypoint: str, python_files: List[str]
    ) -> str:
        """Generate a Makefile with standard targets."""
        py_list = " ".join(python_files) if python_files else "*.py"
        return textwrap.dedent(f"""\
            # ── Makefile ─────────────────────────────────────────────
            .PHONY: install backtest test lint report clean docker-build docker-run help

            PYTHON   ?= python
            PIP      ?= pip
            ENTRY    ?= {entrypoint}
            PY_FILES := {py_list}

            help:  ## Show this help
            \t@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \\
            \t  awk 'BEGIN {{FS = ":.*?## "}}; {{printf "  \\033[36m%-15s\\033[0m %s\\n", $$1, $$2}}'

            install:  ## Install Python dependencies
            \t$(PIP) install -r requirements.txt

            backtest:  ## Run the backtest
            \t$(PYTHON) $(ENTRY)

            test:  ## Run pytest suite
            \t$(PYTHON) -m pytest tests/ -v --tb=short

            lint:  ## Run ruff linter
            \t$(PYTHON) -m ruff check $(PY_FILES)

            format:  ## Auto-format with ruff
            \t$(PYTHON) -m ruff format $(PY_FILES)

            report:  ## Generate HTML/PDF report from backtest output
            \t$(PYTHON) -c "from visualization import generate_report; generate_report()"

            docker-build:  ## Build Docker image
            \tdocker build -t backtest .

            docker-run:  ## Run backtest in Docker
            \tdocker run --rm -v $$(pwd)/output:/app/output backtest

            clean:  ## Remove artefacts
            \trm -rf output/ __pycache__/ .pytest_cache/ *.egg-info/ dist/ build/
            \tfind . -name '*.pyc' -delete
            \tfind . -name '__pycache__' -type d -exec rm -rf {{}} +
        """)

    # ──────────────────────────────────────────────────────────────────
    # GitHub Actions CI
    # ──────────────────────────────────────────────────────────────────

    def _generate_ci_workflow(
        self, entrypoint: str, python_files: List[str]
    ) -> str:
        """Generate a GitHub Actions CI workflow."""
        py_list = " ".join(python_files) if python_files else "*.py"
        return textwrap.dedent(f"""\
            # ── GitHub Actions CI ────────────────────────────────────
            name: CI

            on:
              push:
                branches: [main, master]
              pull_request:
                branches: [main, master]

            jobs:
              lint:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4

                  - name: Set up Python
                    uses: actions/setup-python@v5
                    with:
                      python-version: "3.11"

                  - name: Install dependencies
                    run: |
                      python -m pip install --upgrade pip
                      pip install ruff
                      pip install -r requirements.txt

                  - name: Lint with ruff
                    run: ruff check {py_list}

              test:
                runs-on: ubuntu-latest
                needs: lint
                steps:
                  - uses: actions/checkout@v4

                  - name: Set up Python
                    uses: actions/setup-python@v5
                    with:
                      python-version: "3.11"

                  - name: Install dependencies
                    run: |
                      python -m pip install --upgrade pip
                      pip install -r requirements.txt
                      pip install pytest

                  - name: Run tests
                    run: python -m pytest tests/ -v --tb=short

              backtest:
                runs-on: ubuntu-latest
                needs: test
                steps:
                  - uses: actions/checkout@v4

                  - name: Set up Python
                    uses: actions/setup-python@v5
                    with:
                      python-version: "3.11"

                  - name: Install dependencies
                    run: |
                      python -m pip install --upgrade pip
                      pip install -r requirements.txt

                  - name: Run backtest
                    run: python {entrypoint}
                    timeout-minutes: 30

                  - name: Upload results
                    if: always()
                    uses: actions/upload-artifact@v4
                    with:
                      name: backtest-results
                      path: output/
                      if-no-files-found: ignore
        """)

    # ──────────────────────────────────────────────────────────────────
    # setup.py
    # ──────────────────────────────────────────────────────────────────

    def _generate_setup_py(
        self,
        strategy_name: str,
        strategy_extraction: dict,
        extra_deps: List[str],
    ) -> str:
        """Generate a minimal setup.py for editable installs."""
        description = ""
        authors = []
        if isinstance(strategy_extraction, dict):
            description = strategy_extraction.get("abstract_summary", "")[:200]
            authors = strategy_extraction.get("authors", [])

        author_str = ", ".join(authors) if authors else "Quant2Repo"
        all_deps = list(self._BASE_REQUIREMENTS) + extra_deps
        deps_str = json.dumps(all_deps, indent=8)

        return textwrap.dedent(f"""\
            \"\"\"Minimal setup.py for {strategy_name} backtest.\"\"\"

            from setuptools import setup, find_packages

            setup(
                name="{strategy_name}",
                version="0.1.0",
                description=\"\"\"{description}\"\"\",
                author="{author_str}",
                python_requires=">=3.10",
                install_requires={deps_str},
                packages=find_packages(),
                entry_points={{
                    "console_scripts": [
                        "{strategy_name}=main:main",
                    ],
                }},
            )
        """)

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _detect_entrypoint(generated_files: Dict[str, str]) -> str:
        """Determine the most likely entry-point file."""
        for candidate in ("main.py", "run.py", "backtest.py", "run_backtest.py"):
            if candidate in generated_files:
                return candidate
        # Fallback: first .py file that contains 'if __name__'
        for path, content in generated_files.items():
            if path.endswith(".py") and '__name__' in content:
                return path
        return "main.py"

    @staticmethod
    def _detect_extra_deps(generated_files: Dict[str, str]) -> List[str]:
        """Scan generated code for additional third-party imports."""
        known_extras: Dict[str, str] = {
            "statsmodels": "statsmodels>=0.14",
            "sklearn": "scikit-learn>=1.3",
            "seaborn": "seaborn>=0.12",
            "plotly": "plotly>=5.15",
            "pyfolio": "pyfolio-reloaded>=0.9",
            "empyrical": "empyrical-reloaded>=0.5",
            "cvxpy": "cvxpy>=1.3",
            "arch": "arch>=6.0",
            "fredapi": "fredapi>=0.5",
            "wrds": "wrds>=3.1",
            "requests": "requests>=2.31",
            "tqdm": "tqdm>=4.65",
            "joblib": "joblib>=1.3",
            "openpyxl": "openpyxl>=3.1",
        }
        found: List[str] = []
        for content in generated_files.values():
            for module, pip_spec in known_extras.items():
                if f"import {module}" in content or f"from {module}" in content:
                    if pip_spec not in found:
                        found.append(pip_spec)
        return found

    @staticmethod
    def _safe_name(name: str) -> str:
        """Sanitise a strategy name for use in file/image names."""
        import re
        safe = re.sub(r"[^a-z0-9_-]", "-", name.lower().strip())
        safe = re.sub(r"-+", "-", safe).strip("-")
        return safe or "backtest"
