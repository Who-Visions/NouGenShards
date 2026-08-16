# Cloud Complex Example

This demonstrates a `CLOUD_COMPLEX` task routed to Gemini 3.5 Pro/Flash in the cloud.

## Task Input
```text
We are migrating our application database schema from MySQL to PostgreSQL. Walk through all files in the project and identify any raw SQL queries that use MySQL-specific syntax (such as backticks, LIMIT offsets, or GROUP BY anomalies), and prepare a migration blueprint.
```

## Routing Decision
```text
Classification: CLOUD_COMPLEX
Reason: Multi-file schema migration analysis requires deep project-wide reasoning and Postgres syntax compatibility checks.
```
