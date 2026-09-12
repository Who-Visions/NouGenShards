---
name: nougen-cloudflare
description: Cloudflare for NouGen fleet agents. Use whenever a task mentions Cloudflare, Workers, Workers AI, wrangler, Vectorize, Workflows, Hyperdrive, neurons, the free inference lane, Kaedra cloud fallback, or deploying the Domain wiki. Recall the vault shards first, fetch llms.txt only when the shard is older than the question, and route inference through the workers-ai free lane. Not for DNS, WAF, Zero Trust, or Tunnel work.
---

# NouGen Cloudflare Lane

Workers AI is a free inference lane beside ollama, ollama-cloud, openrouter and hf.
This skill is the doc map, the decision facts, and the two probes that prove it works.

## When to use / when not to

Use for: picking a Workers AI model, budgeting neurons, wiring tool calling, the
Kaedra cloud fallback, wrangler deploys of the Domain wiki, and any
"should we use Workflows / Vectorize / Hyperdrive" question.

Do not use for: DNS, WAF, Zero Trust, Tunnel, or Pages (the `cloudflare:*` plugin
skills cover those). Do not use for local-only inference; that is `fleet-draft`.

## Doc map: recall before you fetch

All shards live on db_index 1. Pull the summary first, the body only if needed.

| Topic | Shard id |
|---|---|
| Workers overview | 1 |
| Workers AI overview | 3 |
| Pricing | 5 |
| Limits | 6 |
| Model catalog | 7 |
| Prompting | 8 |
| REST API | 9 |
| Workers binding | 11 |
| Workflows | 12 |
| Vectorize | 13 |
| Hyperdrive | 14 |
| Next.js on Workers | 15 |

Live index, fetch only when a shard is older than the question needs:

- https://developers.cloudflare.com/workers/llms.txt
- https://developers.cloudflare.com/workers-ai/llms.txt

Rule: official docs beat model memory. Shards are dated snapshots. Re-fetch before
quoting a rate, a limit, or a model id in anything the GM will act on.

## Facts that drive decisions (from the shards, dated snapshots)

- Free allowance: 10,000 Neurons per day on both Free and Paid plans. Overage is
  $0.011 per 1,000 Neurons. Counter resets at 00:00 UTC.
- Rate limits: text generation 300 rpm; frontier models 20 rpm.
- `wrangler dev` still bills neurons. Local dev is not a free sandbox.
- 19 function-calling models in the catalog, 12 of them on the free tier.
- Default pick: `@cf/google/gemma-4-26b-a4b-it`. Tool calling, vision, 256k context,
  9,091 in / 27,273 out neurons per million tokens.
- Runners-up: `qwen3-30b-a3b-fp8`, `granite-4.0-h-micro`, `gpt-oss-20b`.
- Paid-only (skip on the free lane): kimi-k2.6, kimi-k2.7-code, glm-5.2, glm-5.3,
  glm-5.3-flash, deepseek-v4-flash-0731, deepseek-v4-pro-0813.
- Embeddings: `bge-m3`, multilingual, 1075 neurons per million tokens.
- Scoped messages (system / user / assistant) map 1:1 to ollama message lists, so a
  single PROMPT shard serves both lanes.
- Gemma 4: pass `chat_template_kwargs: {"enable_thinking": false}` unless you want
  reasoning tokens billed.
- Response envelope is `{result, success, errors, messages}`. Check `success`,
  not just HTTP 200; a 200 with `success: false` is a failure.

## The fleet lane

Client module: `src/nougen_shards/workers_ai_client.py`.

- `WorkersAIClient.chat(messages, tools=...)` for one-shot and tool-calling chat.
- `kaedra_cloud_fallback()` when the local Kaedra surface is down.
- Neuron budget guard stops the lane before the daily allowance is spent.

Env vars (resolve env, then config, then probe; constants are logged fallbacks):

| Var | Meaning |
|---|---|
| `NOUGEN_CF_ACCOUNT_ID` | account id, from Keymaker |
| `NOUGEN_CF_AI_TOKEN` | Workers AI token, from Keymaker |
| `NOUGEN_CF_AI_BASE_URL` | REST base, override for proxies |
| `NOUGEN_CF_AI_MODEL` | default `@cf/google/gemma-4-26b-a4b-it` |
| `NOUGEN_CF_AI_TIMEOUT_S` | request timeout |
| `NOUGEN_CF_AI_DAILY_NEURONS` | budget guard, default 10000 |

Credential rule 0.3: the token comes from Keymaker (`agent_secrets.db`, DPAPI
wrapped 1 to 3 layers, unwrap in a loop). Reference it by SHA-256 12-hex
fingerprint only. Never ask Dave first, never paste it into chat, logs, or shards.

## Product decision table

| Product | Decision |
|---|---|
| Workers AI | Adopted as a free lane. |
| Workflows | Candidate to back Kaedra's autonomous tool loop: `step.do` per tool call, `waitForEvent` for GM gates. War game required before any build. |
| Vectorize | Candidate edge mirror for the vault's embeddings. Verify limits first. Metadata must carry `id@db` because shard ids are node-local. |
| Hyperdrive | No fit while grid DBs are SQLite. |
| Next.js | Keep static export plus wrangler assets for the wiki. `vinext` is beta; do not migrate. |

## Gotchas

- wrangler uploads can fail with `UND_ERR_SOCKET` when the project path crosses a
  symlink: wrangler walks to the filesystem root and stats every directory. Stage the
  build outside any symlinked tree before deploying.
- One builder per directory. Two concurrent `next build` runs corrupt `.next` and `out`.
- Use `pnpm run deploy`, not bare `pnpm deploy` (that is a workspace command).
- Kaedra's served surface is the `kaedracode` Modelfile on its host node, not the local `agents.py`.

## Probes

```bash
# PONG sanity call on the default model
curl -s "${NOUGEN_CF_AI_BASE_URL:-https://api.cloudflare.com/client/v4}/accounts/${NOUGEN_CF_ACCOUNT_ID}/ai/run/${NOUGEN_CF_AI_MODEL:-@cf/google/gemma-4-26b-a4b-it}" \
  -H "Authorization: Bearer ${NOUGEN_CF_AI_TOKEN}" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Reply with exactly PONG"}],"chat_template_kwargs":{"enable_thinking":false}}' \
  | python -c "import sys,json; r=json.load(sys.stdin); print(r['success'], r['result'].get('response'))"

# One-shot tools= chat on the default model
curl -s "${NOUGEN_CF_AI_BASE_URL:-https://api.cloudflare.com/client/v4}/accounts/${NOUGEN_CF_ACCOUNT_ID}/ai/run/${NOUGEN_CF_AI_MODEL:-@cf/google/gemma-4-26b-a4b-it}" \
  -H "Authorization: Bearer ${NOUGEN_CF_AI_TOKEN}" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"What is the weather in Brooklyn?"}],
       "tools":[{"type":"function","function":{"name":"get_weather","description":"Current weather for a city",
       "parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}],
       "chat_template_kwargs":{"enable_thinking":false}}' \
  | python -c "import sys,json; r=json.load(sys.stdin); print(r['success'], r['result'].get('tool_calls'))"
```

Expect `True PONG` and `True [{'name': 'get_weather', ...}]`. `success: false` with
an `errors` list means auth, model id, or budget; read the error shape before retrying.
