# Quant2Repo Gateway Integration Guide

Quant2Repo is a multi-model agentic framework that converts quantitative finance
research papers into production-ready backtesting repositories. It supports 47
strategies from the awesome-systematic-trading catalog. This document describes
how Quant2Repo operates in **dual-mode**: as a standalone CLI and as a
gateway-managed engine behind [Any2Repo-Gateway](https://github.com/nellaivijay/Any2Repo-Gateway).

---

## Table of Contents

1. [Overview](#1-overview)
2. [Dual-Mode Architecture](#2-dual-mode-architecture)
3. [gateway_adapter.py Components](#3-gateway_adapterpy-components)
4. [Environment Variable Contract](#4-environment-variable-contract)
5. [End-to-End Flow](#5-end-to-end-flow)
6. [Catalog Resolution Flow](#6-catalog-resolution-flow)
7. [Status File Protocol](#7-status-file-protocol)
8. [Engine Manifest](#8-engine-manifest)
9. [Worked Examples](#9-worked-examples)
10. [Docker Deployment](#10-docker-deployment)
11. [Links](#11-links)

---

## 1. Overview

Quant2Repo supports two deployment modes:

| Mode | Entry Point | Orchestration |
|---|---|---|
| **Standalone CLI** | `python main.py --pdf_url ...` or `python main.py --catalog time-series-momentum` | User invokes directly via argparse flags |
| **Gateway-Managed Engine** | `python main.py` (env vars set by gateway) | Any2Repo-Gateway dispatches jobs, reads results via status file and callback |

In standalone mode, the operator controls every parameter through CLI arguments.
In gateway mode, the gateway container launcher sets environment variables before
invoking `main.py`; the adapter layer reads those variables, resolves any catalog
references, runs the pipeline, and reports results back — all without modifying
the core CLI code.

A key differentiator from Research2Repo: Quant2Repo accepts a **`CATALOG_ID`**
environment variable (or `--catalog` CLI flag) that resolves strategy catalog
entries to paper URLs via the built-in `quant.catalog` module. This enables
users to reference strategies by name (e.g., `time-series-momentum`) rather than
requiring a direct paper URL.

---

## 2. Dual-Mode Architecture

The following diagram shows the decision tree inside `main.py` at startup:

```
main.py
  |
  +-- is_gateway_mode()?
  |     |
  |     Yes --> run_gateway_mode()
  |     |       Read env vars (JOB_ID, PDF_URL, CATALOG_ID, ...)
  |     |       Resolve CATALOG_ID to PDF URL if needed
  |     |       Parse ENGINE_OPTIONS JSON
  |     |       Call run_classic() or run_agent()
  |     |       Write .any2repo_status.json
  |     |       POST to CALLBACK_URL
  |     |       sys.exit(0 or 1)
  |     |
  |     No --> Standard CLI (argparse)
  |             Parse --pdf_url / --catalog / --mode / ...
  |             Call run_classic() or run_agent()
  |             Print summary to stdout
  |             sys.exit(0 or 1)
```

### Design Principles

- **Zero-intrusion design.** `gateway_adapter.py` is a self-contained module
  that reads environment variables and translates them into the same function
  calls the CLI uses. No existing CLI code is modified, patched, or
  monkey-patched.

- **Shared pipeline functions.** Both modes invoke the same `run_classic()` and
  `run_agent()` entry points. The gateway adapter simply constructs the
  arguments programmatically instead of parsing them from `sys.argv`.

- **CATALOG_ID resolution.** When `CATALOG_ID` is set (and `PDF_URL` is not),
  the adapter calls `quant.catalog.get_strategy(catalog_id)` to obtain the
  corresponding `StrategyEntry`, extracts its `paper_url`, and feeds that URL
  into the pipeline. This makes the gateway a first-class interface for the
  47-strategy catalog.

---

## 3. gateway_adapter.py Components

The gateway adapter module exposes four public functions:

### `is_gateway_mode() -> bool`

Checks whether the `JOB_ID` environment variable is set. If present, the
process is running under gateway orchestration.

```python
def is_gateway_mode() -> bool:
    return bool(os.environ.get("JOB_ID"))
```

### `write_status_file(output_dir, status_dict) -> Path`

Writes `.any2repo_status.json` to the output directory. The gateway reads this
file after the engine process exits to determine success/failure and collect
metadata.

- Atomic write via `tempfile` + `os.rename` to prevent partial reads.
- Returns the `Path` to the written file.

### `post_callback(callback_url, payload) -> None`

Best-effort HTTP POST to the gateway's callback endpoint. Failures are logged
but do not cause the engine to exit with an error — the gateway can always fall
back to reading the status file.

- Timeout: 10 seconds.
- Retries: 2 attempts with exponential backoff.
- Payload: JSON-serialized status dict (same content as the status file).

### `run_gateway_mode() -> None`

Top-level orchestration function. Execution flow:

1. Read `JOB_ID`, `TENANT_ID`, `PDF_URL`, `PDF_BASE64`, `PAPER_TEXT`,
   `CATALOG_ID`, `OUTPUT_DIR`, `ENGINE_OPTIONS`, `CALLBACK_URL`,
   `Q2R_PROVIDER`, `Q2R_MODEL` from the environment.
2. Validate that at least one input source is present (`PDF_URL`, `PDF_BASE64`,
   `PAPER_TEXT`, or `CATALOG_ID`).
3. If `CATALOG_ID` is set and no direct PDF input is provided, resolve it
   via `quant.catalog.get_strategy()`.
4. Parse `ENGINE_OPTIONS` JSON (default: `{}`).
5. Determine mode (`classic` or `agent`) from options.
6. Invoke `run_classic()` or `run_agent()` with resolved parameters.
7. Build status dict, call `write_status_file()`.
8. If `CALLBACK_URL` is set, call `post_callback()`.
9. `sys.exit(0)` on success, `sys.exit(1)` on failure.

---

## 4. Environment Variable Contract

All configuration in gateway mode is supplied through environment variables.
The gateway container launcher is responsible for setting these before invoking
`python main.py`.

| Variable | Required | Description |
|---|---|---|
| `JOB_ID` | **Yes** | Unique job identifier. Presence of this variable triggers gateway mode. |
| `TENANT_ID` | No | Identifier for the tenant who submitted the job. Included in status metadata. |
| `PDF_URL` | One of these | URL of the research paper PDF to process. |
| `PDF_BASE64` | four inputs | Base64-encoded PDF content (for air-gapped environments). |
| `PAPER_TEXT` | is required | Raw extracted text of the paper (skips PDF parsing). |
| `CATALOG_ID` | | Strategy ID from the built-in 47-strategy catalog (e.g., `time-series-momentum`). |
| `OUTPUT_DIR` | No | Directory for generated repository output. Default: `/tmp/q2r-{JOB_ID}`. |
| `ENGINE_OPTIONS` | No | JSON string with engine configuration. Example: `{"mode":"agent","refine":true}`. |
| `CALLBACK_URL` | No | URL to POST results to after job completion. |
| `Q2R_PROVIDER` | No | Override the default LLM provider (e.g., `gemini`, `openai`, `anthropic`). |
| `Q2R_MODEL` | No | Override the default model name (e.g., `gemini-2.5-pro`). |

### Input Priority

When multiple input sources are provided, the adapter applies the following
priority order:

```
PDF_URL  >  PDF_BASE64  >  PAPER_TEXT  >  CATALOG_ID
```

If `CATALOG_ID` is the only input supplied, the adapter resolves it to a
`PDF_URL` before invoking the pipeline. If `PDF_URL` is already present,
`CATALOG_ID` is recorded in metadata but not used for resolution.

---

## 5. End-to-End Flow

The following sequence diagram shows a complete gateway-managed job lifecycle,
from API call to result retrieval:

```
Client              Gateway              Engine (Q2R)           LLM Provider
  |                    |                      |                      |
  |  POST /api/v1/jobs |                      |                      |
  |  {engine: q2r,     |                      |                      |
  |   catalog_id: ...} |                      |                      |
  |------------------->|                      |                      |
  |                    |                      |                      |
  |  201 {job_id: abc} |                      |                      |
  |<-------------------|                      |                      |
  |                    |                      |                      |
  |                    |  Launch container     |                      |
  |                    |  Set env: JOB_ID,     |                      |
  |                    |  CATALOG_ID, etc.     |                      |
  |                    |--------------------->|                      |
  |                    |                      |                      |
  |                    |                      |  Resolve CATALOG_ID   |
  |                    |                      |  via quant.catalog    |
  |                    |                      |--------+             |
  |                    |                      |        |             |
  |                    |                      |<-------+             |
  |                    |                      |  pdf_url resolved    |
  |                    |                      |                      |
  |                    |                      |  Parse paper         |
  |                    |                      |--------+             |
  |                    |                      |        |             |
  |                    |                      |<-------+             |
  |                    |                      |                      |
  |                    |                      |  Generate code       |
  |                    |                      |--------------------->|
  |                    |                      |  LLM completions     |
  |                    |                      |<---------------------|
  |                    |                      |                      |
  |                    |                      |  Refine & validate   |
  |                    |                      |--------------------->|
  |                    |                      |  LLM completions     |
  |                    |                      |<---------------------|
  |                    |                      |                      |
  |                    |                      |  Write output files  |
  |                    |                      |--------+             |
  |                    |                      |        |             |
  |                    |                      |<-------+             |
  |                    |                      |                      |
  |                    |                      |  Write status file   |
  |                    |                      |  POST callback       |
  |                    |                      |--------+             |
  |                    |                      |        |             |
  |                    |  Callback POST       |<-------+             |
  |                    |<---------------------|                      |
  |                    |                      |                      |
  |                    |  Container exits 0   |                      |
  |                    |<---------------------|                      |
  |                    |                      |                      |
  |  GET /api/v1/jobs/ |                      |                      |
  |       abc/status   |                      |                      |
  |------------------->|                      |                      |
  |                    |                      |                      |
  |  200 {status:      |                      |                      |
  |   completed, ...}  |                      |                      |
  |<-------------------|                      |                      |
  |                    |                      |                      |
  |  GET /api/v1/jobs/ |                      |                      |
  |     abc/artifacts  |                      |                      |
  |------------------->|                      |                      |
  |                    |                      |                      |
  |  200 (tar.gz)      |                      |                      |
  |<-------------------|                      |                      |
```

### Flow Steps

1. **Client** submits a job request to the gateway REST API.
2. **Gateway** validates the request, assigns a `JOB_ID`, persists it, and
   returns `201 Created`.
3. **Gateway** launches the Q2R container (or process) with environment
   variables set per the contract in [Section 4](#4-environment-variable-contract).
4. **Engine** detects gateway mode (`JOB_ID` is set), resolves `CATALOG_ID` if
   needed, and runs the configured pipeline.
5. **Engine** writes `.any2repo_status.json` and POSTs to `CALLBACK_URL`.
6. **Engine** exits with code 0 (success) or 1 (failure).
7. **Gateway** reads the status file from the output volume and updates job
   state.
8. **Client** polls for status and downloads artifacts when ready.

---

## 6. Catalog Resolution Flow

When `CATALOG_ID` is the input source, the adapter resolves it to a paper URL
before the pipeline begins:

```
CATALOG_ID="time-series-momentum"
  |
  v
quant.catalog.get_strategy("time-series-momentum")
  |
  v
StrategyEntry {
  catalog_id: "time-series-momentum",
  title: "Time Series Momentum",
  paper_url: "https://papers.ssrn.com/...",
  category: "trend-following",
  tags: ["momentum", "futures", "cross-section"],
  ...
}
  |
  v
pdf_url = entry.paper_url
  |
  v
Pipeline runs with resolved pdf_url
```

### Resolution Rules

- If `CATALOG_ID` does not match any entry in the catalog, the adapter logs an
  error, writes a `failed` status file, and exits with code 1.
- If `CATALOG_ID` is set alongside `PDF_URL`, the `PDF_URL` takes precedence
  and the catalog entry is only used for metadata enrichment.
- The catalog currently contains **47 strategies** sourced from the
  awesome-systematic-trading collection.

### Catalog Lookup Internals

```
quant/
  catalog/
    __init__.py          # Exports get_strategy(), list_strategies()
    strategies.json      # 47 strategy entries
    models.py            # StrategyEntry dataclass
```

`get_strategy(catalog_id: str) -> StrategyEntry` performs a case-insensitive
lookup against `strategies.json` and returns the matching entry or raises
`CatalogEntryNotFound`.

---

## 7. Status File Protocol

On job completion (success or failure), the engine writes
`.any2repo_status.json` to the root of `OUTPUT_DIR`. The gateway reads this
file to determine job outcome and collect metadata.

### Schema

```json
{
  "job_id": "abc123",
  "status": "completed",
  "engine_id": "quant2repo",
  "files_generated": 15,
  "elapsed_seconds": 98.5,
  "completed_at": "2025-01-15T10:32:00Z",
  "metadata": {
    "tenant_id": "acme",
    "mode": "agent",
    "catalog_id": "time-series-momentum",
    "provider": "gemini"
  }
}
```

### Field Reference

| Field | Type | Description |
|---|---|---|
| `job_id` | string | Echo of the `JOB_ID` env var. |
| `status` | string | `"completed"` or `"failed"`. |
| `engine_id` | string | Always `"quant2repo"`. |
| `files_generated` | integer | Count of files written to `OUTPUT_DIR`. |
| `elapsed_seconds` | float | Wall-clock time for the pipeline run. |
| `completed_at` | string | ISO 8601 timestamp of completion. |
| `metadata` | object | Engine-specific metadata (see below). |

### Metadata Fields

| Field | Type | Description |
|---|---|---|
| `tenant_id` | string | Echo of `TENANT_ID` (may be `null`). |
| `mode` | string | Pipeline mode used: `"classic"` or `"agent"`. |
| `catalog_id` | string | Catalog strategy ID if used (may be `null`). |
| `provider` | string | LLM provider used for generation. |

### Failure Status

On failure, additional fields are included:

```json
{
  "job_id": "abc123",
  "status": "failed",
  "engine_id": "quant2repo",
  "files_generated": 0,
  "elapsed_seconds": 12.3,
  "completed_at": "2025-01-15T10:32:00Z",
  "error": "CatalogEntryNotFound: no strategy matching 'invalid-id'",
  "metadata": {
    "tenant_id": "acme",
    "mode": "agent",
    "catalog_id": "invalid-id",
    "provider": null
  }
}
```

---

## 8. Engine Manifest

The engine manifest declares Quant2Repo's capabilities to the gateway. It is
read during engine registration and used for request validation, routing, and
UI display.

```json
{
  "engine_id": "quant2repo",
  "version": "2.0.0",
  "display_name": "Quant2Repo",
  "description": "Convert quantitative finance papers into backtesting repositories",
  "protocol_version": "1.0",
  "capabilities": [
    "pdf_input",
    "text_input",
    "catalog_input",
    "github_output",
    "local_output"
  ],
  "accepted_inputs": [
    "pdf_url",
    "pdf_base64",
    "paper_text",
    "catalog_id"
  ],
  "container_image": "any2repo/quant2repo:latest",
  "supported_backends": [
    "gcp_vertex",
    "aws_bedrock",
    "azure_ml",
    "on_prem"
  ]
}
```

### Manifest Field Notes

- **`capabilities`**: The `catalog_input` capability is unique to Quant2Repo
  among Any2Repo engines. It signals that the engine can accept strategy
  identifiers from a built-in catalog.
- **`accepted_inputs`**: The gateway uses this list to validate job requests.
  A request with `catalog_id` will be rejected if routed to an engine that
  does not list it here.
- **`container_image`**: The default Docker image. The gateway operator can
  override this in the gateway configuration.
- **`supported_backends`**: Cloud and on-prem backends where this engine can
  be deployed. The gateway uses this for scheduling decisions.

---

## 9. Worked Examples

### Example 1: Standalone CLI with Catalog

Run the time-series-momentum strategy in agent mode with refinement and
execution directly from the command line:

```bash
python main.py \
  --catalog time-series-momentum \
  --mode agent \
  --refine \
  --execute
```

The CLI parses `--catalog`, calls `quant.catalog.get_strategy()` internally,
resolves the paper URL, and runs the full pipeline. Output is written to the
default output directory and a summary is printed to stdout.

### Example 2: Gateway Mode via Environment Variables

Simulate a gateway-dispatched job by setting the required environment variables
directly:

```bash
JOB_ID=test456 \
  TENANT_ID=acme \
  CATALOG_ID=time-series-momentum \
  OUTPUT_DIR=/tmp/q2r-output \
  ENGINE_OPTIONS='{"mode":"agent","refine":true}' \
  python main.py
```

The presence of `JOB_ID` triggers gateway mode. The adapter resolves
`CATALOG_ID` to a paper URL, parses `ENGINE_OPTIONS`, runs the agent pipeline
with refinement, writes `.any2repo_status.json` to `/tmp/q2r-output/`, and
exits with code 0 on success.

Verify the result:

```bash
cat /tmp/q2r-output/.any2repo_status.json | python -m json.tool
```

### Example 3: Full Gateway Flow via API

Submit a job through the Any2Repo-Gateway REST API:

```bash
curl -X POST http://gateway:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -H "X-Tenant-ID: default" \
  -d '{
    "engine": "quant2repo",
    "catalog_id": "time-series-momentum",
    "cloud_backend": "on_prem",
    "options": {
      "mode": "agent",
      "refine": true
    }
  }'
```

Response:

```json
{
  "job_id": "q2r-a1b2c3d4",
  "status": "queued",
  "engine": "quant2repo",
  "created_at": "2025-01-15T10:30:00Z"
}
```

Poll for completion:

```bash
curl http://gateway:8000/api/v1/jobs/q2r-a1b2c3d4/status \
  -H "X-API-Key: your-key"
```

Download artifacts:

```bash
curl -o output.tar.gz \
  http://gateway:8000/api/v1/jobs/q2r-a1b2c3d4/artifacts \
  -H "X-API-Key: your-key"
```

---

## 10. Docker Deployment

### Container Image

The gateway launches Quant2Repo as a container. The standard image is
`any2repo/quant2repo:latest`.

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["python", "main.py"]
```

### Gateway Container Launch

The gateway sets environment variables and mounts a shared volume for output:

```bash
docker run --rm \
  -e JOB_ID=abc123 \
  -e TENANT_ID=acme \
  -e CATALOG_ID=time-series-momentum \
  -e ENGINE_OPTIONS='{"mode":"agent","refine":true}' \
  -e CALLBACK_URL=http://gateway:8000/internal/callback \
  -e Q2R_PROVIDER=gemini \
  -v /data/jobs/abc123:/tmp/q2r-abc123 \
  any2repo/quant2repo:latest
```

### Volume Mounts

| Host Path | Container Path | Purpose |
|---|---|---|
| `/data/jobs/{JOB_ID}` | `/tmp/q2r-{JOB_ID}` | Output directory (status file + generated repo) |

### Resource Limits

Recommended resource limits for production deployments:

| Resource | Minimum | Recommended |
|---|---|---|
| CPU | 1 core | 2 cores |
| Memory | 2 GB | 4 GB |
| Disk | 1 GB | 5 GB |
| Timeout | 120s | 300s |

### Health and Lifecycle

- The container is **ephemeral**: one container per job, exits on completion.
- Exit code 0 indicates success; exit code 1 indicates failure.
- The gateway enforces a configurable timeout (default: 300s). If exceeded, the
  container is killed and the job is marked as `timed_out`.
- No health-check endpoint is required; the gateway monitors the container
  process directly.

### Network Requirements

The container requires outbound HTTPS access to:

- LLM provider APIs (OpenAI, Google AI, Anthropic, etc.)
- Paper source URLs (SSRN, arXiv, etc.) when using `PDF_URL` or `CATALOG_ID`
- `CALLBACK_URL` (internal gateway network, typically reachable via Docker
  network or service mesh)

---

## 11. Links

| Resource | URL |
|---|---|
| Any2Repo-Gateway | <https://github.com/nellaivijay/Any2Repo-Gateway> |
| Engine Protocol Specification | [docs/engine_protocol.md](engine_protocol.md) |
| Research2Repo | <https://github.com/nellaivijay/Research2Repo> |
| awesome-systematic-trading | <https://github.com/edarchimbaud/awesome-systematic-trading> |
