# Local Structured Routing Example

This demonstrates a `LOCAL_STRUCTURED` task routed to Gemma 4 E2B locally.

## Task Input
```text
Extract all unique error codes from the following log:
[2026-06-04 12:00:01] ERROR: DB_CONNECTION_TIMEOUT in connection pool 5
[2026-06-04 12:00:02] ERROR: DB_CONNECTION_TIMEOUT in connection pool 5
[2026-06-04 12:00:15] WARN: SLOW_QUERY in get_users (took 1500ms)
[2026-06-04 12:01:00] ERROR: USER_AUTH_FAILED for user_id 20042
```

## Local Model Prompt
```text
Extract all unique error/warning codes from the log input. Return a JSON structure.
```

## Generated Output
```json
{
  "DB_CONNECTION_TIMEOUT": {
    "type": "ERROR",
    "count": 2
  },
  "SLOW_QUERY": {
    "type": "WARN",
    "count": 1
  },
  "USER_AUTH_FAILED": {
    "type": "ERROR",
    "count": 1
  }
}
```
