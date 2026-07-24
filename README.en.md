<p align="center">
  <a href="./README.md">Русский</a> · <strong>English</strong>
</p>

# KudaGo Nominatim: FastAPI + FastMCP Service

An asynchronous service for searching KudaGo events, places, movies, movie
showings, city news, and editorial guides; resolving free-form locations with
Nominatim; and planning routes through Transitous and OpenRouteService.

One application layer is exposed through two interfaces:

- a REST API under `/api/v1`;
- an agent-facing FastMCP facade v2 over Streamable HTTP at `/mcp` and stdio.

> [!IMPORTANT]
> Queued REST commands and every MCP tool require a running arq worker. The API
> or MCP transport can accept a request without the worker, but cannot execute
> the application command.

> [!WARNING]
> Routing is not supported in every region. Every completed MCP routing result
> contains the `regional_coverage_varies` warning. A `no_route` result applies
> only to the requested points, time, and restrictions; it does not prove that
> no physical route or public transport exists.

## Contents

- [Capabilities](#capabilities)
- [Architecture](#architecture)
- [MCP tools](#mcp-tools)
- [Routing and coverage](#routing-and-coverage)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Connecting an MCP client](#connecting-an-mcp-client)
- [Configuration](#configuration)
- [REST API and job lifecycle](#rest-api-and-job-lifecycle)
- [Testing](#testing)
- [Project structure](#project-structure)
- [Documentation](#documentation)
- [Limitations and production readiness](#limitations-and-production-readiness)

## Capabilities

| Area | Capabilities | Source |
|---|---|---|
| Events and places | Search by city, free-form location, or coordinates; filter by date and category | KudaGo + Nominatim |
| Cinema | Movies and actual movie showings | KudaGo |
| City content | News and editorial guides | KudaGo |
| Geocoding | Coordinate candidates for cities, districts, addresses, and landmarks | Nominatim |
| Public transport | Routes, transfers, stops, and schedules where data is available | Transitous / MOTIS 2 |
| Walking, cycling, driving | Independent street routes | OpenRouteService |
| Diagnostics | Jobs, execution events, full results, and upstream-call logs | PostgreSQL |

Key properties:

- FastAPI with OpenAPI, Swagger UI, and ReDoc;
- FastMCP 3.x facade version 2 with described JSON Schemas;
- Streamable HTTP and stdio MCP transports;
- one shared `CommandExecutor` for REST and MCP;
- PostgreSQL, asynchronous SQLAlchemy, Redis, and arq;
- a geo cache for reusable Nominatim results;
- persisted `job_events`, `command_results`, and `upstream_calls`;
- compact agent-facing responses with explicit semantic flags;
- separate unit, integration, smoke, and opt-in live tests.

## Architecture

Queued REST commands and MCP tools use the same lifecycle:

```text
REST client ─┐
             ├→ JobDispatchService → PostgreSQL commit → Redis → arq worker
MCP client ──┘                                              │
                                                            ▼
                                                   CommandExecutor
                                                            │
                                                            ▼
                                             service → external provider
                                                            │
                                                            ▼
                                      result + events + upstream diagnostics

REST → immediately returns a queued response with job_id
MCP  → awaits the worker → loads persisted CommandOutput → serializes result
```

The job is committed to PostgreSQL before it is enqueued in Redis. The worker
receives only the `job_id`, loads the authoritative command and payload from
the database, executes the handler, and persists the outcome. An enqueue
failure marks the job as `failed` instead of leaving it queued indefinitely.

REST reference and object-detail GET requests execute directly and do not
create jobs. The MCP `get_details` tool, in contrast, uses the shared queued
lifecycle.

See [docs/architecture.md](docs/architecture.md).

## MCP tools

A fully configured server publishes 10 read-only tools. Eight are always
available; two routing tools are published only when their provider is
configured.

| MCP tool | Purpose | Application command | Publication |
|---|---|---|---|
| `resolve_location` | Resolve a free-form location into coordinate candidates | `geo.resolve` | Always |
| `find_events` | Find scheduled events in a calendar window | `events.search` | Always |
| `find_places` | Find venues and attractions | `places.search` | Always |
| `find_movies` | Find movies | `movies.search` | Always |
| `find_movie_showings` | Find actual movie showings | `movie_showings.search` | Always |
| `find_city_news` | Find city news | `news.search` | Always |
| `find_city_guides` | Find editorial city guides | `lists.search` | Always |
| `get_details` | Load the full record for a returned item | `object.detail` | Always |
| `plan_public_transport` | Plan a public-transport journey | `routing.transit.plan` | When `TRANSITOUS_USER_AGENT` is non-empty |
| `plan_street_route` | Plan a walking, cycling, or driving route | `routing.street.plan` | When `OPENROUTESERVICE_API_KEY` is non-empty |

Former MCP v1 names (`events`, `places`, `object`, `transit_route`,
`street_route`, and others) are not aliases.

All tools are declared read-only, non-destructive, and idempotent. Public
schemas include descriptions, enums, numeric limits, and cross-field
validation. Invalid arguments are rejected before a job is created.

Agent-facing results use explicit semantics:

- `schedule_verified=true` denotes a confirmed event or movie-showing
  schedule;
- `showing_times_verified=false` on a movie reminds the agent to use
  `find_movie_showings` for actual times;
- `route_verified=true` is set only when `result_status=ok` and a complete
  route remains in the MCP response;
- search and list data are limited to 64 KiB;
- details and routing data are limited to 128 KiB;
- truncation removes whole items or route alternatives, while the complete
  result remains available in job history.

See [docs/mcp.md](docs/mcp.md) for the complete contract.

## Routing and coverage

Routing tools accept coordinates and do not geocode text themselves:

```text
resolve_location → select one candidate → pass its latitude and longitude
```

`plan_public_transport` and `plan_street_route` are independent:

- Transitous handles only public transport;
- OpenRouteService handles only walking, cycling, and driving;
- the tools do not invoke each other;
- there is no automatic provider fallback.

Conditional publication applies to the MCP catalog only. REST endpoints and
application commands remain registered, but execution without provider
configuration fails with a configuration error.

`plan_public_transport` requires exactly one timezone-aware
`departure_time` or `arrival_time`. Walking access and egress within a transit
route are limited to 900 seconds on each side.

Every completed MCP routing result contains:

```json
{
  "type": "coverage_notice",
  "code": "regional_coverage_varies",
  "message": "Routing is not supported in every region. Availability depends on the provider and its underlying routing data."
}
```

In the July 2026 live tests, Transitous showed no observable Moscow or Moscow
Oblast coverage: the tested points had no stops, stoptimes, or itineraries,
while the Berlin control worked. Geoapify and Google Routes also failed to meet
the requirements for Russian public-transport routing. This is a dated
provider snapshot, not a permanent guarantee.

Details:

- [routing contracts](docs/routing.md);
- [Transitous, Geoapify, and Google Routes live-test report](docs/transit-provider-live-tests.md).

## Requirements

- Python 3.11 or newer;
- PostgreSQL 16;
- Redis 7;
- Docker Engine / Docker Desktop with Compose for the prepared local
  infrastructure;
- PowerShell for the provided `scripts/smoke_test.ps1`;
- an OpenRouteService API key only when `plan_street_route` is needed;
- a valid Transitous User-Agent containing the application name, version, and
  contact when `plan_public_transport` is needed.

## Quick start

Run the following commands from the repository root.

### 1. Prepare the environment

```powershell
Copy-Item .env.example .env
```

Before starting the service, update at least:

- `POSTGRES_PASSWORD`;
- `NOMINATIM_USER_AGENT` so it identifies your application;
- the contact in `TRANSITOUS_USER_AGENT`;
- `OPENROUTESERVICE_API_KEY` when street routing is required.

Do not commit `.env` files containing real passwords or API keys.

### 2. Start the complete stack

```powershell
docker compose up --build -d
docker compose ps --all
```

One command builds the application, applies the Alembic migrations, and starts:

- PostgreSQL;
- Redis with AOF persistence;
- FastAPI + FastMCP (`app.main:app`);
- the arq worker;
- an Nginx gateway on the single public HTTP port.

PostgreSQL and Redis are available only on the internal Compose network by
default, so they do not conflict with host-side instances.

The default command automatically loads `docker-compose.override.yml`: the
source tree is bind-mounted, Uvicorn reloads after changes under `app/`, and
arq watches the same directory. A local Python installation is not required
to run the stack.

The following URLs are then available:

| Purpose | URL |
|---|---|
| REST API | `http://127.0.0.1:8011/api/v1` |
| Swagger UI | `http://127.0.0.1:8011/docs` |
| ReDoc | `http://127.0.0.1:8011/redoc` |
| FastMCP Streamable HTTP | `http://127.0.0.1:8011/mcp` |

### 3. Check the service

```powershell
Invoke-RestMethod http://127.0.0.1:8011/api/v1/health
Invoke-RestMethod http://127.0.0.1:8011/api/v1/health/db
Invoke-RestMethod http://127.0.0.1:8011/api/v1/health/ready
```

For a production-like run without bind mounts or autoreload:

```powershell
docker compose -f docker-compose.yml up --build -d
```

Scale the API and worker without changing the public URL:

```powershell
docker compose up -d --scale app=3 --scale worker=4
```

See the [Docker guide](docs/docker.md) for code, dependency, environment, and
migration update workflows.

## Connecting an MCP client

### Streamable HTTP

With the API and worker running, configure the client to use:

```text
http://127.0.0.1:8011/mcp
```

### Stdio

Start the standalone stdio transport with:

```powershell
python -m app.mcp
```

Equivalent compatibility entrypoint:

```powershell
python mcp_server.py
```

Generic MCP client configuration:

```json
{
  "mcpServers": {
    "kudago-nominatim": {
      "command": "python",
      "args": ["-m", "app.mcp"],
      "cwd": "C:\\absolute\\path\\to\\kudago-nominatim-integrate-mcp"
    }
  }
}
```

The exact configuration format depends on the client. The stdio server opens
its own Redis connection, but application commands are still executed by the
separate arq worker.

## Configuration

Settings are loaded from environment variables and the local `.env` file.

### Application and infrastructure

| Variable | Purpose | `.env.example` value |
|---|---|---|
| `APP_NAME` | FastAPI application name | `KudaGo Nominatim FastAPI Service` |
| `DEBUG` | Debug mode | `0` |
| `DATABASE_ECHO` | SQLAlchemy query logging; forcibly disabled for stdio | `0` |
| `APP_BIND_ADDRESS` | HTTP gateway host interface | `127.0.0.1` |
| `APP_PORT` | HTTP gateway host port | `8011` |
| `UVICORN_WORKERS` | Uvicorn processes per production-like container | `1` |
| `DATABASE_URL` | PostgreSQL asyncpg URL | PostgreSQL at `127.0.0.1:5433` |
| `REDIS_URL` | Redis connection for arq and MCP | `redis://127.0.0.1:6379/0` |
| `COMMAND_JOB_TIMEOUT_SECONDS` | Internal application-command budget | `120` |
| `ARQ_JOB_TIMEOUT_SECONDS` | arq hard timeout; at least 5 seconds above the command timeout | `135` |
| `ARQ_MAX_JOBS` | Maximum concurrent jobs per worker container | `10` |
| `MCP_JOB_WAIT_TIMEOUT_SECONDS` | Maximum worker wait inside an MCP call | `180` |
| `POSTGRES_USER` | PostgreSQL user in Compose | `kudago` |
| `POSTGRES_PASSWORD` | PostgreSQL password in Compose | `change-me` |
| `POSTGRES_DB` | PostgreSQL database in Compose | `kudago_service` |
| `POSTGRES_PORT` | PostgreSQL port with the opt-in host configuration | `5433` |
| `REDIS_PORT` | Redis port with the opt-in host configuration | `6379` |

### External providers

| Variable | Purpose |
|---|---|
| `KUDAGO_BASE_URL` | KudaGo API v1.4 base URL |
| `KUDAGO_LANG` | KudaGo request language |
| `KUDAGO_USER_AGENT` | KudaGo client User-Agent |
| `NOMINATIM_USER_AGENT` | Required identifying Nominatim User-Agent |
| `NOMINATIM_MIN_INTERVAL_SECONDS` | Minimum delay between Nominatim requests |
| `NOMINATIM_COUNTRYCODES` | Geocoding country restriction; `ru` by default |
| `DEFAULT_RADIUS` | Default geo-search radius in meters |
| `TRANSITOUS_BASE_URL` | Transitous / MOTIS 2 base URL |
| `TRANSITOUS_USER_AGENT` | Application name, version, and contact; controls transit MCP tool publication |
| `TRANSITOUS_TIMEOUT_SECONDS` | Transitous timeout |
| `OPENROUTESERVICE_BASE_URL` | OpenRouteService base URL |
| `OPENROUTESERVICE_API_KEY` | API key; controls street-route MCP tool publication |
| `OPENROUTESERVICE_USER_AGENT` | OpenRouteService User-Agent |
| `OPENROUTESERVICE_TIMEOUT_SECONDS` | OpenRouteService timeout |

Exact defaults are defined in [.env.example](.env.example) and
[app/core/config.py](app/core/config.py).

## REST API and job lifecycle

### Queued commands

All primary POST commands create a job and return `job_id` and `queue_job_id`.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/geo/resolve` | Geocoding |
| `POST` | `/api/v1/events/search` | Events |
| `POST` | `/api/v1/places/search` | Places |
| `POST` | `/api/v1/movies/search` | Movies |
| `POST` | `/api/v1/movie-showings/search` | Movie showings |
| `POST` | `/api/v1/news/search` | News |
| `POST` | `/api/v1/lists/search` | Editorial guides |
| `POST` | `/api/v1/routing/transit` | Public transport |
| `POST` | `/api/v1/routing/street` | Walking, cycling, or driving |

Routing endpoints accept coordinates only. Resolve addresses or names first
through `/geo/resolve` or the MCP `resolve_location` tool.

### Direct GET requests

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | API health |
| `GET` | `/api/v1/health/db` | PostgreSQL health |
| `GET` | `/api/v1/references/event-categories` | Event categories |
| `GET` | `/api/v1/references/place-categories` | Place categories |
| `GET` | `/api/v1/references/locations` | KudaGo cities |
| `GET` | `/api/v1/references/locations/{slug}` | City record |
| `GET` | `/api/v1/objects/{type}/{id}` | Full object record |

### Jobs and diagnostics

Job states: `queued`, `running`, `succeeded`, `failed`.

```text
GET /api/v1/jobs/{job_id}
GET /api/v1/jobs/{job_id}?include_result=true
GET /api/v1/jobs/{job_id}/events
GET /api/v1/jobs/{job_id}/results
GET /api/v1/jobs/{job_id}/upstream-calls
```

The default `GET /jobs/{job_id}` response hides large `items` and `routes`.
Fetch complete data through `/results` or `include_result=true`.

A successfully executed job can contain a domain result such as
`geo_ambiguous`, `geo_not_found`, `geo_unsupported`, or `no_route`. These are
not transport errors.

Use [docs/api.md](docs/api.md) and Swagger UI at `/docs` for exact request and
response schemas.

## Testing

Install development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

### Unit and integration tests

```powershell
python -m pytest -q
```

The suite covers application handlers, provider clients, queue lifecycle, the
MCP catalog and schemas, cross-field validation, serializers, response limits,
conditional routing visibility, and the committed reference snapshot.

### REST smoke

With PostgreSQL, Redis, the API, and the worker running:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke_test.ps1
```

Alternative API URL:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke_test.ps1 `
  -BaseUrl "http://127.0.0.1:8011/api/v1"
```

### MCP checks

With PostgreSQL, Redis, and the worker running:

```powershell
python scripts/test_mcp_inmemory.py
python scripts/test_mcp_stdio.py
python scripts/test_mcp_http.py
python scripts/dump_mcp_schemas.py
```

The HTTP check additionally requires Uvicorn.

### Routing live test

```powershell
python scripts/test_routing_live.py
```

The live test calls real providers, requires a valid `TRANSITOUS_USER_AGENT`,
and uses `OPENROUTESERVICE_API_KEY` when configured. It is not part of normal
pytest runs.

Dedicated provider diagnostics and their required environment variables are
documented in the
[live-test report](docs/transit-provider-live-tests.md).

## Development

Apply a new revision to an already running Compose stack:

```powershell
docker compose run --rm migrate
```

Python source changes are picked up automatically by the development
containers. Rebuild the Python services after changing `pyproject.toml`:

```powershell
docker compose up --build -d app worker
```

For development outside Docker, install the package with its development
dependencies. A revision can then be created locally:

```powershell
python -m pip install -e ".[dev]"
python -m alembic revision --autogenerate -m "describe change"
```

Refresh the committed MCP reference snapshot:

```powershell
python scripts/update_mcp_reference_data.py
```

Inspect and persist the actual MCP schemas:

```powershell
python scripts/dump_mcp_schemas.py
```

## Project structure

```text
app/
  api/             FastAPI routers and dependencies
  application/     shared command contracts, executor, and handlers
  core/            settings, PostgreSQL, and Redis
  integrations/    external-provider HTTP clients
  mcp/             schemas, mappers, serializers, server, and tools
  models/          SQLAlchemy models
  repositories/    PostgreSQL operations
  schemas/         REST/application Pydantic contracts
  services/        business rules and provider orchestration
  workers/         arq tasks and WorkerSettings
alembic/            PostgreSQL migrations
docs/               detailed documentation
scripts/            smoke, schema, and live-diagnostic scripts
tests/              unit and integration tests
docker/              HTTP gateway configuration
Dockerfile           FastAPI/FastMCP, worker, and migration image
docker-compose.yml  production-like complete-stack definition
docker-compose.override.yml  local-development autoreload
docker-compose.host.yml  opt-in PostgreSQL and Redis host ports
```

## Documentation

| Document | Contents |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Components, queued lifecycle, persistence, and failure model |
| [docs/api.md](docs/api.md) | REST endpoints and payload examples |
| [docs/mcp.md](docs/mcp.md) | MCP facade v2, catalog, schemas, and envelopes |
| [docs/docker.md](docs/docker.md) | Compose stack, updates, and scaling |
| [docs/routing.md](docs/routing.md) | Transit and street-routing contracts |
| [docs/testing.md](docs/testing.md) | Unit, smoke, MCP, and live checks |
| [docs/mcp-schema-design.md](docs/mcp-schema-design.md) | Agent-facing schema principles |
| [docs/mcp-api-sources.md](docs/mcp-api-sources.md) | Enum and reference-data sources |
| [docs/transit-provider-live-tests.md](docs/transit-provider-live-tests.md) | Transitous, Geoapify, and Google Routes coverage comparison |

## Limitations and production readiness

- Incoming REST, MCP, and debug endpoints have no application-level
  authentication. Do not expose the service publicly without an external auth
  layer.
- `/api/v1/jobs/{job_id}/upstream-calls` returns persisted provider request and
  response payloads. Restrict or disable it in a public deployment.
- Data completeness and availability depend on KudaGo, Nominatim, Transitous,
  and OpenRouteService.
- Transitous and OpenRouteService do not guarantee coverage in every region.
- `no_route` does not prove that no physical route exists.
- An MCP timeout does not cancel the queued job; it can finish later and remain
  available through the REST job endpoints.
- A cached geo result legitimately produces no new upstream-call entry.
- Docker Compose does not containerize the API or worker; it starts PostgreSQL
  and Redis only.
- Keep `.env`, database credentials, and provider API keys out of git.
