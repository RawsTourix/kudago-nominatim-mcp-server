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

`reference.kind` supports `event_categories`, `place_categories`, `locations`,
and `location`. The latter requires `slug`.

`object.object_type` supports `event`, `place`, `movie`, `movie_showing`,
`news`, `list`, `agent`, `agent_role`, and `location`. Use `include_comments`
where comments are supported and `include_showings` for a movie.

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

## Smoke checks

```powershell
python scripts/test_mcp_inmemory.py
python scripts/test_mcp_stdio.py
python scripts/test_mcp_http.py
```
