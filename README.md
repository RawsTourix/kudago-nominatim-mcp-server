# KudaGo Nominatim FastAPI + FastMCP Service

## Overview

The service exposes one application command layer through two contracts:

- FastAPI REST under `/api/v1/*`; search commands are queued for an arq worker,
  while reference and object GET endpoints remain synchronous and untracked;
- an agent-facing FastMCP v2 facade over streamable HTTP at `/mcp` or stdio.

REST and MCP application commands share one queued execution lifecycle:
PostgreSQL job → Redis → arq worker → `CommandExecutor`. REST returns the queued
job immediately; MCP waits for the worker and returns an agent-facing result.
See [docs/mcp.md](docs/mcp.md) for the tool catalog and response envelope.

> An arq worker is required to execute MCP tools as well as queued REST commands.

Асинхронный FastAPI-сервис для поиска событий, мест, фильмов, киносеансов,
новостей и подборок KudaGo. Названия населённых пунктов сопоставляются со
справочником KudaGo, а при необходимости разрешаются через Nominatim.
Transitous предоставляет маршруты общественного транспорта, а
OpenRouteService — маршруты пешком, на велосипеде и на автомобиле.

Длительные операции оформляются как jobs: API сохраняет задачу в PostgreSQL,
помещает её в Redis, а отдельный arq worker выполняет внешние запросы и сохраняет
результаты, события выполнения и диагностические данные.

## Features

- FastMCP transport over streamable HTTP and stdio;
- ten self-contained agent tools with enums, field descriptions and compact results;
- FastAPI HTTP API и автоматическая OpenAPI-документация;
- PostgreSQL и асинхронный SQLAlchemy;
- Redis и arq для фоновых задач;
- интеграции с KudaGo, Nominatim, Transitous и OpenRouteService;
- независимые public-transit и walking/cycling/driving routing commands;
- кэширование результатов геокодирования;
- история событий job и журнал внешних HTTP-вызовов;
- компактное получение статуса и отдельная выдача полных результатов;
- PowerShell smoke-test основных сценариев.

## Architecture

Единый поток application-команды:

```text
REST ─┐
      ├→ api_request → job → Redis → arq → CommandExecutor
MCP ──┘

REST → queued response
MCP  → await worker → MCP serializer → result
```

Подробнее: [docs/architecture.md](docs/architecture.md).

## Project Structure

```text
app/
  application/     shared command executor, contracts and handlers
  api/             HTTP dependencies and routers
  core/            configuration, PostgreSQL and Redis
  integrations/    KudaGo, Nominatim and routing provider clients
  mcp/             agent schemas, mappers, serializers, FastMCP server and tools
  models/          SQLAlchemy models
  repositories/    database access
  schemas/         Pydantic request and response models
  services/        application and integration logic
  workers/         arq tasks and worker settings
alembic/            database migrations
docs/               architecture and API documentation
scripts/            smoke tests
```

## Requirements

- Python 3.11+;
- Docker with Docker Compose;
- PowerShell для запуска готового smoke-test.

## Quick Start

Подготовьте окружение, инфраструктуру и базу данных:

```powershell
Copy-Item .env.example .env
python -m pip install -e .
docker compose up -d
alembic upgrade head
uvicorn app.main:app --reload --port 8011
```

В отдельном терминале запустите worker:

```powershell
arq app.workers.worker_settings.WorkerSettings
```

