# KudaGo + Nominatim MCP Server

MCP server for discovering concerts, theater performances, exhibitions, lectures,
festivals, movies, movie showings, venues and other leisure activities.

The server combines:

- KudaGo Public API v1.4 for events, venues, movies, showings, news, lists and
  reference data.
- OpenStreetMap Nominatim-compatible geocoding for resolving natural place names
  into coordinates.

It is designed as a convenient tool layer for AI agents: an agent can ask for
events near a district, town, landmark or city name even when that place is not a
native KudaGo location slug.

This project is an MVP. By default it uses the public Nominatim service with a
1 request per second local throttle (`NOMINATIM_MIN_INTERVAL_SECONDS=1.0`), which
is roughly 60 geocoding requests per minute. That is useful for prototypes and
personal workflows, but not enough for high-volume production traffic.

## Features

- Search events by KudaGo location slug, natural place name or explicit
  coordinates.
- Search concerts, theater, exhibitions, lectures, festivals and free events via
  KudaGo categories and tags.
- Search venues near a location or within a radius.
- Search movies and movie showings.
- Resolve cities, towns, districts and landmarks through Nominatim.
- Detect ambiguous places instead of silently picking the first geocoding result.
- Retrieve KudaGo news, curated lists, object details, comments and reference
  dictionaries.
- Return structured JSON envelopes that are easy for AI agents to inspect.
- Run as an MCP server over stdio or Streamable HTTP.

## Architecture

```text
AI agent / MCP client
        |
        v
FastMCP tools
        |
        v
Location-aware leisure search
        |
        +-- kudago_mcp_client / KudaGoHttpClient
        |   +-- events, places, movies, showings, news, lists, references
        |
        +-- kudago_nominatim_geo.resolve_geo_for_kudago
            +-- nominatim_geo_client / NominatimHttpClient
                +-- place resolution and ambiguity detection
```

The MCP layer exposes a small set of tools and normalizes common user intents.
KudaGo is responsible for leisure data. Nominatim is responsible for resolving
plain-language place names into coordinates when KudaGo does not have a direct
location match.

Geo resolution follows this order:

1. Use `location` directly when a KudaGo slug such as `msk` or `spb` is provided.
2. Try to match `place_query` against KudaGo locations by slug or localized name.
3. Use Nominatim for `place_query` and pass the resulting `lat`, `lon` and
   `radius` to KudaGo endpoints that support coordinates.
4. Return an explicit `geo.status` such as `ambiguous_place`,
   `place_not_found` or `unsupported` when the server cannot safely continue.

## Example Queries

- Find concerts in Moscow next week.
- What theater performances are available tomorrow in Saint Petersburg?
- What events are happening in Nakhabino?
- I want to watch an action movie near TRK Shchuka.
- Suggest free science and technology events this weekend.
- Find museums or exhibition venues near this address.
- Show movie showings in a specific cinema.

## Available Tools

All tools return a JSON object with at least:

- `status`: `ok` or `error`.
- `tool`: the tool name.
- `data`: the upstream KudaGo or Nominatim response when the call succeeds.
- `geo`: geo resolution details for location-aware tools.

### `resolve_place`

Resolve a natural place name through Nominatim.

Useful when an agent needs coordinates, wants to check ambiguity, or needs to ask
the user which place they meant.

Parameters:

- `query`: place name, address, district or landmark.
- `countrycodes`: optional comma-separated country filter, defaults to `ru`.
- `limit`: number of candidates from 1 to 10.
- `accept_language`: response language, for example `ru` or `en`.

### `reference`

Fetch KudaGo dictionaries.

Supported `kind` values:

- `event_categories`
- `place_categories`
- `locations`
- `location`
- `agent_roles`
- `agent_role`

Use this before category, place-category, location or role filtering when the
agent needs exact KudaGo slugs or IDs.

### `search`

Full-text KudaGo search.

Parameters include:

- `query`: text query.
- `ctype`: `event`, `place`, `news` or `list`.
- `location`: KudaGo location slug.
- `place_query`: natural place name resolved by KudaGo or Nominatim.
- `lat`, `lon`, `radius`: explicit geo search.
- `is_free`, `include_inactual`, `expand`, `page`, `page_size`, `lang`.

Use this for text search such as "jazz", "museum" or "where to go". For strict
date/category filtering, prefer `events`.

### `events`

Search KudaGo events with deterministic filters.

Parameters include:

- `location` or `place_query`.
- `lat`, `lon`, `radius`.
- `actual_since`, `actual_until`: Unix timestamp or ISO 8601 date/time.
- `categories`, `tags`: comma-separated KudaGo slugs.
- `is_free`.
- `fields`, `expand`, `order_by`, `page`, `page_size`, `lang`.

### `events_of_the_day`

Fetch KudaGo editorial events of the day.

This tool requires a KudaGo location slug or a `place_query` that can be matched
to a KudaGo location. It does not use Nominatim coordinates.

### `places`

Search KudaGo venues and places.

Parameters include:

- `location` or `place_query`.
- `lat`, `lon`, `radius`.
- `categories`, `tags`.
- `has_showings`: useful for cinemas.
- `fields`, `expand`, `page`, `page_size`, `lang`.

### `movies`

Search KudaGo movies.

Parameters include:

- `location` or `place_query`.
- `actual_since`, `actual_until`.
- `premiering_in_location`.
- `place_id`, `page`, `page_size`, `lang`.

This tool works with KudaGo location slugs. It does not use Nominatim
coordinates.

### `movie_showings`

Search movie showings, show showings for a movie, or fetch one showing.

Modes:

- Pass `showing_id` for `/movie-showings/{id}/`.
- Pass `movie_id` for `/movies/{id}/showings/`.
- Pass neither for `/movie-showings/`.

Parameters include:

- `location` or `place_query`.
- `actual_since`, `actual_until`.
- `place_id`, `is_free`, `page`, `page_size`, `lang`.

This tool works with KudaGo location slugs. It does not use Nominatim
coordinates.

### `news`, `lists`, `agents`, `object`, `comments`

Additional KudaGo tools:

- `news`: city news and fresh KudaGo materials.
- `lists`: curated KudaGo lists and selections.
- `agents`: people and organizations associated with KudaGo entities.
- `object`: details for `event`, `news`, `list`, `place`, `movie`,
  `movie_showing`, `agent`, `agent_role` or `location`.
- `comments`: comments for `event`, `news`, `list`, `place` or `movie`.

## Ambiguous Locations

The server does not silently choose a location when multiple candidates exist.

Example input:

```text
Alekseevka
```

Example response shape:

```json
{
  "status": "error",
  "tool": "events",
  "message": "Several Nominatim candidates were found. Pick one and call the tool again with explicit lat, lon and radius.",
  "geo": {
    "status": "ambiguous_place",
    "kind": "none",
    "candidates": [
      {"display_name": "Alekseevka, Belgorod Oblast, Russia"},
      {"display_name": "Alekseevka, Samara Oblast, Russia"},
      {"display_name": "Alekseevka, Republic of Bashkortostan, Russia"}
    ]
  }
}
```

An agent should show the candidates to the user, ask for clarification, and then
call the target tool again with explicit `lat`, `lon` and `radius`.

## Installation

Clone the repository and install it into a Python 3.11+ environment:

```bash
git clone <repo-url>
cd kudago-nominatim-mcp-server
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

The dependencies in `requirements.txt` are sufficient to run the MCP server.
For development and tests, install the project with its optional development
dependencies:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

## Running

Stdio is the default transport and is the best fit for most MCP desktop/client
integrations:

```bash
python kudago_nominatim_mcp_server.py
```

The same command with an explicit transport:

```bash
python kudago_nominatim_mcp_server.py --transport stdio
```

Streamable HTTP:

```bash
python kudago_nominatim_mcp_server.py --transport http --host 127.0.0.1 --port 8010 --path /mcp/
```

Transport priority is:

```text
CLI arguments > environment variables > defaults
```

## MCP Configuration

Stdio example:

```json
{
  "name": "kudago_nominatim",
  "alias": "kudago",
  "connect_type": "executable",
  "executable": "python",
  "args": ["/absolute/path/to/kudago_nominatim_mcp_server.py"],
  "env": {
    "KUDAGO_LANG": "ru",
    "NOMINATIM_USER_AGENT": "your-app-name/0.1.0 (your-email-or-url)",
    "NOMINATIM_EMAIL": "your-email@example.com",
    "NOMINATIM_MIN_INTERVAL_SECONDS": "1.0",
    "NOMINATIM_COUNTRYCODES": "ru"
  },
  "enabled": true
}
```

Streamable HTTP example:

```json
{
  "name": "kudago_nominatim",
  "alias": "kudago",
  "connect_type": "streamable_http",
  "url": "http://127.0.0.1:8010/mcp/",
  "headers": {},
  "enabled": true
}
```

When using Streamable HTTP, start the server separately before starting the MCP
client.

## Configuration

Environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `KUDAGO_BASE_URL` | `https://kudago.com/public-api/v1.4/` | KudaGo API base URL. |
| `KUDAGO_LANG` | `ru` | Default KudaGo response language. |
| `NOMINATIM_BASE_URL` | `https://nominatim.openstreetmap.org/` | Nominatim-compatible API base URL. |
| `NOMINATIM_USER_AGENT` | `nominatim-geo-client/0.1.0` | Application User-Agent sent to Nominatim. Set a real contact value. |
| `NOMINATIM_REFERER` | empty | Optional Referer header for Nominatim. |
| `NOMINATIM_EMAIL` | empty | Optional email parameter passed to Nominatim search. |
| `NOMINATIM_MIN_INTERVAL_SECONDS` | `1.0` | Local delay between Nominatim requests. |
| `NOMINATIM_COUNTRYCODES` | `ru` | Default country filter for geocoding. |
| `DEFAULT_RADIUS` | `50000` | Fallback radius in meters for coordinate searches. |
| `TRUST_ENV` | `true` | Whether HTTP clients trust proxy environment variables. |
| `LOG_DIR` | `logging` | Directory for log files. |
| `DEBUG` | `0` | Enables debug logging when truthy. |
| `MCP_TRANSPORT` | `stdio` | `stdio` or `http`. |
| `MCP_HOST` | `127.0.0.1` | HTTP host. |
| `MCP_PORT` | `8010` | HTTP port. |
| `MCP_PATH` | `/mcp/` | Streamable HTTP path. |

## Limitations

- The default setup uses the public Nominatim service and is intentionally
  throttled to one geocoding request per second. See the public
  [Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/).
- For production, high traffic or strict availability requirements, use a
  self-hosted Nominatim instance or another geocoding provider behind a
  compatible endpoint.
- Coordinate search is available only for KudaGo endpoints that support
  `lat`, `lon` and `radius`; several KudaGo endpoints require a native location
  slug.
- Movie showings depend on KudaGo coverage for a city, cinema and date range.
- Event availability, categories, tags and prices depend on KudaGo data quality.
- This server does not buy tickets, reserve seats or verify live ticket
  availability.

## Roadmap

- Self-hosted geocoding deployment examples.
- Optional provider adapters for other geocoding APIs.
- Additional leisure data sources.
- Ticket availability signals where a reliable data source exists.
- Route planning between events.
- Travel time and cost estimation.
- Response normalization layer on top of raw KudaGo objects.

## Notes for Production Use

Treat the current server as an MVP integration layer. It is a good fit for local
AI-agent tooling, demos and controlled low-volume workflows. For production,
replace the public Nominatim endpoint, configure a real User-Agent/contact email,
add observability and decide how aggressively you want to cache geocoding
results.
