# Agent-facing FastMCP transport

FastMCP is available as streamable HTTP at `/mcp` and as a standalone stdio
server:

```powershell
uvicorn app.main:app --reload --port 8011
python -m app.mcp
```

The MCP contract is a version 2 agent facade. It maps user intentions to the
existing application commands; it is deliberately not a second copy of the
REST request models.

## Execution lifecycle

All MCP application commands use the shared queued lifecycle:

```text
FastMCP tool
  -> commit api_request + job in PostgreSQL
  -> enqueue process_command_job in Redis
  -> await arq worker
  -> load the persisted CommandOutput in a new DB session
  -> MCP serializer and response envelope
```

The arq worker is required for HTTP, stdio and in-memory MCP transports. The
FastMCP server owns one Redis pool per server lifespan and exposes it to tools
through the hidden `Context` parameter; `ctx` is not part of any public tool
schema. Application handlers and external APIs run only in the worker.

The timeout chain is deliberately ordered: command execution uses
`COMMAND_JOB_TIMEOUT_SECONDS` (120 seconds by default), arq enforces the hard
`ARQ_JOB_TIMEOUT_SECONDS` limit (135 seconds), and MCP waits up to the
server-lifespan value `MCP_JOB_WAIT_TIMEOUT_SECONDS` (180 seconds). The MCP
value configured on a particular server instance is passed to every tool. The
arq hard timeout must leave at least five seconds after the command timeout for
rollback and terminal-state persistence.
An MCP wait timeout returns `processing_timeout` with `retryable=false`, leaves
the job queued or running, and does not abort it. Redis, worker and timeout
failures never fall back to inline execution.

## Tool catalog

| MCP tool | User intent | Application command |
|---|---|---|
| `resolve_location` | Geocode a free-form location | `geo.resolve` |
| `find_events` | Find scheduled events in a calendar window | `events.search` |
| `find_places` | Find venues and attractions | `places.search` |
| `find_movies` | Find movie records | `movies.search` |
| `find_movie_showings` | Find actual cinema showings | `movie_showings.search` |
| `find_city_news` | Find current or historical city news | `news.search` |
| `find_city_guides` | Find editorial city guides | `lists.search` |
| `get_details` | Hydrate an item returned by a search tool | `object.detail` |
| `plan_public_transport` | Plan a public-transport journey | `routing.transit.plan` |
| `plan_street_route` | Plan a walking, cycling or driving route | `routing.street.plan` |

The former MCP names (`events`, `places`, `reference`, `object`,
`transit_route`, and the other version 1 names) are not aliases. This is an
intentional MCP-only breaking change. REST endpoints and application command
names are unchanged.

## Self-contained schemas

Every public field has a JSON Schema description and machine-readable limits.
Finite sets use enums:

- event categories and place categories are separate enums;
- KudaGo locations come from the committed v1.4 reference snapshot;
- detail item types and routing modes are fixed agent-facing enums;
- `radius_km`, `limit`, page bounds and string lengths carry numeric/string
  constraints.

The runtime never downloads reference data. Refresh it explicitly with:

```powershell
python scripts/update_mcp_reference_data.py
```

The `reference` tool is therefore no longer required. See
[mcp-schema-design.md](mcp-schema-design.md) and
[mcp-api-sources.md](mcp-api-sources.md).

## Location and time rules

`find_events` and `find_places` require exactly one of:

- `place` for a free-form city, district, address or landmark;
- `location_slug` for a value from the committed KudaGo enum;
- `coordinates` plus `radius_km`.

City-only tools require exactly one of `city` and `location_slug`.

Calendar tools accept either `date` or a complete `date_from`/`date_to` range.
Ranges are inclusive and limited to 31 days. `timezone` accepts an IANA name
or a fixed offset. When omitted for an exact snapshot location slug or city
name, the committed KudaGo timezone is used. Coordinates and other free-form
places require an explicit timezone. Calendar results report
`applied_timezone` and exact UTC boundaries.

## Semantic result flags

- `find_events`: `result_kind=scheduled_events`, `schedule_verified=true` for
  a completed KudaGo result, and only occurrence dates overlapping the applied
  window. In each `matching_dates` item, `start` or `end` can be `null` for
  startless or endless events. `schedules` contains a compact recurring
  schedule; `use_place_schedule=true` means that occurrence times should be
  checked against the venue schedule;
