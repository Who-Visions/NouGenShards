# 🚀 NouGenShards CLI: The Top-1% Onboarding Plan

The strongest signal across the best CLI tools: optimize for time-to-first-value and remember that friction compounds — a 5-step flow where each step is 90% smooth still loses ~41% of users. 
The best tools deliver onboarding through the CLI itself, not ten pages of docs, use smart defaults, never make you leave the terminal, and get you to a real win in the first 5 minutes — InfluxData calls it "Time to Awesome."

> 🎯 **The whole game is Time-to-First-Shard.** A new user should store a memory and watch their agent *recall it* inside 5 minutes — before reading any docs. Every step below removes a decision, defaults to *yes*, and never makes you leave the terminal.

---

## 🥇 The “aha” moment
> Your agent has prompts. Mine has shards. The first time the CLI hands a stored shard back to your agent and it *recalls what worked* — that’s activation. Steps 1–4 exist only to get you there fast.

---

## 🚀 The 10 Steps

### 1️⃣ Install in one command — and prove it worked

```bash
npm i -g nougen   # or: brew install nougen
nougen --version
```

**Top 1% move:** the very next thing you run is `nougen` with no args — a great CLI greets a first-timer with *what to do next*, not an error. You should see a 3-line “next: run `nougen init`” hint.

### 2️⃣ Bootstrap the local shard layer (idempotent, offline)

```bash
nougen init
```

This creates `~/.nougen/shards/nougen_shards.db` with the `shards`, `shard_fts` (FTS5), `shard_edges`, and `shard_cache` tables. It’s **local-first** — no network, no account. Safe to re-run; it never clobbers existing data.

### 3️⃣ Write your first shard (so there’s something to recall)

```bash
nougen add "Use bm25(shard_fts) for ranking, not LIKE" --tags sql,retrieval
```

Don’t start empty. One real shard now means Step 4 actually *demonstrates value* instead of returning nothing.

### 4️⃣ Search it back — this is the win

```bash
nougen search "how do I rank shards"
```

You should get your shard back, scored. **This is Time-to-First-Value.** If a first-timer sees retrieval work here, they’re hooked; everything after is depth.

### 5️⃣ Connect it to your agent (the actual point)

```bash
nougen connect --mcp
```

Wires NouGenShards in as an MCP memory tool so your coding agent can `recall` and `write` shards mid-task. Defaults to the standard MCP socket — **don’t make the user hand-edit config**; the command should auto-detect and confirm with a *y/N* defaulting to yes.

### 6️⃣ Set your tag + scope convention on day one

```bash
nougen config set default-scope project
```

Decide early: shards scoped to `project` vs `global`. This is the single highest-leverage habit — clean scope/tags now = clean retrieval forever. Adopt 3–5 tags max to start.

### 7️⃣ Ingest real work, not toy data

```bash
nougen ingest ./README.md
git log -5 --pretty=%B | nougen add --stdin --tags decisions
```

Pipe in actual docs, decisions, and snippets. Realistic data makes retrieval feel authentic immediately instead of like a demo.

### 8️⃣ Close the outcome loop (let trust scores learn)

```bash
nougen mark <shard-id> --worked     # or --failed
```

NouGenShards weights retrieval by outcome (success/failure → `trust_score`). Marking results is what makes recall get *smarter over time* instead of just bigger. Teach this on the first day.

### 9️⃣ Learn the 3 daily commands + lean on `--help`

```bash
nougen --help        # discoverability is the feature
nougen search ...    # recall
nougen add ...       # capture
nougen status        # what’s in the layer
```

You only need three verbs to live in it: **add, search, status.** A top-tier CLI makes the rest *discoverable* rather than memorized.

### 🔟 Make it stick — automate capture

```bash
nougen hook install   # auto-capture shards from your shell / agent
alias ns="nougen search"
```

The top 1% don’t rely on willpower — they wire it into the workflow. An auto-capture hook + a 2-keystroke alias turns NouGenShards from a tool you *remember to use* into memory that just *accumulates*.

---

## ✅ First-session checklist

- [ ]  `nougen --version` returns cleanly
- [ ]  `nougen init` created `~/.nougen/shards/nougen_shards.db`
- [ ]  Stored at least one real shard
- [ ]  Got a scored result from `nougen search`
- [ ]  Connected to your agent via `nougen connect --mcp`
- [ ]  Set a default scope + agreed on starter tags
- [ ]  Marked one shard `--worked` to seed the trust loop
- [ ]  Installed the auto-capture hook

> 🧠 **Design rule for the CLI team:** **deliver this playbook *inside* the tool.** `nougen init` should end by printing steps 3–5, and `nougen status` should nudge the next unfinished step. Onboarding that lives in the terminal beats onboarding that lives in a doc.