# API

Base path: `/api/v1`.

Интерактивная OpenAPI-документация доступна в `/docs` после запуска сервиса.

## Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | состояние API |
| `GET` | `/health/db` | проверка PostgreSQL |

## Search Commands

Все POST-команды ниже создают job и возвращают `job_id` и `queue_job_id`.

| Method | Path | Main filters |
|---|---|---|
| `POST` | `/geo/resolve` | `query`, `countrycodes`, `limit`, `accept_language` |
| `POST` | `/events/search` | location/coordinates, dates, categories, tags, `is_free` |
| `POST` | `/places/search` | location/coordinates, categories, tags, showings |
| `POST` | `/movies/search` | location, place, tags, dates, premiere/free filters |
| `POST` | `/movie-showings/search` | location, movie/place IDs, dates, `is_free` |
| `POST` | `/news/search` | location, tags, `actual_only` |
| `POST` | `/lists/search` | location, tags |
| `POST` | `/routing/transit` | coordinate pair, time and transit constraints |
| `POST` | `/routing/street` | coordinate pair, walking/cycling/driving profile |

Search-команды принимают `location` как KudaGo slug либо `place_query` как
человекочитаемое название. Events и places также поддерживают полный набор
`lat`, `lon`, `radius`.

### Examples

Создание поиска событий:

```http
POST /api/v1/events/search
Content-Type: application/json
```

```json
{
  "place_query": "Москва",
  "categories": "concert",
  "page_size": 3,
  "lang": "ru"
}
```

Ответ содержит идентификатор фоновой задачи:

```json
{
  "status": "ok",
  "job_id": "a9e38c5c-d58d-43cb-b930-f6d6b268a466",
  "queue_job_id": "events.search:a9e38c5c-d58d-43cb-b930-f6d6b268a466",
  "enqueued": true
}
```

Поиск киносеансов:

```http
POST /api/v1/movie-showings/search
Content-Type: application/json
```

```json
{
  "location": "msk",
  "page_size": 3,
  "lang": "ru"
}
```

Получение карточки места:

```http
GET /api/v1/objects/place/1470?lang=ru
```

### Routing

Оба routing endpoint принимают координаты и создают queued jobs. Они не
геокодируют адреса и не вызывают друг друга.

```http
POST /api/v1/routing/transit
Content-Type: application/json
```

```json
{
  "origin_lat": 52.5200,
  "origin_lon": 13.4050,
  "destination_lat": 52.5100,
  "destination_lon": 13.3900,
  "time": "2026-07-12T18:40:00+02:00",
  "arrive_by": false,
  "transit_modes": ["SUBWAY", "BUS"],
  "num_itineraries": 3
}
```

```http
POST /api/v1/routing/street
Content-Type: application/json
```

```json
{
  "origin_lat": 55.842,
  "origin_lon": 37.180,
  "destination_lat": 55.850,
  "destination_lon": 37.195,
  "profile": "walking",
  "include_instructions": true,
  "include_geometry": false
}
```

Допустимые street profiles: `walking`, `cycling`, `driving`. Provider-specific
имена вроде `foot-walking` во внешний контракт не входят. Полные normalized
result contracts описаны в [routing.md](routing.md).

## Jobs

| Method | Path | Description |
|---|---|---|
| `POST` | `/jobs` | создать произвольную job |
| `GET` | `/jobs/{job_id}` | статус и компактный результат |
| `GET` | `/jobs/{job_id}?include_result=true` | статус и полный result payload |
| `GET` | `/jobs/{job_id}/events` | хронология выполнения |
| `GET` | `/jobs/{job_id}/results` | сохранённые command results |
| `GET` | `/jobs/{job_id}/upstream-calls` | реальные внешние HTTP-вызовы |
| `POST` | `/jobs/{job_id}/run-test` | синхронная диагностическая команда |
| `POST` | `/jobs/{job_id}/enqueue-test` | queued диагностическая команда |

Успех транспорта и успех бизнес-результата различаются. Например, job может
быть `succeeded`, а `result_payload.status` — `geo_ambiguous`.

## References

| Method | Path | Description |
|---|---|---|
| `GET` | `/references/event-categories` | категории событий |
| `GET` | `/references/place-categories` | категории мест |
| `GET` | `/references/locations` | города KudaGo |
| `GET` | `/references/locations/{slug}` | карточка города |

Все reference endpoints поддерживают query-параметр `lang`.

## Object Details

```text
GET /objects/{object_type}/{object_id}
```

Поддерживаемые типы:

```text
event
place
movie
movie_showing
news
list
agent
agent_role
location
```

Опциональные query-параметры:

- `lang`;
- `include_comments` для поддерживаемых типов;
- `include_showings` для movie.

## Common Result Statuses

| Status | Meaning |
|---|---|
| `ok` | команда выполнена |
| `ambiguous` / `geo_ambiguous` | найдено несколько geo candidates |
| `geo_not_found` | место не найдено |
| `geo_unsupported` | endpoint не поддерживает найденные координаты |
| `no_route` | provider корректно ответил, но маршрут не найден |

Для точных request/response schemas используйте OpenAPI `/docs`.