- `find_places`: `schedule_verified=false`; returned venues do not prove that
  an event is scheduled there;
- `find_movies`: `showing_times_verified=false`; use
  `find_movie_showings` for actual times;
- `find_movie_showings`: `schedule_verified=true` for a completed result; when
  date fields are omitted, the next seven days are searched;
- routing: `route_verified=true` only when `result_status=ok` and at least one
  complete route remains in the MCP response.

Search/list `data` is limited to 64 KiB. Whole items are removed from the end
when needed and the response reports `truncated`, `returned_to_agent` and
`full_result_available`. Routing has a 128 KiB limit and removes whole route
alternatives, never part of a leg. Full command output remains in job history.

Search data exposes only agent-level `applied_filters`; internal timestamps,
CSV values and `page_size` remain hidden. Geo metadata appears once in the MCP
envelope. `get_details` is capped at 128 KiB by removing complete comments and
showings from the end and reporting truncated sections.

## Routing visibility and workflow

`plan_public_transport` is registered only when `TRANSITOUS_USER_AGENT` is
non-empty. `plan_street_route` is registered only when
`OPENROUTESERVICE_API_KEY` is non-empty. Missing configuration produces a
server warning instead of a tool that is guaranteed to fail.

When only text is known:

1. call `resolve_location`;
2. select one coordinate candidate;
3. pass that candidate's latitude and longitude together to
   `plan_public_transport` for schedules, stops and transfers, or
   `plan_street_route` for an independent walking/cycling/driving route.

Both routing tools accept an optional label with each coordinate pair and
preserve it in the result and persisted request text. `plan_public_transport`
requires exactly one timezone-aware departure or arrival time. Omitted
`transport_modes` means all provider-supported transit modes; an explicit list
restricts the search. Routing `no_route` responses include structured
diagnostics and retry hints with both a stable code and agent-readable message.
`plan_street_route` exposes `travel_mode`, not an ORS profile.

Every completed result from either routing tool also contains a structured
`data.warnings` entry with `code=regional_coverage_varies`. This warning is
present for successful and `no_route` results because provider coverage is not
available in every region.

`plan_public_transport` publishes that time invariant as a structural JSON
Schema `oneOf`. Clients therefore see the requirement for exactly one non-null
`departure_time` or `arrival_time` in the machine-readable schema as well as in
the field descriptions; the opposite field may be omitted or sent as `null`.

The routing live smoke uses the real Streamable HTTP endpoint at `/mcp` with
Uvicorn, Redis, an arq worker, PostgreSQL and the real providers. The in-memory
MCP transport remains covered separately by unit and integration tests.

Provider-specific values such as `TRANSIT`, `foot-walking` and
`cycling-regular` are not public MCP values.

## Response envelope and errors

Successful calls return:

```json
{
  "status": "ok",
  "tool": "find_events",
  "job_id": "uuid",
  "result_status": "ok",
  "geo": null,
  "data": {},
  "meta": {}
}
```

Cross-field validation errors are structured and occur before job creation:

```json
{
  "status": "error",
  "tool": "find_events",
  "job_id": null,
  "error_type": "validation_error",
  "message": "Invalid tool arguments.",
  "details": [
    {
      "field": "radius_km",
      "code": "missing_required_companion",
      "message": "radius_km is required when coordinates are provided."
    }
  ],
  "retryable": true
}
```

If a worker is not available before the configured wait timeout, the persisted
job remains available for later worker execution:

```json
{
  "status": "error",
  "tool": "find_events",
  "job_id": "uuid",
  "error_type": "processing_timeout",
  "message": "The job is still queued or running and did not finish within the MCP wait timeout.",
  "retryable": false
}
```

Execution diagnostics and full results are available through the unchanged
REST job endpoints:

```text
GET /api/v1/jobs/{job_id}
GET /api/v1/jobs/{job_id}/events
GET /api/v1/jobs/{job_id}/results
GET /api/v1/jobs/{job_id}/upstream-calls
```

All tools declare read-only, non-destructive, idempotent and open-world MCP
annotation hints.
