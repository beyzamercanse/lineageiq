# LineageIQ — Security Model

## Read-only agent surface
The agent can only touch data through registered read-only tools. There is no write path from the
agent to the database.

### SQL tool (`run_readonly_sql`)
- Parsed with `sqlglot` before execution.
- Only a single `SELECT` (safe CTEs allowed). Rejected: INSERT, UPDATE, DELETE, DROP, ALTER,
  TRUNCATE, COPY, GRANT, transaction-control, multiple statements, comments-as-smuggling.
- Schema allowlist + table allowlist enforced from the parsed AST.
- Row limit, query-length limit, execution timeout.
- Runs under a dedicated PostgreSQL read-only role (`lineageiq_ro`) as defense in depth.
- Returns bounded result sets with truncation indicator.

### Other tools
`search_logs`, `query_lineage`, `search_historical_incidents`, `inspect_pipeline_runs`,
`inspect_schema` validate inputs, bound output sizes, and never return secrets.

## Prompt-injection defense
Tool output (logs, table values, incident text) is treated as untrusted data. The agent is
instructed never to follow instructions embedded in tool results.

## Secrets
- Secrets only via environment (`.env`, never committed). `.env.example` documents the variables.
- Never log API keys, DB passwords, or unredacted prompts containing secrets.
- API error responses never expose stack traces.

## Data
All data is synthetic. No real PII. The fictional company is AtlasCommerce.

## Tests
`backend/tests/security/` asserts the SQL tool rejects every forbidden statement class and
out-of-allowlist / oversized queries.