После запуска выполните smoke-test:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke_test.ps1
```

## Environment Variables

Создайте локальный файл окружения:

```powershell
Copy-Item .env.example .env
```

Основные настройки:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | asyncpg URL подключения к PostgreSQL |
| `REDIS_URL` | Redis database для arq |
| `MCP_JOB_WAIT_TIMEOUT_SECONDS` | максимальное ожидание worker для MCP-вызова; по умолчанию 180 секунд |
| `KUDAGO_BASE_URL` | базовый URL KudaGo API |
| `KUDAGO_LANG` | язык запросов KudaGo |
| `KUDAGO_USER_AGENT` | User-Agent клиента KudaGo |
| `NOMINATIM_USER_AGENT` | обязательный User-Agent Nominatim |
| `NOMINATIM_MIN_INTERVAL_SECONDS` | минимальный интервал между запросами |
| `NOMINATIM_COUNTRYCODES` | ограничение поиска по странам |
| `DEFAULT_RADIUS` | радиус геопоиска по умолчанию, метры |
| `TRANSITOUS_BASE_URL` | базовый URL Transitous / MOTIS 2 |
| `TRANSITOUS_USER_AGENT` | имя приложения, версия и контакт; без значения transit MCP tool не публикуется |
| `TRANSITOUS_TIMEOUT_SECONDS` | timeout Transitous routing |
| `OPENROUTESERVICE_BASE_URL` | базовый URL OpenRouteService |
| `OPENROUTESERVICE_API_KEY` | API key; без значения street-route MCP tool не публикуется |
| `OPENROUTESERVICE_USER_AGENT` | User-Agent OpenRouteService; по умолчанию `kudago-nominatim-service/0.1.0` |
| `OPENROUTESERVICE_TIMEOUT_SECONDS` | timeout OpenRouteService directions |

Не коммитьте `.env` с реальными учётными данными.

## Docker Services

`docker-compose.yml` поднимает инфраструктуру:

- PostgreSQL 16;
- Redis 7.

API и worker в текущем MVP запускаются локально, а не в контейнерах.

```powershell
docker compose up -d
docker compose ps
```

Порт PostgreSQL задаётся через `POSTGRES_PORT`; Redis доступен на `6379`.

## Running Locally

Установите проект:

```powershell
python -m pip install -e .
```

Запустите инфраструктуру и примените миграции:

```powershell
docker compose up -d
alembic upgrade head
```

Запустите API:

```powershell
uvicorn app.main:app --reload --port 8011
```

Документация будет доступна по адресам:

```text
http://127.0.0.1:8011/docs
http://127.0.0.1:8011/redoc
```

## Running Worker

В отдельном терминале:

```powershell
arq app.workers.worker_settings.WorkerSettings
```

API, MCP transport и worker должны использовать одинаковые `DATABASE_URL` и
`REDIS_URL`. Worker обязателен для queued REST endpoints и всех MCP tools.

## Database Migrations

Применить миграции:

```powershell
alembic upgrade head
```

Создать миграцию после изменения моделей:

```powershell
alembic revision --autogenerate -m "describe change"
```

## API Endpoints

Основные команды:

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/geo/resolve` | геокодирование названия |
| `POST` | `/api/v1/events/search` | поиск событий |
| `POST` | `/api/v1/places/search` | поиск мест |
| `POST` | `/api/v1/movies/search` | поиск фильмов |
| `POST` | `/api/v1/movie-showings/search` | поиск киносеансов |
| `POST` | `/api/v1/news/search` | поиск новостей |
| `POST` | `/api/v1/lists/search` | поиск подборок |
| `POST` | `/api/v1/routing/transit` | общественный транспорт через Transitous |
| `POST` | `/api/v1/routing/street` | пешком, велосипед или автомобиль через OpenRouteService |
| `GET` | `/api/v1/objects/{type}/{id}` | полная карточка объекта |
| `GET` | `/api/v1/references/*` | справочники KudaGo |

Полная таблица: [docs/api.md](docs/api.md).

Маршрутизация принимает только координаты. Если известен адрес или название,
сначала используйте `resolve_location`, затем передайте выбранные координаты в
`plan_public_transport` либо `plan_street_route`. Подробные контракты и ограничения описаны
в [docs/routing.md](docs/routing.md).

## Jobs Lifecycle

Фоновый endpoint сразу возвращает `job_id`. Проверить состояние:

```text
GET /api/v1/jobs/{job_id}
```

Стандартные состояния: `queued`, `running`, `succeeded`, `failed`.

По умолчанию массив `items` скрывается из ответа job. Полные данные доступны:

```text
GET /api/v1/jobs/{job_id}/results
GET /api/v1/jobs/{job_id}?include_result=true
```

Диагностика:

```text
GET /api/v1/jobs/{job_id}/events
GET /api/v1/jobs/{job_id}/upstream-calls
```

## Smoke Test

Перед тестом должны работать PostgreSQL, Redis, API и arq worker.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke_test.ps1
```

Run the MCP checks after PostgreSQL and Redis are available, migrations are
applied, and the arq worker is running:

```powershell
python scripts/test_mcp_inmemory.py
python scripts/test_mcp_stdio.py
python scripts/test_mcp_http.py
python scripts/dump_mcp_schemas.py
```

The HTTP check expects the FastAPI application to be running. To launch only
the stdio MCP transport for an MCP client, use:

```powershell
python -m app.mcp
```

Другой адрес API можно передать параметром:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke_test.ps1 `
  -BaseUrl "http://127.0.0.1:8011/api/v1"
```

## Known Issues

- KudaGo `/places/` с `has_showings=movie` может завершаться по `ReadTimeout`
  даже с ограниченным временным диапазоном. Для киносеансов используйте
  `/api/v1/movie-showings/search`.
- Надёжность и полнота данных зависят от внешних KudaGo и Nominatim API.
- Transitous работает best-effort и не гарантирует покрытие или realtime-данные
  для каждого региона. `no_route` не доказывает отсутствие транспорта вообще.
- Debug endpoint `/jobs/{id}/upstream-calls` возвращает сохранённые upstream
  payloads без отдельной авторизации; перед публичным развёртыванием его нужно
  защитить или отключить.

## Roadmap

- автоматические unit и integration tests;
- аутентификация и ограничение debug endpoints;
- контейнеризация API и worker;
- retry/backoff и метрики внешних запросов.
