# KudaGo + Nominatim MCP transport selector

Drop-in версия для `internet-search-bot/src/mcp/`.

Архитектура сервера:

```text
tools / business logic
        ↓
FastMCP instance
        ↓
transport selector at startup
        ├─ stdio
        └─ streamable-http
```

Функционал tools не менялся: добавлен только выбор транспорта при запуске.

## Runtime-файлы для `src/mcp/`

```text
kudago_mcp_client/
nominatim_geo_client/
kudago_nominatim_config.py
kudago_nominatim_geo.py
kudago_nominatim_mcp_server.py
kudago_nominatim_utils.py
```

## Stdio: дефолтный режим

```bash
python src/mcp/kudago_nominatim_mcp_server.py
```

То же явно:

```bash
python src/mcp/kudago_nominatim_mcp_server.py --transport stdio
```

## Streamable HTTP

```bash
python src/mcp/kudago_nominatim_mcp_server.py --transport http --host 127.0.0.1 --port 8010 --path /mcp/
```

Также поддерживаются env-переменные:

```env
MCP_TRANSPORT=stdio
MCP_HOST=127.0.0.1
MCP_PORT=8010
MCP_PATH=/mcp/
```

Приоритет: CLI args > env > defaults.

## Config snippets

- `mcp_config_stdio_snippet.json` — старое подключение через executable/stdin/stdout.
- `mcp_config_streamable_http_snippet.json` — подключение к уже запущенному HTTP MCP-серверу.

Для Streamable HTTP сервер нужно запустить отдельно до старта клиента:

```bash
python src/mcp/kudago_nominatim_mcp_server.py --transport http --host 127.0.0.1 --port 8010
```

А в `mcp.config` подключить URL:

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

## Важное

- Для локального HTTP используй `127.0.0.1`, не `0.0.0.0`.
- Не включай одновременно stdio и HTTP-конфиг одного и того же сервера, иначе получишь дубликаты tools.
- `NOMINATIM_USER_AGENT` лучше заменить на реальный контакт/URL проекта.
