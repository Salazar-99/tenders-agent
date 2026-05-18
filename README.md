# tenders-agent
Tenders Agent for the QueryTenders Platform

## Development

Run the API locally:

```bash
uv run tenders-agent
```

Healthcheck:

```bash
curl http://localhost:8001/health
```

ADK session state is persisted in Postgres. Set `POSTGRES_URL` before starting
the service:

```bash
POSTGRES_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/adk_sessions
```

The app wires this URL into ADK's `DatabaseSessionService`, which stores
sessions, events, app state, and user state in Postgres.

`/query` requires `X-API-Key`. The service validates that key against the
backend Postgres `api_keys` table by hashing the raw key with SHA-256 and
checking that it is not revoked or expired. Configure the validation database
with either `API_KEY_POSTGRES_URL`, the backend-style `POSTGRES_ENDPOINT`,
`POSTGRES_USER`, and `POSTGRES_PASSWORD`, or `POSTGRES_URL`:

```bash
POSTGRES_ENDPOINT=postgres://sparktenders@localhost:5432/sparktenders
POSTGRES_USER=sparktenders
POSTGRES_PASSWORD=sparktenders
```

ClickHouse MCP configuration is read from the environment or `.env`:

```bash
CLICKHOUSE_MCP_COMMAND=mcp-clickhouse
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=
CLICKHOUSE_DATABASE=default
CLICKHOUSE_SECURE=false
CLICKHOUSE_VERIFY=false
CLICKHOUSE_CONNECT_TIMEOUT=30
CLICKHOUSE_SEND_RECEIVE_TIMEOUT=30
```
