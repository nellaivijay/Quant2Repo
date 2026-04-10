"""Content-addressed pipeline cache.

Provides file-system-backed caching for every stage of the Quant2Repo
pipeline: PDF extraction, architecture plans, generated source files,
and arbitrary metadata.  Each artifact set is keyed by a hash derived
from the input PDF, enabling fast re-runs without re-calling the LLM.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class PipelineCache:
    """File-system cache for pipeline artifacts.

    Artifacts are stored under ``<cache_dir>/<pdf_hash>/`` where
    *pdf_hash* is typically the first 16 hex characters of the SHA-256
    digest of the input PDF.

    Directory layout per paper::

        <cache_dir>/
          <pdf_hash>/
            extraction.pkl    — pickled strategy extraction
            plan.pkl          — pickled architecture plan
            metadata.json     — JSON metadata (provider, timestamps, …)
            files/            — generated source tree
              config.py
              data_loader.py
              …

    Parameters:
        cache_dir: Root directory for all cache data.
    """

    def __init__(self, cache_dir: str = ".q2r_cache") -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ──────────────────────────────────────────────────────────────────
    # Hashing helpers
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def hash_file(file_path: str) -> str:
        """Return a 16-char hex SHA-256 hash of a file's contents."""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()[:16]

    @staticmethod
    def hash_text(text: str) -> str:
        """Return a 16-char hex SHA-256 hash of a string."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    # ──────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────

    def _artifact_dir(self, pdf_hash: str) -> Path:
        """Return (and create) the artifact directory for *pdf_hash*."""
        d = self.cache_dir / pdf_hash
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ──────────────────────────────────────────────────────────────────
    # Extraction (strategy extraction pickle)
    # ──────────────────────────────────────────────────────────────────

    def has_extraction(self, pdf_hash: str) -> bool:
        """Return ``True`` if a cached extraction exists for *pdf_hash*."""
        return (self._artifact_dir(pdf_hash) / "extraction.pkl").exists()

    def save_extraction(self, pdf_hash: str, extraction: Any) -> None:
        """Persist a strategy extraction to disk."""
        path = self._artifact_dir(pdf_hash) / "extraction.pkl"
        with open(path, "wb") as f:
            pickle.dump(extraction, f)
        logger.debug("Saved extraction cache for %s", pdf_hash)

    def load_extraction(self, pdf_hash: str) -> Any:
        """Load a previously cached extraction."""
        path = self._artifact_dir(pdf_hash) / "extraction.pkl"
        with open(path, "rb") as f:
            return pickle.load(f)  # noqa: S301

    # ──────────────────────────────────────────────────────────────────
    # Architecture plan
    # ──────────────────────────────────────────────────────────────────

    def has_plan(self, pdf_hash: str) -> bool:
        """Return ``True`` if a cached plan exists for *pdf_hash*."""
        return (self._artifact_dir(pdf_hash) / "plan.pkl").exists()

    def save_plan(self, pdf_hash: str, plan: Any) -> None:
        """Persist an architecture plan to disk."""
        path = self._artifact_dir(pdf_hash) / "plan.pkl"
        with open(path, "wb") as f:
            pickle.dump(plan, f)
        logger.debug("Saved plan cache for %s", pdf_hash)

    def load_plan(self, pdf_hash: str) -> Any:
        """Load a previously cached plan."""
        path = self._artifact_dir(pdf_hash) / "plan.pkl"
        with open(path, "rb") as f:
            return pickle.load(f)  # noqa: S301

    # ──────────────────────────────────────────────────────────────────
    # Generated files
    # ──────────────────────────────────────────────────────────────────

    def has_generated_files(self, pdf_hash: str) -> bool:
        """Return ``True`` if cached generated files exist for *pdf_hash*."""
        return (self._artifact_dir(pdf_hash) / "files").is_dir()

    def save_generated_files(self, pdf_hash: str, files: Dict[str, str]) -> None:
        """Persist generated source files to disk.

        Args:
            pdf_hash: Cache key.
            files: Mapping of relative path → file content.
        """
        files_dir = self._artifact_dir(pdf_hash) / "files"
        files_dir.mkdir(parents=True, exist_ok=True)
        for path, content in files.items():
            file_path = files_dir / path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
        logger.debug("Saved %d generated files for %s", len(files), pdf_hash)

    def load_generated_files(self, pdf_hash: str) -> Dict[str, str]:
        """Load previously cached generated files.

        Returns:
            Mapping of relative path → file content.
        """
        files_dir = self._artifact_dir(pdf_hash) / "files"
        files: Dict[str, str] = {}
        if files_dir.exists():
            for f in files_dir.rglob("*"):
                if f.is_file():
                    rel = str(f.relative_to(files_dir))
                    files[rel] = f.read_text()
        return files

    # ──────────────────────────────────────────────────────────────────
    # Metadata (JSON)
    # ──────────────────────────────────────────────────────────────────

    def save_metadata(self, pdf_hash: str, metadata: dict) -> None:
        """Persist JSON metadata alongside cached artifacts."""
        path = self._artifact_dir(pdf_hash) / "metadata.json"
        with open(path, "w") as f:
            json.dump(metadata, f, indent=2, default=str)

    def load_metadata(self, pdf_hash: str) -> dict:
        """Load JSON metadata for *pdf_hash* (empty dict if absent)."""
        path = self._artifact_dir(pdf_hash) / "metadata.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return {}

    # ──────────────────────────────────────────────────────────────────
    # Arbitrary stage cache
    # ──────────────────────────────────────────────────────────────────

    def has_stage(self, pdf_hash: str, stage_name: str) -> bool:
        """Return ``True`` if a cached result exists for the named stage."""
        return (self._artifact_dir(pdf_hash) / f"{stage_name}.pkl").exists()

    def save_stage(self, pdf_hash: str, stage_name: str, data: Any) -> None:
        """Cache an arbitrary pipeline stage result."""
        path = self._artifact_dir(pdf_hash) / f"{stage_name}.pkl"
        with open(path, "wb") as f:
            pickle.dump(data, f)

    def load_stage(self, pdf_hash: str, stage_name: str) -> Any:
        """Load a previously cached pipeline stage result."""
        path = self._artifact_dir(pdf_hash) / f"{stage_name}.pkl"
        with open(path, "rb") as f:
            return pickle.load(f)  # noqa: S301

    # ──────────────────────────────────────────────────────────────────
    # Cache management
    # ──────────────────────────────────────────────────────────────────

    def list_cached(self) -> list[str]:
        """Return a list of all cached pdf_hash keys."""
        if not self.cache_dir.exists():
            return []
        return [
            d.name
            for d in self.cache_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]

    def clear(self) -> None:
        """Remove all cached data."""
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Cache cleared")

    def clear_hash(self, pdf_hash: str) -> None:
        """Remove cached data for a specific pdf_hash."""
        d = self.cache_dir / pdf_hash
        if d.exists():
            shutil.rmtree(d)
            logger.info("Cleared cache for %s", pdf_hash)
