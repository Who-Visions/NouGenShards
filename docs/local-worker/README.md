# Local Worker Routing — Gemma 4 E2B as the grunt-work lane

**License: Apache-2.0** (see `LICENSE`). This subtree is deliberately **not** covered by the
Who Visions Source-Available License that governs the rest of this repository — adoption docs
are only useful if people can actually adopt them.

---

## The idea

Stop oversteering your agent. Let a local model do the grunt work.

The point is *not* to make the local model smarter than your main agent. The point is to stop
spending premium tokens on jobs a small local model handles fine.

```
local AI    = worker
main agent  = supervisor
human       = driver
```

In one-off chats this saves nothing worth having. In **agent workflows** it compounds, because
the same small steps repeat constantly: log inspection, file scanning, scrape cleanup, grep
output, first-pass debugging. That repetition is where the local lane pays.

## Setup

Install Ollama (<https://ollama.com/download>), then:

```bash
ollama pull gemma4:e2b
ollama run gemma4:e2b
```

## Call it as a worker, not a chatbot

The worker gets a narrow job and a fixed output contract. That contract is the whole trick —
an unconstrained small model returns log spam, and you have gained nothing.

```bash
curl -s http://localhost:11434/api/chat \
  -d '{
    "model": "gemma4:e2b",
    "messages": [
      {
        "role": "system",
        "content": "You are a local inspection worker. Read messy input and return only: finding, evidence pointer, confidence, next action. Do not dump raw logs."
      },
      {
        "role": "user",
        "content": "Inspect this and return the clean worker result:\n\nPASTE_INPUT_HERE"
      }
    ],
    "options": { "temperature": 0.2, "num_predict": 500 },
    "stream": false
  }'
```

The worker returns exactly four fields, every time:

```
finding:
evidence_pointer:
confidence:
next_action:
```

## Wire it in as a subagent

Give the IDE agent this definition once, and it stops needing to be told:

```
Define a new subagent named local_inspection_worker.
Use my local Ollama model: gemma4:e2b.

Purpose:
  Handle small worker tasks before using premium models.

Use it for:
  - log inspection
  - file scanning
  - summaries
  - cleanup
  - first-pass debugging
  - messy input inspection

Return only:
  - finding
  - evidence pointer
  - confidence
  - next action

Rules:
  - do not dump raw logs
  - do not overexplain
  - preserve file paths, line numbers, IDs, commands, and error codes
  - if evidence is weak, say so
```

The last two rules matter more than they look. Preserving paths, line numbers and error codes is
what lets the supervisor act on the worker's output without re-reading the source. And a worker
that cannot say "evidence is weak" will invent confidence instead.

## What belongs local, what does not

| Local worker | Supervisor |
|---|---|
| log inspection, file scanning | multi-file refactors |
| summaries, cleanup | architectural decisions |
| first-pass debugging | judgment calls, tradeoffs |
| messy input → structured output | anything where being wrong is expensive |

## Verify the routing actually happened

An external model claiming it used your local lane is not evidence that it did. Check the Ollama
logs, not the assistant's narration. Junk routing looks identical to real routing from the
outside, and the only difference is in the logs.

## `scripts/delegate_task.py`

A minimal one-shot delegator: `python delegate_task.py '<instruction>' [<model>]`, defaulting to
`gemma4:e2b`.

**Known drift, not yet fixed:** it posts to Ollama's raw `/api/generate` and sets no token
budget, and its startup line names a model tag it does not use. Current NouGen doctrine is the
OpenAI-compatible `/v1/chat/completions` path with `max_tokens` ≥ 1400, because the Gemma
E-series spends a hidden reasoning budget first and returns **empty content with no error** when
starved. Treat this script as a demo of the shape, not as the reference client.

## Provenance

The pattern, the worker contract and the subagent definition above are from
["Stop Burning Tokens on Tasks Gemma 4 E2B Can Handle"](https://www.reddit.com/r/google_antigravity/comments/1tvwdmh/stop_burning_tokens_on_tasks_gemma_4_e2b_can/)
(r/google_antigravity). See `NOTICE` for the full provenance record, including related
independent work by another author.
