# FastMCP transport

The FastMCP transport exposes the shared application command layer. It is
available as streamable HTTP at `/mcp` on the FastAPI application and as a
standalone stdio server:

```powershell
uvicorn app.main:app --reload --port 8011
python -m app.mcp
```

## Tools

| Tool | Purpose | Key parameters | Command |
|---|---|---|---|
| `resolve_place` | Resolve a free-form place with Nominatim | `query`, `countrycodes`, `limit` | `geo.resolve` |
| `events` | Search events | location or geo input, dates, categories, tags | `events.search` |
| `places` | Search places | location or geo input, categories, showings | `places.search` |
| `movies` | Search movies | `location`, `place_query`, `place_id`, dates | `movies.search` |
| `movie_showings` | Search cinema showings | location, movie/place ID, dates | `movie_showings.search` |
| `news` | Search news | `location`, `place_query`, `tags` | `news.search` |
| `lists` | Search editorial lists | `location`, `place_query`, `tags` | `lists.search` |
| `reference` | Read categories and locations | `kind`, optional `slug`, `lang` | `reference.get` |
| `object` | Read an object detail | `object_type`, `object_id`, include flags | `object.detail` |
| `transit_route` | Verified public transport journey | coordinate pair, time, transit modes | `routing.transit.plan` |
| `street_route` | Verified walking/cycling/driving route | coordinate pair, profile | `routing.street.plan` |

`reference.kind` supports `event_categories`, `place_categories`, `locations`,
and `location`. The latter requires `slug`. `locations` lists official KudaGo
slugs; it is not a whitelist of every searchable city. For another city,
settlement, district, address, or landmark, pass the free-form name as
`place_query` to `events` or `places`. Those tools check KudaGo locations first
and can fall back to Nominatim coordinates.

`object.object_type` supports `event`, `place`, `movie`, `movie_showing`,
`news`, `list`, `agent`, `agent_role`, and `location`. Use `include_comments`
where comments are supported and `include_showings` for a movie.

## Routing workflow

1. Call `resolve_place` for a textual origin or address.
2. Read destination coordinates from an event or an `object` detail result.
3. Call `transit_route` for trains, suburban rail, metro, buses, trams,
   ferries and transfers. Its itinerary already includes walking access,
   transfers and egress where Transitous supplies them.
4. Call `street_route` only for a separate walking, cycling or driving route.

Never use `street_route` to invent public transport stops, schedules or missing
transit legs. There is no automatic Transitous-to-OpenRouteService fallback.
The routing tools accept coordinates only; provider-specific profile names are
not part of their schemas.

## Response envelope

Successful calls return:

```json
{
  "status": "ok",
  "tool": "events",
  "job_id": "uuid",
  "result_status": "ok",
  "geo": null,
  "data": {},
  "meta": {}
}
```

Validation failures and execution errors return `status: "error"`, `tool`,
`error_type`, `message`, and a nullable `job_id`. A non-null job ID means the
execution can be inspected through the REST diagnostics endpoints:

```text
GET /api/v1/jobs/{job_id}
GET /api/v1/jobs/{job_id}/events
GET /api/v1/jobs/{job_id}/upstream-calls
```

For routing, inspect `result_status`: `ok` confirms a provider route,
`no_route` means none was found for the supplied query, and an envelope
`status: "error"` means execution did not complete. MOTIS v6 does not expose a
structured coverage-unavailable result, so do not interpret `no_route` as
proof that transport does not exist.

## Smoke checks

```powershell
python scripts/test_mcp_inmemory.py
python scripts/test_mcp_stdio.py
python scripts/test_mcp_http.py
```
