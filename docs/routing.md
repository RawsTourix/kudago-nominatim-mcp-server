# Routing

The service exposes two independent coordinate-first routing capabilities:

| Domain | Application command | MCP v2 tool | Provider |
|---|---|---|---|
| Public transport | `routing.transit.plan` | `plan_public_transport` | Transitous / MOTIS 2 |
| Walking, cycling, driving | `routing.street.plan` | `plan_street_route` | OpenRouteService |

## Responsibility boundary

`plan_public_transport` handles trains, suburban rail, metro, buses, trams,
ferries, transfers and the walking access/egress legs supplied inside a
Transitous itinerary. `plan_street_route` handles only an independent walking,
cycling or driving journey. The tools do not call each other and there is no
provider fallback.

Both tools accept nested `{latitude, longitude}` points. Resolve text first:

```text
resolve_location -> select confirmed coordinates -> routing tool
```

Public MCP modes are lower-case agent values. The mapper converts them to the
existing application enums; ORS profiles such as `foot-walking` remain
internal. Street MCP calls always request instructions and disable geometry.

## Normalized contracts

Transit routes contain query facts, complete alternatives, warnings and the
required Transitous/OpenStreetMap attribution. Street routes contain distance,
duration, bbox, segments and instructions. Provider raw responses, MOTIS debug
fields, cursors and geometry are absent from MCP data.

`route_verified` is true only when `result_status=ok` and at least one complete
route is returned to the agent. `no_route` produces `route_verified=false` and
an empty route list; it is not proof that transport does not exist.

MCP routing data is limited to 128 KiB by removing whole alternatives from the
end, never part of a leg. Complete persisted results remain available at:

```text
GET /api/v1/jobs/{job_id}/results
GET /api/v1/jobs/{job_id}?include_result=true
```

## Conditional publication

- `plan_public_transport` is published only when `TRANSITOUS_USER_AGENT` is
  non-empty and includes application name, client version and contact;
- `plan_street_route` is published only when `OPENROUTESERVICE_API_KEY` is
  non-empty.

The FastAPI and worker routing commands remain available regardless of MCP
catalog visibility. Missing MCP provider configuration is logged as a warning.

## Provider contracts

Transitous production currently links to the tagged MOTIS `v2.10.2` OpenAPI
definition. The service calls stable `GET /api/v6/plan`, whose coordinate
strings are `latitude,longitude`. OpenRouteService Directions v2 receives
`[longitude, latitude]` at `POST /v2/directions/{profile}/json`.

Only ORS error codes `2009` and `2016` are normalized as `no_route`; a bare HTTP
404 remains an execution error. MOTIS v6 has no structured coverage result.
