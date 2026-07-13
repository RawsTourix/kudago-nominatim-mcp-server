# MCP API sources

Checked on 2026-07-13 against official provider documentation only.

| Provider | API/version | Operations | Checked |
|---|---|---|---|
| [KudaGo](https://docs.kudago.com/api/) | Public API v1.4 | events, places, movies, showings, news, lists, categories, locations | 2026-07-13 |
| [Nominatim](https://nominatim.org/release-docs/latest/api/Search/) | Search API 5.3.2 | `/search` | 2026-07-13 |
| [Transitous](https://transitous.org/api/) / [MOTIS](https://raw.githubusercontent.com/motis-project/motis/refs/tags/v2.10.2/openapi.yaml) | Stable MOTIS 2, OpenAPI tag v2.10.2 | `GET /api/v6/plan` | 2026-07-13 |
| [OpenRouteService](https://giscience.github.io/openrouteservice/api-reference/endpoints/directions/requests-and-return-types) | Directions v2, backend docs 9.7.1 | `POST /v2/directions/{profile}/json` | 2026-07-13 |
| [FastMCP](https://gofastmcp.com/servers/tools) | v3 | tools, schema metadata, annotations, version | 2026-07-13 |

The Transitous production API page currently links its interactive docs to the
MOTIS `v2.10.2` tagged OpenAPI definition. That exact tag is recorded here;
the route application command still targets the stable versioned `/api/v6`
operation.

## Public field mapping

| MCP field | Official source / upstream field | Internal transformation | MCP restriction / difference |
|---|---|---|---|
| `resolve_location.place` | Nominatim `q` | `query` | 1–500 characters |
| `country_codes` | Nominatim `countrycodes` | lowercase list to CSV; null stays null | max 10 alpha-2 codes; no default `ru` filter |
| `language` | Nominatim `accept-language` | `accept_language` | 1–100 characters; default `ru` |
| `resolve_location.limit` | Nominatim `limit` | direct | 1–10 instead of upstream 40 |
| `place` | application free-form location resolver | `place_query` | exactly one location source |
| `city` | KudaGo locations + application resolver | `place_query` | city name, not arbitrary address |
| `location_slug` | KudaGo v1.4 `locations[].slug` | `location` | committed snapshot enum |
| `coordinates.latitude` | KudaGo `lat`; routing latitude | nested model to scalar | -90 to 90; latitude is first |
| `coordinates.longitude` | KudaGo `lon`; routing longitude | nested model to scalar | -180 to 180; longitude is second |
| `radius_km` | KudaGo `radius` in metres | multiply by 1000 and round to integer | 0.1–100 km; required with coordinates |
| `date`, `date_from`, `date_to` | KudaGo `actual_since`, `actual_until` | local calendar boundaries to UTC Unix timestamps | single date or inclusive range, max 31 days |
| `timezone` | MCP calendar semantics | IANA/fixed offset to aware datetime | default `+03:00` |
| event `categories` | KudaGo v1.4 event-category slugs | enum list to CSV | separate committed event enum |
| place `categories` | KudaGo v1.4 place-category slugs | enum list to CSV | separate committed place enum |
| `free_only` | KudaGo `is_free` | renamed | nullable boolean; hidden raw name |
| `page` | KudaGo `page` | direct | 1–10000 |
| search `limit` | KudaGo `page_size` | renamed | 1–20 instead of upstream 100 |
| `cinema_id` | KudaGo movie `place` / showing `place_id` | renamed to application `place_id` | integer >= 1 |
| `movie_id` | KudaGo movie-specific showings ID | direct | integer >= 1 |
| `premiering_only` | KudaGo `premiering_in_location` | renamed | nullable boolean |
| `only_current` | KudaGo news `actual_only` | renamed | default true |
| `item_type` | KudaGo detail resource type | `guide` maps to application `list` | six agent-facing enum values |
| `item_id` | KudaGo object ID | maps to `object_id` | 1–100 characters |
| `include_comments` | KudaGo comment endpoints | direct after applicability validation | only event/place/movie/news/guide |
| `include_showings` | KudaGo movie showings | direct after applicability validation | only movie |
| routing `origin`, `destination` | MOTIS `fromPlace`/`toPlace`; ORS `coordinates` | MOTIS uses `lat,lon`; ORS uses `[lon,lat]` through existing services | distinct nested coordinate points |
| `departure_time` | MOTIS `time`, `arriveBy=false` | aware datetime plus flag | mutually exclusive with arrival time |
| `arrival_time` | MOTIS `time`, `arriveBy=true` | aware datetime plus flag | mutually exclusive with departure time |
| `modes` | MOTIS `transitModes` | lower-case agent enum to existing `TransitMode` | no raw `TRANSIT` or non-transit modes |
| `max_transfers` | MOTIS `maxTransfers` | direct | 0–10 |
| transit `limit` | MOTIS `numItineraries` | renamed | 1–5, default 3 |
| street `mode` | ORS path profile | public enum to the application route enum; the existing service maps that to foot-walking/cycling-regular/driving-car | provider profile hidden |

Technical upstream fields such as tags, KudaGo language controls, `page_size`,
raw timestamps, MOTIS search-window tuning and ORS geometry flags are not
public MCP fields. The application/REST contracts retain them.
