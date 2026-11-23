# Context7 — Current Library Docs

Context7 ([context7.com](https://context7.com)) is a docs service that
returns **current library documentation** for a question or a library ID.
Use it whenever the answer depends on a current library version or a
recently changed API — framework versions, new releases, changed defaults,
new flags — instead of answering from training memory. Training memory goes
stale; Context7 returns the docs as published now, with the library version
named in the result.

Skip it for general concepts or stable knowledge that does not depend on a
version.

## Status — read this first

**A live lookup through the fleet tools is BLOCKED on a missing Keymaker
entry (2026-11-22).** The key name is `CONTEXT7_API_KEY`; the entry does
not exist in the Keymaker yet, and it is pending the operator adding it.
Until then every fleet tool below degrades cleanly to a named missing-key
error (see [Errors](#errors)) — no crash, no leak, no silent empty
answer. Do not work around this by pasting a key anywhere; keys go into
the Keymaker, never into chat, files, or commits.

What *is* verified live (2026-11-22):

- The Mister Who connection (`custom.context7`) works: `usage` returned
  200, free plan, 0 of 1000 requests used; `search` for Next.js 15 caching
  returned current docs from `/vercel/next.js/v15.5.28`.
- The fleet tools are unit-tested: `tests/test_mcp_context7.py`, 16 tests,
  all passing; tenancy tests 29 passed. Those tests stub the transport —
  **no live fleet lookup has succeeded yet**, because the Keymaker entry
  is missing. A live fleet lookup is untested until the key lands.

## Setup

Two separate keys/connections exist. Do not confuse them.

### 1. Mister Who's connection (`custom.context7`)

Mister Who talks to Context7 directly through the registered connector.
Key held in Muse secure storage (bearer header, host `context7.com`,
format `ctx7sk*`); never in a file. Helper and doc:

- Helper: `~/workspace/custom-connectors/custom.context7/bin/client.py`
  (`search`, `resolve`, `docs`, `usage`)
- Connector doc: `~/workspace/custom-connectors/custom.context7/CONNECTOR.md`
- Skill: `~/workspace/custom-skills/context7/SKILL.md`

Free plan: **1000 requests/month**, usage resets on the 1st of the month.
The `usage` call itself does not count as a request.

### 2. Fleet MCP tools (this repo)

The fleet tools read their key from the Keymaker **at call time** with
`keymaker.get_secret("CONTEXT7_API_KEY")` — never cached, never stored,
never logged, never hard-coded. The entry is **pending** (see Status
above). Once the operator adds it under exactly that name, the tools work
with no code change.

Keymaker-first is the house rule: check the Keymaker before asking anyone
for a key. The operator is the only person who can add this entry.

## The three surfaces

| Surface | Where | For whom |
|---|---|---|
| Skill path | `~/workspace/custom-skills/context7/SKILL.md` + the `custom.context7` helper | Mister Who (this runtime), direct Context7 REST calls |
| Fleet MCP tools | `src/nougen_shards/context7.py` (thin client) + `src/nougen_shards/mcp.py` (tools) | Any fleet lane, through the one MCP server |
| Mister Who helper | `~/workspace/custom-connectors/custom.context7/bin/client.py` | Direct CLI use from this runtime |

All three hit the same Context7 API. The skill and the fleet tools share
the same two lookup flows below; only the auth path differs (secure
storage vs Keymaker).

## MCP design decision (2026-11-22)

**The native fleet tools ARE the Context7 MCP surface.** The official
remote Context7 MCP server (`https://mcp.context7.com/mcp`) was **not**
wired as a lane. Reasons:

- **One server, one auth path, one tenant label.** The fleet pattern for
  an external docs/research service is native tools in `mcp.py`
  delegating to a thin client module (`arxiv_radar`, `cloudflare`,
  `nougentube`). A remote MCP lane would be a second server with its own
  transport and its own bearer handling.
- **It would bypass the tenant gate.** The four tools are labelled
  `OWNER_ONLY` in `src/nougen_shards/tenant_policy.py`, so tenants can
  never spend the owner's Context7 quota. A remote lane has no
  tenant-policy label.
- **No Keymaker hook.** Fleet auth is Keymaker-first
  (`CONTEXT7_API_KEY` at call time). A remote MCP lane has no Keymaker
  hook, so its key would live outside the fleet's credential discipline.

Revisit only if the remote server gains something the native tools cannot
do; the decision, the reasons, and this pointer live in the module
docstrings of `src/nougen_shards/context7.py` and the comment block above
the tools in `src/nougen_shards/mcp.py`.

## Fleet MCP tools

All four return JSON strings. All four are `OWNER_ONLY`.

| Tool | What it does |
|---|---|
| `context7_search(query, libraries?)` | Search current docs by question; Context7 picks the libraries and returns ranked snippets. No resolve step needed. `libraries` is an optional list of name/ID hints, max 4. |
| `context7_resolve(library_name, query?)` | Resolve a library name (e.g. `next.js`) to its Context7 library ID. Optional `query` ranks the matches by topic. |
| `context7_docs(library_id, query, tokens=5000, language?)` | Fetch docs snippets for one library ID. `tokens` is the snippet budget (default 5000, ceiling 10000). `language` ranks examples for one language (e.g. `typescript`). |
| `context7_usage()` | Monthly usage for the key: plan, requests used, reset date. Free; does not count as a request. |

Client implementation: `src/nougen_shards/context7.py`
(`search_docs`, `resolve_library`, `fetch_docs`, `usage`).
Tests: `tests/test_mcp_context7.py`.

## Lookup flows

### Flow 1 — Search by question (fastest)

Use when the library is clear from the task and you want the best
matching snippets fast. One focused question per call; name the library
when you know it.

Fleet:

```python
context7_search(
    query="How do I cache in Next.js 15?",
    libraries=["next.js"],
)
```

Skill / helper equivalent:

```text
python3 ~/workspace/custom-connectors/custom.context7/bin/client.py search \
  --query "How do I cache in Next.js 15?" --library next.js
```

Repeat `--library` up to four times when the question spans more than
one library. Read the returned text and follow its source links for the
full page.

### Flow 2 — Resolve, then fetch docs for one library

Use when you need docs from one specific library, or you need to pick
between similar libraries. Resolve first, pick the ID whose title,
description, and version list match, then fetch with one focused
question per call.

Fleet:

```python
context7_resolve(library_name="next.js", query="caching")
context7_docs(library_id="/vercel/next.js", query="caching", tokens=5000)
```

Skill / helper equivalent:

```text
python3 ~/workspace/custom-connectors/custom.context7/bin/client.py resolve \
  --library-name next.js --query "caching"

python3 ~/workspace/custom-connectors/custom.context7/bin/client.py docs \
  --library-id /vercel/next.js --query "caching" --tokens 5000
```

Raise `tokens` above the 5000 default when the first answer is too thin;
lower it for a short answer. Add `language` when you want examples
ranked for one language.

## Version pinning

Pin the version when the user names one, or when the current docs differ
from the version in use. Write the pinned ID as
`/owner/repo/<version>` or `/owner/repo@<version>` and pass it as the
library ID:

```python
context7_docs(library_id="/vercel/next.js/v15.5.28", query="caching", tokens=1000)
```

Check the version list in the resolve result before pinning a version
that may not exist. Fall back to the unpinned ID when the pinned version
returns no docs.

## Errors

| Signal | Meaning | What to do |
|---|---|---|
| Missing-key error naming `CONTEXT7_API_KEY` and the Keymaker | The Keymaker entry does not exist yet. Expected until the operator adds it. | Stop. No live lookup is possible. Do not ask for the key value; the entry is pending with the operator. |
| `no_documentation_found` (HTTP 404) | No docs matched. | Treat as an **empty result**, not an error. Broaden the question or try a different library name. |
| `rate_limited` (HTTP 429) | Rate limit hit. | Honour `Retry-After`, back off, retry. |
| `service_unavailable` (HTTP 503) | Search failed. | Retry later. |
| `unauthorized` (HTTP 401) | Key rejected. | Check the `CONTEXT7_API_KEY` value in the Keymaker (fingerprint only — never print it). |
| `forbidden` (HTTP 403) | Access denied. | Check library access permissions or the plan. |
| HTTP 301 (skill/helper path) | Library moved. | Use the new library ID from `redirectUrl`. |

After a failed or timed-out call, check the current state with a read
before retrying — the first request may have completed. Redirects are
refused by the fleet client; a redirect means the endpoint needs
verifying, not following.

## Limits

- **Free plan: 1000 requests/month**, resetting on the 1st. Check
  `context7_usage()` before a heavy lookup run, and again if a run
  returns unexpected errors and the quota may be spent.
- `tokens` ceiling is 10000 per `context7_docs` call.
- `libraries` hints cap at 4 per `context7_search` call.
- The v3 search endpoint returns plain-text docs, not JSON; the client
  surfaces them under `result.text`.
- Without an API key the limits are lower; with the key they follow the
  plan.

## Presenting a result

Give the answer in plain words and **name the library and version the
docs came from**. Quote the exact snippet that settles the question and
link its source page. Say plainly when Context7 returned nothing, so the
reader knows the answer came from elsewhere.

## Files

- `src/nougen_shards/context7.py` — thin client (endpoints, key lookup,
  error mapping)
- `src/nougen_shards/mcp.py` — `context7_search`, `context7_resolve`,
  `context7_docs`, `context7_usage`
- `src/nougen_shards/tenant_policy.py` — all four labelled `OWNER_ONLY`
- `tests/test_mcp_context7.py` — 16 tests (transport stubbed; no live
  lookup)
- `docs/context7.md` — this file
