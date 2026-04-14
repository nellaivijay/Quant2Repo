"""Gateway adapter — enables Quant2Repo to run in dual mode.

When the ``JOB_ID`` environment variable is set, the engine runs in
**gateway mode**: it reads job parameters from env vars, executes the
pipeline, writes a ``.any2repo_status.json`` status file, and optionally
POSTs results to a callback URL.

When ``JOB_ID`` is *not* set, the engine behaves exactly as before —
a standalone CLI tool driven by ``argparse``.

This module implements the Any2Repo Engine Protocol v1.0.
See: https://github.com/nellaivijay/Any2Repo-Gateway/blob/main/docs/engine_protocol.md
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("quant2repo.gateway")


# ── Detection ────────────────────────────────────────────────────────────


def is_gateway_mode() -> bool:
    """Return True if the engine was launched by Any2Repo-Gateway.

    Gateway mode is indicated by the presence of the ``JOB_ID``
    environment variable, which the gateway always injects.
    """
    return bool(os.environ.get("JOB_ID"))


# ── Status file ──────────────────────────────────────────────────────────


def write_status_file(
    output_dir: str,
    job_id: str,
    status: str,
    *,
    output_url: str = "",
    error: str = "",
    files_generated: int = 0,
    elapsed_seconds: float = 0.0,
    metadata: Optional[dict] = None,
) -> str:
    """Write ``.any2repo_status.json`` per the Engine Protocol spec.

    Args:
        output_dir: The directory where generated files were written.
        job_id: Unique job identifier (from ``JOB_ID`` env var).
        status: ``"completed"`` or ``"failed"``.
        output_url: URL to the generated output (optional).
        error: Error message (required when status is ``"failed"``).
        files_generated: Number of files produced.
        elapsed_seconds: Wall-clock execution time.
        metadata: Additional engine-specific metadata.

    Returns:
        Absolute path to the status file.
    """
    os.makedirs(output_dir, exist_ok=True)
    status_path = os.path.join(output_dir, ".any2repo_status.json")

    payload = {
        "job_id": job_id,
        "status": status,
        "engine_id": "quant2repo",
        "output_url": output_url,
        "error": error,
        "files_generated": files_generated,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata or {},
    }

    with open(status_path, "w") as f:
        json.dump(payload, f, indent=2)

    logger.info("Wrote status file: %s (status=%s)", status_path, status)
    return status_path


def post_callback(callback_url: str, payload: dict) -> bool:
    """POST job results to the gateway callback URL (best-effort).

    Returns True on success, False on failure (never raises).
    """
    if not callback_url:
        return False
    try:
        import requests
        resp = requests.post(callback_url, json=payload, timeout=30)
        resp.raise_for_status()
        logger.info("Callback POST to %s succeeded (HTTP %d)", callback_url, resp.status_code)
        return True
    except Exception as exc:
        logger.warning("Callback POST to %s failed: %s", callback_url, exc)
        return False


# ── Gateway entry point ──────────────────────────────────────────────────


def run_gateway_mode() -> None:
    """Execute Quant2Repo in gateway mode.

    Reads all parameters from environment variables:
        JOB_ID          — Unique job identifier (required)
        TENANT_ID       — Tenant who submitted the job
        PDF_URL         — URL of the research paper
        PDF_BASE64      — Base64-encoded PDF (alternative)
        PAPER_TEXT       — Raw paper text (alternative)
        CATALOG_ID      — Strategy from the built-in catalog
        OUTPUT_DIR      — Where to write generated files (default: /tmp/q2r-{JOB_ID})
        ENGINE_OPTIONS  — JSON string of additional options
        CALLBACK_URL    — URL to POST results to on completion
        Q2R_PROVIDER    — LLM provider override
        Q2R_MODEL       — Model name override

    The function:
    1. Parses env vars into pipeline arguments
    2. Runs the appropriate pipeline (classic or agent)
    3. Writes ``.any2repo_status.json``
    4. POSTs to ``CALLBACK_URL`` if set
    5. Exits with code 0 (success) or 1 (failure)
    """
    job_id = os.environ.get("JOB_ID", "")
    tenant_id = os.environ.get("TENANT_ID", "")
    pdf_url = os.environ.get("PDF_URL", "")
    pdf_base64 = os.environ.get("PDF_BASE64", "")
    paper_text = os.environ.get("PAPER_TEXT", "")
    catalog_id = os.environ.get("CATALOG_ID", "")
    output_dir = os.environ.get("OUTPUT_DIR", f"/tmp/q2r-{job_id}")
    callback_url = os.environ.get("CALLBACK_URL", "")
    options_json = os.environ.get("ENGINE_OPTIONS", "{}")

    logger.info(
        "Gateway mode: job_id=%s tenant_id=%s catalog_id=%s pdf_url=%s output_dir=%s",
        job_id, tenant_id, catalog_id or "(none)",
        pdf_url[:80] if pdf_url else "(none)", output_dir,
    )

    # Parse engine options
    try:
        options = json.loads(options_json) if options_json else {}
    except json.JSONDecodeError:
        options = {}

    mode = options.get("mode", "classic")
    provider_name = os.environ.get("Q2R_PROVIDER") or options.get("provider")
    model_name = os.environ.get("Q2R_MODEL") or options.get("model")

    # Handle base64 PDF input
    pdf_path = ""
    if pdf_base64 and not pdf_url:
        import base64
        pdf_path = os.path.join(output_dir, "input_paper.pdf")
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
        with open(pdf_path, "wb") as f:
            f.write(base64.b64decode(pdf_base64))
        logger.info("Decoded base64 PDF to %s", pdf_path)

    # Resolve catalog entry to PDF URL if needed
    if catalog_id and not pdf_url and not pdf_path:
        try:
            from quant.catalog import get_strategy
            entry = get_strategy(catalog_id)
            if entry and entry.paper_url:
                pdf_url = entry.paper_url
                logger.info("Resolved catalog '%s' to PDF: %s", catalog_id, pdf_url)
        except Exception as exc:
            logger.warning("Catalog lookup failed for '%s': %s", catalog_id, exc)

    start_time = time.time()
    files_generated = 0

    try:
        if mode == "agent":
            from main import run_agent
            run_agent(
                pdf_url=pdf_url,
                pdf_path=pdf_path,
                output_dir=output_dir,
                provider_name=provider_name,
                model_name=model_name,
                refine=options.get("refine", False),
                execute=options.get("execute", False),
                evaluate=options.get("evaluate", False),
                code_rag=options.get("code_rag", False),
                verbose=options.get("verbose", False),
                catalog_id=catalog_id,
            )
        else:
            from main import run_classic
            run_classic(
                pdf_url=pdf_url,
                pdf_path=pdf_path,
                output_dir=output_dir,
                provider_name=provider_name,
                model_name=model_name,
                skip_validation=options.get("skip_validation", False),
                skip_tests=options.get("skip_tests", False),
                verbose=options.get("verbose", False),
                catalog_id=catalog_id,
            )

        # Count generated files
        files_generated = sum(
            1 for _ in Path(output_dir).rglob("*") if _.is_file()
            and _.name != ".any2repo_status.json"
        )

        elapsed = time.time() - start_time
        logger.info("Pipeline completed: %d files in %.1fs", files_generated, elapsed)

        status_path = write_status_file(
            output_dir=output_dir,
            job_id=job_id,
            status="completed",
            files_generated=files_generated,
            elapsed_seconds=elapsed,
            metadata={
                "tenant_id": tenant_id,
                "mode": mode,
                "catalog_id": catalog_id,
                "provider": provider_name or "auto",
            },
        )

        # Callback
        if callback_url:
            with open(status_path) as f:
                post_callback(callback_url, json.load(f))

        sys.exit(0)

    except Exception as exc:
        elapsed = time.time() - start_time
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.error("Pipeline failed: %s", error_msg, exc_info=True)

        status_path = write_status_file(
            output_dir=output_dir,
            job_id=job_id,
            status="failed",
            error=error_msg,
            files_generated=files_generated,
            elapsed_seconds=elapsed,
            metadata={
                "tenant_id": tenant_id,
                "mode": mode,
                "catalog_id": catalog_id,
                "provider": provider_name or "auto",
            },
        )

        if callback_url:
            with open(status_path) as f:
                post_callback(callback_url, json.load(f))

        sys.exit(1)
