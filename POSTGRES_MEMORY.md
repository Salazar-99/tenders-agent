# Postgres Memory Design

ADK supports persistent session state in Postgres through
`DatabaseSessionService`, but it does not currently ship a Postgres-backed
memory service. To use Postgres for memory, we would implement ADK's
`BaseMemoryService` in this app.

The service would ingest useful conversation events from completed sessions
into a dedicated memory table. A practical schema would include:

```sql
CREATE TABLE agent_memories (
  id uuid PRIMARY KEY,
  app_name text NOT NULL,
  user_id text NOT NULL,
  session_id text,
  author text,
  content jsonb NOT NULL,
  text text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
```

For simple recall, add a generated `tsvector` column or expression index and
search with Postgres full-text search. For semantic recall, enable `pgvector`,
store an embedding per memory row, and search by vector distance scoped to
`app_name` and `user_id`.

The ADK implementation would provide:

- `add_session_to_memory(session)`: extract text from session events and insert
  rows into `agent_memories`.
- `add_events_to_memory(...)`: insert incremental event memories after each
  turn when we do not want to reprocess the whole session.
- `search_memory(app_name, user_id, query)`: run full-text or vector search and
  return ADK `MemoryEntry` objects.

This can live alongside the existing Postgres session tables, but it should use
its own table and indexes because session history is an audit log while memory
is a retrieval-optimized view of facts worth recalling.
