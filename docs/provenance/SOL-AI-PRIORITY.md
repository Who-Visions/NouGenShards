# Provenance Packet — "Sol-Ai" Prior Use

**Subject:** Priority of use of the name **Sol-Ai** in the NouGenShards project.
**Prepared:** 2026-06-28 (Keymaker route — evidence preservation).
**Status:** Factual record. Not a legal conclusion.

---

## 1. Claim

**Sol-Ai is a Who Visions creation in continuous use since April 2026** —
roughly **81 days before** OpenAI's public announcement of "GPT-5.6 Sol" on
2026-06-26.

- **First use (operator record): 2026-04-06** — local `Sol-Ai\` source files
  (`sol.py`, `sol_avatar.txt`), with `SOL.md` on 2026-04-10. See §4.
- **Earliest cryptographically anchored corroboration: 2026-06-11** — the name
  enters this repository's git history, already carrying a **trademark
  declaration** for "Sol-Ai." See §3. This is not the origin; it is the first
  point that is tamper-evident and externally timestamped on GitHub.

The April files and the June git history are mutually consistent: the same name,
the same project, the same operator.

**Explicitly unknown / not claimed:** whether OpenAI used the internal name
"Sol" before its public announcement. This packet makes no claim about OpenAI's
internal naming history. It documents *our* prior use only.

---

## 2. Tamper-evidence note (read first)

Git commit SHAs form a hash chain: any alteration of historical content or
metadata changes every subsequent SHA, breaking the chain. Local *author dates*
can in principle be set by the committer, so the **authoritative anchor is the
server-side record on GitHub** (push timestamps and commit visibility for
`Who-Visions/NouGenShards`), which is external to this machine. The SHAs below
can be matched against GitHub's copy to confirm they were present server-side at
the stated times. PR #9: https://github.com/Who-Visions/NouGenShards/pull/9

---

## 3. In-repository evidence (verifiable)

### 3.1 First appearance — 2026-06-11

- **Commit:** `5173c429c2393aaffaf39c0507e7924115f7e873`
- **Author:** WhoVisions \<contact@whovisions.com\>
- **Authored & committed:** 2026-06-11 13:34:23 -0400
- **Message:** *docs: integrate the Architecture of Adjacency as the formal theoretical foundation*

This commit contains **two independent introductions** of the name:

1. A **trademark declaration** (NOTICE.md):
   > **Who Visions**, **NouGen**, **NouGenShards**, and **Sol-Ai** are
   > trademarks of Who Visions LLC. All other trademarks are the property of
   > their respective owners.

2. A **model tag** in source (`models_client.py`):
   > `for prefix in ["dav1d:e2b", "rhea-noir:e2b", "sol-ai:e2b"]:`

A documented trademark assertion of "Sol-Ai" therefore exists in the repository
as of **2026-06-11**, 15 days before the OpenAI announcement.

### 3.2 Named fleet roster — 2026-06-12

- **Commit:** `99d177015021a77cf7a18bc57f09faf4ea3a956c`
- **Authored & committed:** 2026-06-12 21:11:38 -0400
- **Message:** *feat: NouGen fleet roster (agents.py) — six named players on local models*

Introduced the agent persona with its etymology (independent, non-coincidental
derivation):
- `"Sol-Ai": AgentSpec(name="Sol-Ai", ...)`
- `default_model="sol-ai:e4b"`
- Module docstring: *Names carry meaning: Sol-Ai is Soleil — "sun" in Kreyol.*
- Persona: *You are Sol-Ai — Soleil, the sun.*

The "Soleil / sun (Kreyòl)" etymology documents an origin **independent** of any
external "Sol" naming — it derives from the project's established Kreyòl lineage
(cf. *Anghkooey* = "remember"), present in the same commit.

### 3.3 Current-state file hashes (SHA-256)

Computed 2026-06-28 at HEAD `a1a74fb8d4d6b0819cdde69ac931f6248f643e44`:

| File | SHA-256 |
|------|---------|
| `README.md` | `7848561d5d2fe11f83966fbe293ccd957a8a97da1fa28374ca6c50f06b0f29f9` |
| `src/nougen_shards/agents.py` | `2dc9db7776acc9c27e277c6fdba225937c8d16dc571ffa2d043cdc2962c7b6fb` |

`README.md` line ~213 lists: *"**Sol-Ai**: Broad Reasoning & Illumination"*.

---

## 4. Primary first-use evidence — April 2026 (operator record)

These are the **earliest** records of Sol-Ai and establish first use. They live
on the operator's machine (the Watchtower vault / NouGenShards FTS DB), outside
this repository, so they are **not independently verifiable from within this
repo** — they are recorded here from the operator's direct record and must be
preserved as **primary sources** (original filesystem metadata intact).

| Source | Detail | Timestamp |
|--------|--------|-----------|
| `Sol-Ai\sol.py` | local file CreationTime | **2026-04-06 03:19:42** |
| `Sol-Ai\sol_avatar.txt` | local file CreationTime | **2026-04-06 04:27:34** |
| `Sol-Ai\SOL.md` | local file CreationTime | 2026-04-10 22:13:36 |
| FTS DB | `Sol-Ai (Player)` in `FleetPresence.tsx` shard | 2026-06-14 17:55:35 |
| FTS DB | "Sol-Ai" — 38 hits indexed | (multiple) |

**Hardening checklist** (turns the April record from attested → independently
verifiable — do on the operator machine, preserve outputs):

1. `sha256sum "Sol-Ai\sol.py" "Sol-Ai\sol_avatar.txt" "Sol-Ai\SOL.md"` — record hashes.
2. Export the raw filesystem metadata (e.g. `stat` / PowerShell `Get-Item |
   Format-List *` showing CreationTime), save alongside the hashes.
3. Export the FTS shard rows that mention Sol-Ai (with their `ts` columns) to a
   file; hash that file.
4. Timestamp-anchor the hashes externally (e.g. OpenTimestamps, or commit the
   hash list to this repo so GitHub stamps it server-side).
5. Capture screenshots of the file properties and the FTS query results.

---

## 5. Counterparty reference

- OpenAI, "Previewing GPT-5.6 Sol: a next-generation model" — **2026-06-26**.
  https://openai.com/index/previewing-gpt-5-6-sol/

---

## 6. Independent verification

Anyone with access to `Who-Visions/NouGenShards` can reproduce §3:

```bash
# First appearance of the name in history (oldest first)
git log --all --reverse -S"Sol-Ai" --date=iso \
  --format="%H | authored:%ad | %an | %s"

# Inspect the introducing commits
git show 5173c429c2393aaffaf39c0507e7924115f7e873   # trademark decl + model tag (2026-06-11)
git show 99d177015021a77cf7a18bc57f09faf4ea3a956c   # named roster + etymology (2026-06-12)

# Re-derive current file hashes
sha256sum README.md src/nougen_shards/agents.py
```

Cross-check the printed SHAs against GitHub's server-side copy (commit pages /
PR #9) to confirm server-side presence at the stated dates.

---

## 7. Next-play guidance (unchanged)

- **Do not** rename Sol-Ai reflexively.
- Preserve primary sources: the local `Sol-Ai\` files (with original metadata),
  the FTS DB, and this repository's full git history.
- If this escalates to brand / legal / public positioning, extend this packet
  with: filesystem metadata exports, screenshots, the FTS shard rows, and an
  independent timestamp anchor (e.g. OpenTimestamps over this file's hash).
