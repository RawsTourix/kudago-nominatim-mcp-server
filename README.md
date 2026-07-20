<p align="center">
  <strong>Русский</strong> · <a href="./README.en.md">English</a>
</p>

# KudaGo Nominatim: FastAPI + FastMCP сервис

Асинхронный сервис для поиска событий, мест, фильмов, киносеансов, городских
новостей и подборок KudaGo, разрешения географических названий через Nominatim
и построения маршрутов через Transitous и OpenRouteService.

Одна прикладная логика опубликована через два интерфейса:

- REST API под `/api/v1`;
- фасад FastMCP v2 для агентов через Streamable HTTP `/mcp` и stdio.

> [!IMPORTANT]
> Для REST-команд через очередь и всех MCP-инструментов нужен запущенный arq
> worker.
> API или MCP transport без worker смогут принять запрос, но не выполнят
> application-команду.

> [!WARNING]
> Маршрутизация поддерживается не во всех регионах. Каждый завершённый ответ
> маршрутного MCP-инструмента содержит предупреждение
> `regional_coverage_varies`. `no_route`
> относится только к указанным точкам, времени и ограничениям и не доказывает,
> что физического маршрута или транспорта вообще не существует.

## Содержание

- [Возможности](#возможности)
- [Архитектура](#архитектура)
- [MCP-инструменты](#mcp-инструменты)
- [Маршрутизация и покрытие](#маршрутизация-и-покрытие)
- [Требования](#требования)
- [Быстрый старт](#быстрый-старт)
- [Подключение MCP-клиента](#подключение-mcp-клиента)
- [Конфигурация](#конфигурация)
- [REST API и жизненный цикл задач](#rest-api-и-жизненный-цикл-задач)
- [Тестирование](#тестирование)
- [Структура проекта](#структура-проекта)
- [Документация](#документация)
- [Ограничения и подготовка к промышленному развертыванию](#ограничения-и-подготовка-к-промышленному-развертыванию)

## Возможности

| Область | Возможности | Источник |
|---|---|---|
| События и места | Поиск по городу, свободному названию или координатам; фильтры по датам и категориям | KudaGo + Nominatim |
| Кино | Фильмы и реальные киносеансы | KudaGo |
| Городской контент | Новости и редакционные подборки | KudaGo |
| Геокодирование | Кандидаты координат для города, района, адреса или объекта | Nominatim |
| Общественный транспорт | Маршруты, пересадки, остановки и расписание при наличии данных | Transitous / MOTIS 2 |
| Пешком, велосипед, автомобиль | Независимые маршруты по дорожной сети | OpenRouteService |
| Диагностика | Jobs, события выполнения, полные результаты и журнал upstream-вызовов | PostgreSQL |

Ключевые свойства:

- FastAPI с OpenAPI, Swagger UI и ReDoc;
- фасад FastMCP 3.x версии 2 с описанными JSON Schema;
- MCP-транспорты Streamable HTTP и stdio;
- единый `CommandExecutor` для REST и MCP;
- PostgreSQL, асинхронный SQLAlchemy, Redis и arq;
- geo cache для повторного использования результатов Nominatim;
- сохранение `job_events`, `command_results` и `upstream_calls`;
- компактные agent-facing ответы с явными семантическими флагами;
- отдельные модульные, интеграционные, сценарные и запускаемые вручную проверки
  реальных провайдеров.

## Архитектура

REST-команды через очередь и MCP-инструменты используют один жизненный цикл:

```text
REST-клиент ─┐
             ├→ JobDispatchService → фиксация PostgreSQL → Redis → arq worker
MCP-клиент ──┘                                                  │
                                                                ▼
                                                   CommandExecutor
                                                                │
                                                                ▼
                                              сервис → внешний провайдер
                                                                │
                                                                ▼
                                 результат + события + upstream-диагностика

REST → сразу возвращает ответ с job_id поставленной в очередь задачи
MCP  → ждёт worker → читает сохранённый CommandOutput → сериализует ответ
```

Задача фиксируется в PostgreSQL до постановки в Redis. Обработчик arq получает
только `job_id`, загружает авторитетные команду и входные данные из базы,
выполняет handler и сохраняет итог. Ошибка постановки в очередь не оставляет
задачу навечно в `queued`: она переводится в `failed`.

Справочники и детальные REST GET-запросы выполняются напрямую и не создают
задач. MCP `get_details`, напротив, проходит через общий цикл с очередью.

Подробнее: [docs/architecture.md](docs/architecture.md).

## MCP-инструменты

Полностью настроенный сервер публикует 10 инструментов только для чтения.
Восемь доступны всегда, два маршрутных инструмента — только при наличии
конфигурации провайдера.

| MCP-инструмент | Назначение | Команда приложения | Публикация |
|---|---|---|---|
| `resolve_location` | Разрешить свободное название в кандидаты координат | `geo.resolve` | Всегда |
| `find_events` | Найти события в календарном окне | `events.search` | Всегда |
| `find_places` | Найти места и достопримечательности | `places.search` | Всегда |
| `find_movies` | Найти фильмы | `movies.search` | Всегда |
| `find_movie_showings` | Найти реальные киносеансы | `movie_showings.search` | Всегда |
| `find_city_news` | Найти городские новости | `news.search` | Всегда |
| `find_city_guides` | Найти редакционные подборки | `lists.search` | Всегда |
| `get_details` | Получить полную карточку найденного объекта | `object.detail` | Всегда |
| `plan_public_transport` | Построить маршрут общественного транспорта | `routing.transit.plan` | При непустом `TRANSITOUS_USER_AGENT` |
| `plan_street_route` | Построить пеший, велосипедный или автомобильный маршрут | `routing.street.plan` | При непустом `OPENROUTESERVICE_API_KEY` |

Старые имена MCP v1 (`events`, `places`, `object`, `transit_route`,
`street_route` и другие) не являются псевдонимами.

Все инструменты объявлены как доступные только для чтения, неразрушающие и
идемпотентные. Публичные схемы содержат описания, перечисления (`enum`),
числовые ограничения и межполевую валидацию. Ошибки аргументов возвращаются до
создания job.

В результатах для агента:

- `schedule_verified=true` означает подтверждённое расписание событий или
  киносеансов;
- `showing_times_verified=false` у фильма напоминает, что для времени сеанса
  нужен `find_movie_showings`;
- `route_verified=true` выставляется только при `result_status=ok` и наличии
  полного маршрута в MCP-ответе;
- данные поиска и подборок ограничены 64 KiB;
- детальные данные и маршруты ограничены 128 KiB;
- при усечении удаляются целые items или варианты маршрута, а полный результат
  остаётся в истории job.

Полный контракт: [docs/mcp.md](docs/mcp.md).

## Маршрутизация и покрытие

Инструменты маршрутизации принимают координаты и не геокодируют текст
самостоятельно:

```text
resolve_location → выбрать один candidate → передать его latitude и longitude
```

`plan_public_transport` и `plan_street_route` независимы:

- Transitous отвечает только за общественный транспорт;
- OpenRouteService отвечает только за walking/cycling/driving;
- инструменты не вызывают друг друга;
- автоматического резервного переключения между провайдерами нет.

Условная публикация относится только к MCP-каталогу. REST-маршруты и команды
приложения остаются зарегистрированными, но без настройки провайдера их
выполнение завершится ошибкой конфигурации.

`plan_public_transport` требует ровно одно значение с часовым поясом:
`departure_time` или `arrival_time`. Пеший доступ до и после участка
общественного транспорта ограничен 900 секундами с каждой стороны.

Каждый завершённый результат маршрутизации в MCP содержит:

```json
{
  "type": "coverage_notice",
  "code": "regional_coverage_varies",
  "message": "Routing is not supported in every region. Availability depends on the provider and its underlying routing data."
}
```

На live-тестах июля 2026 года Transitous не показал наблюдаемого покрытия
Москвы и Московской области: для проверенных точек отсутствовали stops,
stoptimes и itineraries, тогда как контрольный Берлин работал. Geoapify и
Google Routes также не удовлетворили требованиям российского
маршрутизации на общественном транспорте по России. Это снимок состояния
провайдеров на дату теста, а не вечная гарантия.

Подробности:

- [routing-контракты](docs/routing.md);
- [отчёт о live-тестах Transitous, Geoapify и Google Routes](docs/transit-provider-live-tests.md).

## Требования

- Python 3.11 или новее;
- PostgreSQL 16;
- Redis 7;
- Docker Engine / Docker Desktop с Compose — для готовой локальной
  инфраструктуры;
- PowerShell — для готового `scripts/smoke_test.ps1`;
- API key OpenRouteService — только если нужен `plan_street_route`;
- корректный Transitous User-Agent с именем приложения, версией и контактом —
  если нужен `plan_public_transport`.

## Быстрый старт

Команды ниже выполняются из корня репозитория.

### 1. Подготовить окружение

```powershell
Copy-Item .env.example .env
python -m pip install -e .
```

Перед запуском измените в `.env` как минимум:

- `POSTGRES_PASSWORD`;
- `NOMINATIM_USER_AGENT`, чтобы он идентифицировал ваше приложение;
- контакт в `TRANSITOUS_USER_AGENT`;
- `OPENROUTESERVICE_API_KEY`, если нужна маршрутизация OpenRouteService.

Не коммитьте `.env` с реальными паролями и API keys.

### 2. Запустить PostgreSQL и Redis

```powershell
docker compose up -d
docker compose ps
```

Compose поднимает только инфраструктуру. API и worker в текущей конфигурации
запускаются локально.

После копирования `.env.example` PostgreSQL доступен на `127.0.0.1:5433`, Redis
— на `127.0.0.1:6379`.

### 3. Применить миграции

```powershell
python -m alembic upgrade head
```

### 4. Запустить API

```powershell
python -m uvicorn app.main:app --reload --port 8011
```

Доступные адреса:

| Назначение | URL |
|---|---|
| REST API | `http://127.0.0.1:8011/api/v1` |
| Swagger UI | `http://127.0.0.1:8011/docs` |
| ReDoc | `http://127.0.0.1:8011/redoc` |
| FastMCP Streamable HTTP | `http://127.0.0.1:8011/mcp` |

### 5. Запустить обработчик arq

В отдельном терминале:

```powershell
arq app.workers.worker_settings.WorkerSettings
```

API, MCP-процесс и обработчик arq должны использовать одинаковые
`DATABASE_URL` и `REDIS_URL`.

### 6. Проверить сервис

```powershell
Invoke-RestMethod http://127.0.0.1:8011/api/v1/health
Invoke-RestMethod http://127.0.0.1:8011/api/v1/health/db
```

## Подключение MCP-клиента

### Streamable HTTP

При запущенных API и worker укажите клиенту:

```text
http://127.0.0.1:8011/mcp
```

### Stdio

Отдельный stdio-транспорт запускается так:

```powershell
python -m app.mcp
```

Эквивалентный совместимый entrypoint:

```powershell
python mcp_server.py
```

Обобщённый пример конфигурации MCP-клиента:

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

Формат конфигурации зависит от конкретного клиента. Stdio-сервер сам
подключается к Redis, но application-команды по-прежнему выполняет отдельный
arq worker.

## Конфигурация

Настройки загружаются из переменных окружения и локального `.env`.

### Приложение и инфраструктура

| Переменная | Назначение | Значение в `.env.example` |
|---|---|---|
| `APP_NAME` | Имя FastAPI-приложения | `KudaGo Nominatim FastAPI Service` |
| `DEBUG` | Debug-режим | `0` |
| `DATABASE_ECHO` | Журналирование SQL-запросов; для stdio принудительно отключается | `0` |
| `DATABASE_URL` | Asyncpg URL PostgreSQL | PostgreSQL на `127.0.0.1:5433` |
| `REDIS_URL` | Redis для arq и MCP | `redis://127.0.0.1:6379/0` |
| `COMMAND_JOB_TIMEOUT_SECONDS` | Внутренний бюджет application-команды | `120` |
| `ARQ_JOB_TIMEOUT_SECONDS` | Жёсткий лимит arq; минимум на 5 секунд больше лимита команды | `135` |
| `MCP_JOB_WAIT_TIMEOUT_SECONDS` | Максимальное ожидание worker внутри MCP-вызова | `180` |
| `POSTGRES_USER` | Пользователь PostgreSQL в Compose | `kudago` |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL в Compose | `change-me` |
| `POSTGRES_DB` | База PostgreSQL в Compose | `kudago_service` |
| `POSTGRES_PORT` | Порт PostgreSQL на host | `5433` |

### Внешние провайдеры

| Переменная | Назначение |
|---|---|
| `KUDAGO_BASE_URL` | Базовый URL KudaGo API v1.4 |
| `KUDAGO_LANG` | Язык KudaGo-запросов |
| `KUDAGO_USER_AGENT` | User-Agent клиента KudaGo |
| `NOMINATIM_USER_AGENT` | Обязательный идентифицирующий User-Agent Nominatim |
| `NOMINATIM_MIN_INTERVAL_SECONDS` | Минимальный интервал между Nominatim-запросами |
| `NOMINATIM_COUNTRYCODES` | Ограничение геокодирования по странам; по умолчанию `ru` |
| `DEFAULT_RADIUS` | Радиус geo search по умолчанию, метры |
| `TRANSITOUS_BASE_URL` | Базовый URL Transitous / MOTIS 2 |
| `TRANSITOUS_USER_AGENT` | Имя приложения, версия и контакт; управляет публикацией transit MCP tool |
| `TRANSITOUS_TIMEOUT_SECONDS` | Тайм-аут Transitous |
| `OPENROUTESERVICE_BASE_URL` | Базовый URL OpenRouteService |
| `OPENROUTESERVICE_API_KEY` | API key; управляет публикацией street-route MCP tool |
| `OPENROUTESERVICE_USER_AGENT` | User-Agent OpenRouteService |
| `OPENROUTESERVICE_TIMEOUT_SECONDS` | Тайм-аут OpenRouteService |

Точные defaults находятся в [.env.example](.env.example) и
[app/core/config.py](app/core/config.py).

## REST API и жизненный цикл задач

### Команды через очередь

Все основные POST-команды создают job и возвращают `job_id` и
`queue_job_id`.

| Метод | Endpoint | Назначение |
|---|---|---|
| `POST` | `/api/v1/geo/resolve` | Геокодирование |
| `POST` | `/api/v1/events/search` | События |
| `POST` | `/api/v1/places/search` | Места |
| `POST` | `/api/v1/movies/search` | Фильмы |
| `POST` | `/api/v1/movie-showings/search` | Киносеансы |
| `POST` | `/api/v1/news/search` | Новости |
| `POST` | `/api/v1/lists/search` | Подборки |
| `POST` | `/api/v1/routing/transit` | Общественный транспорт |
| `POST` | `/api/v1/routing/street` | Пешком, велосипед или автомобиль |

Маршрутные endpoints принимают только координаты. Адрес или название сначала
разрешите через `/geo/resolve` или MCP `resolve_location`.

### Прямые GET-запросы

| Метод | Endpoint | Назначение |
|---|---|---|
| `GET` | `/api/v1/health` | Состояние API |
| `GET` | `/api/v1/health/db` | Проверка PostgreSQL |
| `GET` | `/api/v1/references/event-categories` | Категории событий |
| `GET` | `/api/v1/references/place-categories` | Категории мест |
| `GET` | `/api/v1/references/locations` | Города KudaGo |
| `GET` | `/api/v1/references/locations/{slug}` | Карточка города |
| `GET` | `/api/v1/objects/{type}/{id}` | Детальная карточка объекта |

### Задачи и диагностика

Состояния задачи: `queued`, `running`, `succeeded`, `failed`.

```text
GET /api/v1/jobs/{job_id}
GET /api/v1/jobs/{job_id}?include_result=true
GET /api/v1/jobs/{job_id}/events
GET /api/v1/jobs/{job_id}/results
GET /api/v1/jobs/{job_id}/upstream-calls
```

Обычный `GET /jobs/{job_id}` скрывает большие `items` и `routes`. Полные данные
доступны через `/results` или `include_result=true`.

Успешно выполненная задача может содержать доменный результат `geo_ambiguous`,
`geo_not_found`, `geo_unsupported` или `no_route`. Это не ошибка транспорта.

Точные схемы запросов и ответов: [docs/api.md](docs/api.md) и Swagger UI
`/docs`.

## Тестирование

Установить dev dependencies:

```powershell
python -m pip install -e ".[dev]"
```

### Модульные и интеграционные тесты

```powershell
python -m pytest -q
```

Тесты проверяют обработчики приложения, клиенты провайдеров, жизненный цикл
очереди, MCP-каталог и схемы, межполевую валидацию, сериализаторы, ограничения
размера ответа, условную публикацию маршрутных инструментов и зафиксированный
снимок справочников.

### Проверка REST-сценариев

После запуска PostgreSQL, Redis, API и worker:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke_test.ps1
```

Другой API URL:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke_test.ps1 `
  -BaseUrl "http://127.0.0.1:8011/api/v1"
```

### Проверки MCP

При запущенных PostgreSQL, Redis и worker:

```powershell
python scripts/test_mcp_inmemory.py
python scripts/test_mcp_stdio.py
python scripts/test_mcp_http.py
python scripts/dump_mcp_schemas.py
```

HTTP-проверка дополнительно требует запущенный Uvicorn.

### Проверка маршрутизации с реальными провайдерами

```powershell
python scripts/test_routing_live.py
```

Этот тест обращается к реальным провайдерам, требует корректный
`TRANSITOUS_USER_AGENT` и использует `OPENROUTESERVICE_API_KEY`, если он задан.
Он не входит в обычный pytest.

Отдельные provider-диагностики и необходимые переменные окружения описаны в
[отчёте о live-тестах](docs/transit-provider-live-tests.md).

## Разработка

Применить миграции:

```powershell
python -m alembic upgrade head
```

Создать ревизию миграции:

```powershell
python -m alembic revision --autogenerate -m "описание изменения"
```

Обновить зафиксированный в git снимок справочников MCP:

```powershell
python scripts/update_mcp_reference_data.py
```

Проверить и сохранить реальные MCP schemas:

```powershell
python scripts/dump_mcp_schemas.py
```

## Структура проекта

```text
app/
  api/             FastAPI routers и зависимости
  application/     общие контракты команд, executor и обработчики
  core/            settings, PostgreSQL и Redis
  integrations/    HTTP-клиенты внешних провайдеров
  mcp/             схемы, преобразователи, сериализаторы, server и tools
  models/          модели SQLAlchemy
  repositories/    операции с PostgreSQL
  schemas/         контракты Pydantic для REST и прикладного слоя
  services/        бизнес-правила и оркестрация провайдеров
  workers/         задачи arq и WorkerSettings
alembic/            миграции PostgreSQL
docs/               подробная документация
scripts/            сценарные проверки, выгрузка схем и live-диагностика
tests/              модульные и интеграционные тесты
docker-compose.yml  PostgreSQL и Redis для локальной разработки
```

## Документация

| Документ | Содержание |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Компоненты, цикл очереди, хранение данных и модель ошибок |
| [docs/api.md](docs/api.md) | REST endpoints и примеры данных |
| [docs/mcp.md](docs/mcp.md) | MCP-фасад v2, каталог, схемы и envelopes |
| [docs/routing.md](docs/routing.md) | Контракты маршрутов общественного транспорта и дорожной сети |
| [docs/testing.md](docs/testing.md) | Модульные, интеграционные, MCP- и live-проверки |
| [docs/mcp-schema-design.md](docs/mcp-schema-design.md) | Принципы схем для агентов |
| [docs/mcp-api-sources.md](docs/mcp-api-sources.md) | Источники перечислений и справочных данных |
| [docs/transit-provider-live-tests.md](docs/transit-provider-live-tests.md) | Сравнение покрытия Transitous, Geoapify и Google Routes |

## Ограничения и подготовка к промышленному развертыванию

- Входящие REST, MCP и диагностические endpoints не имеют аутентификации на
  уровне приложения. Не публикуйте сервис в интернет без внешнего слоя
  аутентификации.
- `/api/v1/jobs/{job_id}/upstream-calls` возвращает сохранённые request/response
  payloads провайдеров. Ограничьте к нему доступ или отключите его в публичном
  окружении.
- Полнота и доступность данных зависят от KudaGo, Nominatim, Transitous и
  OpenRouteService.
- Transitous и OpenRouteService не гарантируют покрытие каждого региона.
- `no_route` не является доказательством отсутствия физического маршрута.
- MCP timeout не отменяет queued job: она может завершиться позднее и остаться
  доступной через REST job endpoints.
- Кэшированный geo result закономерно не создаёт новый upstream-call.
- Docker Compose не контейнеризирует API и обработчик arq; он запускает только
  PostgreSQL и Redis.
- Храните `.env`, реквизиты базы данных и API keys провайдеров вне git.
