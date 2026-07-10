# Routing

The service exposes two independent, coordinate-first routing capabilities:

| Domain | Application command | MCP tool | Provider |
|---|---|---|---|
| Public transport | `routing.transit.plan` | `transit_route` | Transitous / MOTIS 2 |
| Walking, cycling, driving | `routing.street.plan` | `street_route` | OpenRouteService |

## Responsibility boundary

`transit_route` handles trains, suburban rail, metro, buses, trams, ferries,
transfers and the walking access/egress legs supplied inside the Transitous
itinerary. `street_route` handles only an independent walking, cycling or
driving journey. The tools do not call each other and there is no automatic
fallback from Transitous to OpenRouteService.

Both tools accept coordinates, not addresses. Use this workflow when the user
provided text:

```text
resolve_place -> select confirmed coordinates -> transit_route or street_route
```

Do not rebuild Transitous walking legs through OpenRouteService. Do not infer
stations, line numbers, transfers or schedules from a street route.

## Normalized contracts

Transit results contain a stable `query`, `routes`, `warnings` and
`attribution`. Every itinerary includes departure/arrival time, duration,
transfer count, realtime/cancellation flags, and normalized legs. Leg facts
such as stop names, line names, headsign, agency and scheduled/realtime times
are copied only when the provider supplied them. Geometry, MOTIS debug output,
page cursors and raw request parameters are not exposed.

Street results contain the external profile (`walking`, `cycling` or
`driving`), route distance/duration, bbox, segments and optional steps. The
OpenRouteService profile names `foot-walking`, `cycling-regular` and
`driving-car` remain internal. Full geometry is persisted only when requested;
the compact MCP response always removes it and sets `geometry_hidden: true`.

Complete persisted results remain available at:

```text
GET /api/v1/jobs/{job_id}/results
GET /api/v1/jobs/{job_id}?include_result=true
```

## Status and error model

| Result status | Meaning | Job state |
|---|---|---|
| `ok` | provider returned at least one normalized route | `succeeded` |
| `no_route` | provider returned no route for this query | `succeeded` |
| `coverage_unavailable` | provider explicitly reported missing coverage/data | `succeeded` |
| execution error | timeout, network/DNS, HTTP 429/5xx, invalid response or configuration failure | `failed` |

OpenRouteService HTTP 404 and routing errors `2009`/`2016` are normalized as
`no_route`; other provider errors are not hidden. A `no_route` result is not
proof that transport does not exist—it only describes this provider query.

## Provider requirements

Transitous is a community best-effort service. Coverage and realtime data are
not guaranteed. Every request sends `TRANSITOUS_USER_AGENT`; Transitous asks it
to contain the application name, client version and a contact email or website.
Results include links to the Transitous data sources and OpenStreetMap
attribution.

OpenRouteService requires `OPENROUTESERVICE_API_KEY` only when `street_route` is
called. The key is sent in the authorization header and is never written to
jobs, command results, upstream payloads, logs or error text. An empty key does
not prevent FastAPI, the worker or MCP server from starting.
