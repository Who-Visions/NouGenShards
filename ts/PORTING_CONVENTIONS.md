# NouGenShards TS Port — Conventions (binding for all port agents)

Source of truth: the Python module at `../src/nougen_shards/<name>.py`. Port 1:1.

## Rules
1. **Names**: keep Python `snake_case` function/field names and module file names exactly (e.g. `get_db_path`, `nougen_context.ts`). Mirror docstrings as JSDoc with `(TS mimic of <file>.py)` in the header.
2. **ESM**: `"module": "NodeNext"` — all relative imports MUST end in `.js` (e.g. `import * as core from "./core.js"`). Files live under `ts/src/`, compiled to `ts/dist/`.
3. **SQLite**: use built-in `node:sqlite` (`DatabaseSync`). Pattern: `conn.exec("PRAGMA busy_timeout=10000;"); conn.exec("PRAGMA journal_mode=WAL;")`. Rows: `prepare(...).get(...)/.all(...)` cast to `Record<string, any>`. COUNT queries: `SELECT COUNT(*) AS c`.
4. **HTTP**: global `fetch` with `AbortSignal.timeout(ms)`. Network-bound functions become `async`. Streaming: read `res.body.getReader()` + `TextDecoder`, write chunks with `process.stdout.write`.
5. **Strict TS**: must compile under `strict: true`. Use `Record<string, any>` for dict-shaped rows (type `Shard` from `core.js`). No `@ts-ignore` unless unavoidable.
6. **Errors**: Python `try/except: pass` → `try {