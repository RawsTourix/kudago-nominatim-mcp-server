# Docker and Compose

## Services

The Compose project keeps stateful infrastructure and stateless application
processes separate:

```text
client -> gateway -> app (FastAPI + FastMCP) -> Redis -> worker (arq)
                         |                         |
                         +------ PostgreSQL <------+

migrate -> PostgreSQL (one-shot, before app and worker)
```

| Service | Responsibility | Persistent state |
|---|---|---|
| `gateway` | Stable HTTP endpoint and load balancing across `app` replicas | none |
| `app` | FastAPI and FastMCP Streamable HTTP | none |
| `worker` | arq command execution | none |
| `migrate` | `alembic upgrade head` before application startup | none |
| `redis` | arq queue, configured with AOF | `redis_data` |
| `postgres` | jobs, results, caches, and diagnostics | `postgres_data` |

There are no fixed `container_name` values. The gateway resolves the Compose
`app` service through Docker DNS and refreshes its upstream addresses, so API
replicas can be added without publishing another host port.
The `app` and `gateway` healthchecks use `/api/v1/health/ready`, which verifies
both PostgreSQL and Redis connectivity.

## Development start

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps --all
docker compose logs -f app worker
```

Compose automatically merges `docker-compose.override.yml`. It bind-mounts
the repository into each Python container, runs Uvicorn with `--reload`, and
runs arq with `--watch /app/app`.

The complete API is exposed through the gateway at
`http://127.0.0.1:8011`. PostgreSQL and Redis stay on the internal Docker
network. Set `APP_BIND_ADDRESS=0.0.0.0` only when the API must be reachable
from other machines and an appropriate firewall/authentication setup exists.

To expose PostgreSQL and Redis to host-side clients, explicitly include the
opt-in configuration:

```powershell
docker compose `
  -f docker-compose.yml `
  -f docker-compose.override.yml `
  -f docker-compose.host.yml `
  up --build -d
```

The default host ports are `5433` and `6379`. This command fails intentionally
when those ports are already owned by another local stack; change
`POSTGRES_PORT` or `REDIS_PORT` in `.env` in that case.

## Updating a running development stack

| Change | Command or behavior |
|---|---|
| Python source under `app/` | API reload and worker restart automatically |
| `pyproject.toml` dependencies | `docker compose up --build -d app worker` |
| `.env` values | `docker compose up -d --force-recreate app worker` |
| New Alembic revision | `docker compose run --rm migrate` |
| `docker/nginx.conf` | `docker compose exec gateway nginx -s reload` |
| Compose configuration | `docker compose up -d` |

Use backward-compatible, expand/contract database migrations while old and new
application processes may overlap. Compose can recreate services cleanly, but
it is not a zero-downtime orchestrator.

## Production-like start

Specifying only the base file disables the development override:

```powershell
docker compose -f docker-compose.yml up --build -d
```

The application then runs from the immutable image without source bind mounts
or autoreload. Put TLS and production authentication at the gateway or at an
external ingress. Supply secrets through deployment-managed environment or
secret facilities rather than committing `.env`.

## Scaling

Prefer one Uvicorn process per container and scale containers horizontally:

```powershell
docker compose up -d --scale app=3 --scale worker=4
```

For the production-like variant:

```powershell
docker compose -f docker-compose.yml up -d --scale app=3 --scale worker=4
```

`ARQ_MAX_JOBS` controls concurrency per worker container. Effective maximum
job concurrency is approximately `worker replicas * ARQ_MAX_JOBS`; external
provider rate limits and PostgreSQL capacity should determine the actual
values. `UVICORN_WORKERS` is available when multiple processes per container
are specifically desired.

Scaling PostgreSQL and Redis requires a dedicated HA design or managed
services; do not create Compose replicas of these stateful services.

## Operations

```powershell
# Current state, including the completed migration container
docker compose ps --all

# Follow application logs
docker compose logs -f gateway app worker

# Restart one layer
docker compose restart worker

# Stop containers while preserving PostgreSQL and Redis volumes
docker compose down

# Inspect the resolved configuration
docker compose config
```

`docker compose down --volumes` also deletes the database and Redis volumes
and therefore should only be used when that data loss is intentional.
