# Testing

The FastMCP integration is checked in four layers: unit tests, the existing
REST/worker smoke test, an in-memory MCP call, and real stdio/HTTP transports.

## Setup

```powershell
Copy-Item .env.example .env
python -m pip install -e ".[dev]"
docker compose up --build -d
```

Compose starts PostgreSQL, Redis, the migrated database, the API, and the arq
worker. The local editable installation is only needed for running pytest and
the diagnostic scripts from the host.

## 1. Unit tests

```powershell
python -m pytest -q
```

The MCP-specific suite verifies the exact tool catalog, actual schemas through
`fastmcp.Client`, cross-field validation, serializers, response caps,
conditional routing visibility and the committed reference snapshot. Queue
lifecycle tests also verify commit-before-enqueue ordering, generic worker
registration, enqueue failures, persisted result restoration, MCP timeout and
cancellation behavior, closed DB sessions during worker waits, and hidden
FastMCP `Context` injection.

Inspect and persist the actual schemas with:

```powershell
python scripts/dump_mcp_schemas.py
```

The script writes `artifacts/mcp_schemas.json` and fails when a public property
has no description.

## 2. REST and worker regression

The Compose stack already runs the API and worker. Confirm they are healthy:

```powershell
docker compose ps --all
```

Run the existing smoke test:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke_test.ps1
```

## 3. MCP calls

All MCP checks require PostgreSQL, Redis and the arq worker. The HTTP check also
requires Uvicorn on port 8011. In-memory and stdio start their own FastMCP
server lifespans and Redis pools, but application commands still execute only
in the external worker.

The stdio entrypoint always disables SQLAlchemy query echo because stdout is
reserved exclusively for MCP JSON-RPC messages. Other logs must use stderr.

```powershell
python scripts/test_mcp_inmemory.py
python scripts/test_mcp_stdio.py
python scripts/test_mcp_http.py
```

An alternative query can be supplied as the positional argument:

```powershell
python scripts/test_mcp_http.py "Апрелевка"
```

Each script verifies `ping`, the version 2 agent catalog, discovery tools and
their MCP envelopes. The scripts print `job_id` values for diagnostics.

Routing unit tests use `httpx.MockTransport`, injected clients and
`AsyncMock`; they do not access Transitous or OpenRouteService over the network.
Optional live provider checks are separate:

```powershell
python scripts/test_routing_live.py
```

The script requires a Transitous User-Agent containing application name,
version and contact. OpenRouteService cases are skipped with a clear message
when `OPENROUTESERVICE_API_KEY` is empty. Live checks are never part of normal
`pytest`.

## 4. Persisted diagnostics

Use the printed MCP `job_id` while the FastAPI application is running:

```powershell
curl.exe "http://127.0.0.1:8011/api/v1/jobs/<job_id>"
curl.exe "http://127.0.0.1:8011/api/v1/jobs/<job_id>/events"
curl.exe "http://127.0.0.1:8011/api/v1/jobs/<job_id>/results"
curl.exe "http://127.0.0.1:8011/api/v1/jobs/<job_id>/upstream-calls"
```

A cached geo result legitimately has no new upstream-call entry.
