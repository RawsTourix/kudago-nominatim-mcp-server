# Testing

The FastMCP integration is checked in four layers: unit tests, the existing
REST/worker smoke test, an in-memory MCP call, and real stdio/HTTP transports.

## Setup

```powershell
Copy-Item .env.example .env
python -m pip install -e ".[dev]"
docker compose up -d
python -m alembic upgrade head
```

## 1. Unit tests

```powershell
python -m pytest -q
```

## 2. REST and worker regression

Start the API and worker in separate terminals:

```powershell
python -m uvicorn app.main:app --reload --port 8011
```

```powershell
arq app.workers.worker_settings.WorkerSettings
```

Run the existing smoke test:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke_test.ps1
```

## 3. MCP calls

The in-memory and stdio checks require PostgreSQL but do not require Uvicorn or
the ARQ worker. The HTTP check requires Uvicorn on port 8011.

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

Each script verifies `ping`, tool discovery, an inline `resolve_place` call,
and the returned MCP envelope. It prints the `job_id` for the diagnostics check.

## 4. Persisted diagnostics

Use the printed MCP `job_id` while the FastAPI application is running:

```powershell
curl.exe "http://127.0.0.1:8011/api/v1/jobs/<job_id>"
curl.exe "http://127.0.0.1:8011/api/v1/jobs/<job_id>/events"
curl.exe "http://127.0.0.1:8011/api/v1/jobs/<job_id>/results"
curl.exe "http://127.0.0.1:8011/api/v1/jobs/<job_id>/upstream-calls"
```

A cached geo result legitimately has no new upstream-call entry.
