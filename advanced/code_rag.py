"""GitHub reference code mining for backtests (CodeRAG).

Searches GitHub for reference backtest implementations related to the
strategy being generated, downloads relevant source files, scores their
relevance with an LLM, and provides reference context to the code
generator for improved output quality.

Workflow:

1. **Search** — build GitHub search queries from the strategy extraction
   (e.g. ``"momentum backtest pandas"``).
2. **Download** — clone or fetch raw files from the most-starred repos.
3. **Index** — build a :class:`CodeRAGIndex` mapping each reference file
   to the target plan files it is most relevant to.
4. **Retrieve** — during generation, call :meth:`get_reference_context`
   to inject the most relevant reference snippets into the prompt.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────

@dataclass
class ReferenceFile:
    """A single source file fetched from a GitHub repository.

    Attributes:
        repo: Repository slug (``owner/name``).
        path: File path within the repository.
        content: Full source content (truncated if very large).
        stars: Star count of the repository (used as a quality proxy).
        language: Programming language (should be Python).
        url: Permanent URL to the file on GitHub.
    """

    repo: str = ""
    path: str = ""
    content: str = ""
    stars: int = 0
    language: str = "Python"
    url: str = ""


@dataclass
class FileMapping:
    """Maps a target plan file to its most relevant reference files.

    Attributes:
        target_path: Path of the file being generated (e.g. ``signals.py``).
        references: Scored list of ``(ReferenceFile, relevance_score)`` pairs,
            sorted from most to least relevant.
    """

    target_path: str = ""
    references: List[Tuple[ReferenceFile, float]] = field(default_factory=list)

    @property
    def best(self) -> Optional[ReferenceFile]:
        """Return the single highest-scored reference, or ``None``."""
        if self.references:
            return self.references[0][0]
        return None

    def top_k(self, k: int = 3) -> List[ReferenceFile]:
        """Return the *k* most relevant reference files."""
        return [ref for ref, _ in self.references[:k]]


@dataclass
class CodeRAGIndex:
    """Complete index mapping every target file to reference code.

    Attributes:
        mappings: Per-target-file mappings.
        reference_files: Flat list of all downloaded reference files.
        repos_searched: Repository slugs that were searched.
        search_queries: Queries that were issued to GitHub.
    """

    mappings: Dict[str, FileMapping] = field(default_factory=dict)
    reference_files: List[ReferenceFile] = field(default_factory=list)
    repos_searched: List[str] = field(default_factory=list)
    search_queries: List[str] = field(default_factory=list)

    def get_mapping(self, target_path: str) -> Optional[FileMapping]:
        """Return the :class:`FileMapping` for *target_path*, if any."""
        return self.mappings.get(target_path)


# ──────────────────────────────────────────────────────────────────────
# CodeRAG engine
# ──────────────────────────────────────────────────────────────────────

class CodeRAG:
    """GitHub reference code mining engine.

    Parameters:
        provider: LLM provider for relevance scoring.
        config: Optional :class:`Q2RConfig`.
        github_token: Personal access token for GitHub API (optional but
            recommended to avoid rate-limiting).
        max_repos: Maximum number of repos to fetch.
        max_files_per_repo: Maximum Python files to download per repo.
    """

    _GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
    _GITHUB_CONTENTS_URL = "https://api.github.com/repos/{repo}/contents/{path}"
    _GITHUB_RAW_URL = "https://raw.githubusercontent.com/{repo}/HEAD/{path}"

    def __init__(
        self,
        provider: Any,
        config: Optional[Any] = None,
        github_token: Optional[str] = None,
        max_repos: int = 3,
        max_files_per_repo: int = 20,
    ) -> None:
        self.provider = provider
        self.config = config
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN", "")
        self.max_repos = max_repos
        self.max_files_per_repo = max_files_per_repo

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def build_index(
        self,
        strategy_extraction: dict,
        plan: Any,
    ) -> CodeRAGIndex:
        """Search GitHub, download files, and build the relevance index.

        Args:
            strategy_extraction: Extracted strategy details.
            plan: Architecture plan with ``.files`` list.

        Returns:
            A populated :class:`CodeRAGIndex`.
        """
        index = CodeRAGIndex()

        # Step 1: Build search queries
        queries = self._build_queries(strategy_extraction)
        index.search_queries = queries

        # Step 2: Search repositories
        repos = self._search_repos(queries)
        index.repos_searched = [r["full_name"] for r in repos]

        # Step 3: Download reference files
        for repo_info in repos[: self.max_repos]:
            try:
                files = self._download_repo_files(repo_info)
                index.reference_files.extend(files)
            except Exception as e:
                logger.warning(
                    "Failed to download from %s: %s",
                    repo_info.get("full_name", "?"),
                    e,
                )

        if not index.reference_files:
            logger.info("No reference files found on GitHub")
            return index

        # Step 4: Score relevance for each target file
        target_files = self._get_target_files(plan)
        for target_path in target_files:
            mapping = self._score_references(
                target_path, index.reference_files
            )
            index.mappings[target_path] = mapping

        logger.info(
            "CodeRAG index built: %d reference files across %d repos",
            len(index.reference_files),
            len(index.repos_searched),
        )
        return index

    def get_reference_context(
        self,
        target_file: str,
        index: CodeRAGIndex,
        max_tokens: int = 4000,
    ) -> str:
        """Return reference code context for a target file.

        Args:
            target_file: Path of the file being generated.
            index: A previously built :class:`CodeRAGIndex`.
            max_tokens: Approximate character budget for context.

        Returns:
            A formatted string of reference code snippets.
        """
        mapping = index.get_mapping(target_file)
        if not mapping or not mapping.references:
            return ""

        parts: List[str] = []
        char_budget = max_tokens * 4  # rough chars-per-token
        used = 0

        for ref, score in mapping.references:
            snippet = ref.content[:3000]
            header = (
                f"# Reference: {ref.repo}/{ref.path} "
                f"(relevance={score:.2f}, stars={ref.stars})"
            )
            block = f"{header}\n{snippet}\n"
            if used + len(block) > char_budget:
                break
            parts.append(block)
            used += len(block)

        return "\n".join(parts)

    # ──────────────────────────────────────────────────────────────────
    # Query building
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_queries(strategy_extraction: dict) -> List[str]:
        """Construct GitHub search queries from the strategy extraction."""
        queries: List[str] = []

        # Base terms
        signal_types = strategy_extraction.get("signal_types", [])
        if not signal_types:
            signals = strategy_extraction.get("signals", [])
            signal_types = [
                s.get("signal_type", "") if isinstance(s, dict) else ""
                for s in signals
            ]
        signal_types = [s for s in signal_types if s]

        asset_classes = strategy_extraction.get("asset_classes", ["equities"])
        strategy_name = strategy_extraction.get("strategy_name", "")

        # Primary query: signal type + backtest
        for st in signal_types[:3]:
            queries.append(f"{st} backtest python pandas")

        # Secondary: strategy name
        if strategy_name:
            safe_name = re.sub(r"[^a-zA-Z0-9 ]", "", strategy_name)
            queries.append(f"{safe_name} python backtest")

        # Tertiary: asset class + factor
        for ac in asset_classes[:2]:
            queries.append(f"{ac} factor model python")

        # Fallback
        if not queries:
            queries = ["quantitative trading backtest python"]

        return queries[:5]

    # ──────────────────────────────────────────────────────────────────
    # GitHub API
    # ──────────────────────────────────────────────────────────────────

    def _github_headers(self) -> Dict[str, str]:
        """Return headers for GitHub API requests."""
        headers: Dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    def _search_repos(self, queries: List[str]) -> List[dict]:
        """Search GitHub for relevant repositories.

        Returns a deduplicated list of repo dicts sorted by stars.
        """
        try:
            import requests
        except ImportError:
            logger.warning("requests not installed — skipping GitHub search")
            return []

        seen: set = set()
        repos: List[dict] = []

        for query in queries:
            try:
                resp = requests.get(
                    self._GITHUB_SEARCH_URL,
                    params={
                        "q": f"{query} language:python",
                        "sort": "stars",
                        "order": "desc",
                        "per_page": 5,
                    },
                    headers=self._github_headers(),
                    timeout=15,
                )
                if resp.status_code != 200:
                    logger.debug(
                        "GitHub search returned %d for query '%s'",
                        resp.status_code,
                        query,
                    )
                    continue

                for item in resp.json().get("items", []):
                    slug = item.get("full_name", "")
                    if slug not in seen:
                        seen.add(slug)
                        repos.append(item)
            except Exception as e:
                logger.debug("GitHub search failed for '%s': %s", query, e)

        # Sort by stars descending
        repos.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)
        return repos[: self.max_repos * 2]  # extra buffer for download failures

    def _download_repo_files(self, repo_info: dict) -> List[ReferenceFile]:
        """Download Python files from a GitHub repository."""
        try:
            import requests
        except ImportError:
            return []

        slug = repo_info.get("full_name", "")
        stars = repo_info.get("stargazers_count", 0)
        default_branch = repo_info.get("default_branch", "main")

        # Use the GitHub tree API for efficiency
        tree_url = (
            f"https://api.github.com/repos/{slug}"
            f"/git/trees/{default_branch}?recursive=1"
        )

        try:
            resp = requests.get(
                tree_url,
                headers=self._github_headers(),
                timeout=15,
            )
            if resp.status_code != 200:
                return []

            tree = resp.json().get("tree", [])
        except Exception as e:
            logger.debug("Failed to fetch tree for %s: %s", slug, e)
            return []

        # Filter for Python files, skip tests/docs/setup
        python_files = [
            item
            for item in tree
            if (
                item.get("path", "").endswith(".py")
                and item.get("type") == "blob"
                and not any(
                    skip in item["path"].lower()
                    for skip in ("test", "setup.py", "conftest", "__pycache__", "docs/")
                )
            )
        ]

        # Prefer smaller files (more likely to be focused modules)
        python_files.sort(key=lambda f: f.get("size", 0))
        python_files = python_files[: self.max_files_per_repo]

        results: List[ReferenceFile] = []
        for file_info in python_files:
            path = file_info["path"]
            raw_url = f"https://raw.githubusercontent.com/{slug}/{default_branch}/{path}"
            try:
                content_resp = requests.get(raw_url, timeout=10)
                if content_resp.status_code == 200:
                    content = content_resp.text[:10000]  # cap size
                    results.append(ReferenceFile(
                        repo=slug,
                        path=path,
                        content=content,
                        stars=stars,
                        url=f"https://github.com/{slug}/blob/{default_branch}/{path}",
                    ))
            except Exception:
                continue

        return results

    # ──────────────────────────────────────────────────────────────────
    # Relevance scoring
    # ──────────────────────────────────────────────────────────────────

    def _score_references(
        self,
        target_path: str,
        reference_files: List[ReferenceFile],
    ) -> FileMapping:
        """Score each reference file's relevance to *target_path*.

        Uses a combination of keyword heuristics and (optionally) LLM
        scoring for the top candidates.
        """
        mapping = FileMapping(target_path=target_path)

        # Stage 1: Fast keyword-based pre-filtering
        scored: List[Tuple[ReferenceFile, float]] = []
        target_keywords = self._extract_keywords(target_path)

        for ref in reference_files:
            score = self._keyword_score(target_keywords, ref)
            scored.append((ref, score))

        # Sort by keyword score, take top candidates for LLM scoring
        scored.sort(key=lambda x: x[1], reverse=True)
        top_candidates = scored[:8]

        # Stage 2: LLM-based relevance scoring for top candidates
        if top_candidates:
            try:
                llm_scored = self._llm_score(target_path, top_candidates)
                mapping.references = llm_scored
            except Exception as e:
                logger.debug("LLM scoring failed, using keyword scores: %s", e)
                mapping.references = top_candidates[:5]
        else:
            mapping.references = []

        return mapping

    @staticmethod
    def _extract_keywords(path: str) -> List[str]:
        """Extract search keywords from a file path."""
        base = os.path.splitext(os.path.basename(path))[0]
        # Split on underscores and common separators
        parts = re.split(r"[_\-.]", base.lower())
        # Add semantic expansions
        expansions: Dict[str, List[str]] = {
            "signal": ["signal", "factor", "alpha", "indicator"],
            "portfolio": ["portfolio", "position", "weight", "allocation"],
            "data": ["data", "loader", "fetch", "download", "source"],
            "analysis": ["analysis", "metric", "performance", "evaluation"],
            "config": ["config", "parameter", "setting"],
            "main": ["main", "run", "backtest", "pipeline"],
            "visualization": ["plot", "chart", "report", "visual"],
        }
        keywords = list(parts)
        for part in parts:
            if part in expansions:
                keywords.extend(expansions[part])
        return list(set(keywords))

    @staticmethod
    def _keyword_score(
        target_keywords: List[str], ref: ReferenceFile
    ) -> float:
        """Fast keyword-overlap relevance score (0-1)."""
        ref_text = (ref.path + " " + ref.content[:500]).lower()
        if not target_keywords:
            return 0.0
        hits = sum(1 for kw in target_keywords if kw in ref_text)
        score = hits / len(target_keywords)

        # Boost for star count (log scale)
        import math
        star_boost = min(0.2, math.log1p(ref.stars) / 50)
        return min(1.0, score + star_boost)

    def _llm_score(
        self,
        target_path: str,
        candidates: List[Tuple[ReferenceFile, float]],
    ) -> List[Tuple[ReferenceFile, float]]:
        """Use LLM to refine relevance scores for top candidates."""
        refs_text = ""
        for i, (ref, _) in enumerate(candidates):
            refs_text += (
                f"\n[{i}] {ref.repo}/{ref.path} ({ref.stars} stars)\n"
                f"{ref.content[:500]}\n"
            )

        prompt = f"""Score the relevance (0.0-1.0) of each reference file
to the target file "{target_path}" in a quantitative trading backtest.

Reference files:
{refs_text}

Return JSON: {{"scores": [0.8, 0.3, ...]}} (one float per reference, same order)"""

        from providers.base import GenerationConfig

        config = GenerationConfig(
            temperature=0.0,
            max_output_tokens=512,
            response_format="json",
        )
        result = self.provider.generate(prompt, config=config)
        data = self._extract_json(result.text)
        llm_scores = data.get("scores", [])

        scored: List[Tuple[ReferenceFile, float]] = []
        for i, (ref, kw_score) in enumerate(candidates):
            llm_score = llm_scores[i] if i < len(llm_scores) else 0.0
            # Blend keyword and LLM scores
            combined = 0.4 * kw_score + 0.6 * float(llm_score)
            scored.append((ref, round(combined, 3)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:5]

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _get_target_files(plan: Any) -> List[str]:
        """Extract target file paths from an architecture plan."""
        if hasattr(plan, "files"):
            return [
                f.get("path", "") if isinstance(f, dict) else str(f)
                for f in plan.files
                if (f.get("path", "") if isinstance(f, dict) else str(f)).endswith(".py")
            ]
        return []

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
        return {}
