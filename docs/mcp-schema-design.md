# MCP schema design

## REST and MCP are different contracts

FastAPI exposes detailed application request models and low-level provider
filters. The MCP version 2 facade exposes ten user intentions with compact
results. A tool may rename fields, change units, convert dates, hide technical
parameters and serialize the saved command output without changing the REST
endpoint or application command.

The mapping is documented in [mcp.md](mcp.md). Old MCP names are removed rather
than retained as aliases, so the model sees one unambiguous action per intent.

## Field descriptions and constraints

Tool docstrings explain purpose, when to use the tool and its main result
limitation. Argument documentation lives on `Annotated[..., Field(...)]` so it
appears beside the property in the actual FastMCP JSON Schema.

Every property describes its meaning, format, units, important combinations
and default. Numeric bounds, string lengths, patterns and collection sizes are
machine-readable. Standard Pydantic coercion remains enabled, while finite
sets and cross-field combinations are strict.

## Enum strategy

`EventCategory`, `PlaceCategory` and `KudaGoLocationSlug` are built from
`app/mcp/reference_data/kudago_v1_4.json`. This is a committed KudaGo v1.4
reference snapshot, not an immutable protocol standard. The generator is
manual and deterministic; application startup never depends on KudaGo being
available.

Detail types, public-transport modes and street modes are small static enums.
Provider-specific routing profiles remain internal.

## Location strategy

Event/place discovery validates exactly one location source:

```text
place
location_slug
coordinates + radius_km
```

The mapper converts `radius_km` to integer metres and nested coordinates to the
application `lat`/`lon` fields. City-only KudaGo operations validate exactly
one of a free-form `city` and a snapshot `location_slug`.

`resolve_location` is international by default. Omitted `country_codes` maps
to `countrycodes=None`, overriding the REST model's historical `ru` default.

## Date strategy

Calendar inputs accept a single date or a complete inclusive range of at most
31 days. IANA timezones and fixed UTC offsets are accepted. The mapper converts
local start-of-day and end-of-day boundaries to UTC Unix timestamps for
`actual_since` and `actual_until`.

Events require a time window. Movie and showing searches allow no window so
the existing application defaults remain available.

## Response compaction

The complete `CommandOutput.result_payload` is saved through the existing job,
result and upstream-call repositories before any MCP-specific serialization.
Search serializers keep identification, short descriptive facts, coordinates,
semantic flags and `details_ref`, while dropping body text, HTML, images,
provider cursors and unrelated historical occurrences.

Search/list data is capped at 64 KiB; routing data is capped at 128 KiB. Caps
remove complete items or complete route alternatives from the end. They never
mutate the saved command result.

## Semantic flags

The facade distinguishes data existence from schedule or route verification:

- places are not scheduled events;
- movie records are not cinema showings;
- showing records are explicit KudaGo showings;
- an event is schedule-verified only relative to its requested window;
- a route is verified only when the provider result is `ok` and routes exist.

These flags describe provider evidence, not realtime freshness or universal
coverage.

## Breaking changes

The MCP version 1 tool names and `reference` workflow are removed. FastAPI,
application command names, queues, tables, migrations, repositories, external
clients and persisted full job history are unchanged.
