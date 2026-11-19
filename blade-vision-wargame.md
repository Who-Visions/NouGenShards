# Blade vision-model war-game

Date: 2026-11-19. Status: **EXECUTION STOPPED AT THE ROUTE — no live Blade
measurement exists.** Every verdict below that depends on a Blade measurement
is marked **NOT MEASURED — awaiting Blade-side run**. Nothing in this doc is
presented as measured on Blade unless the ledger says so.

## What was asked

War-game a local vision model for Blade (Dave's Razer Blade 15 Advanced 2020),
same bar as today's arXiv war-game: adopt/adapt/reject per lane, every verdict
needs a receipt, governed ledger, nothing judged without a measurement or a
plainly stated "not measured". Candidates: Qwen2.5-VL 3B primary, Moondream 2B
bulk second, Qwythos 9B fallback only, Qwen3-VL 2B/4B as the newer-generation
alternative. Four lanes: (1) Eye Watch frame reader, (2) private screenshot
reader, (3) photo archive tagger, (4) Eye read_photo backup.

## Route discovery — the finding that stopped the execution

A normal (non-sharp) execution route to Blade was searched first, read-only.
Result: **there is no usable normal route from this VM, and the one route
that looks usable is a trap.**

| Route | Result | Receipt |
|---|---|---|
| `dav1d_exec` (fleet MCP) | SHARP — forbidden by Dave's standing rules. Not used. | Task brief + standing rules |
| `ask_dav1d` (fleet MCP) | **NOT a measurement route.** The dav1d:e2b Ollama persona has no tools, no web, no video access. It answers from its weights — it narrates. Proof: asked for `nvidia-smi` output, it replied "NVIDIA GeForce RTX 4090, memory.total 24576MB, memory.free 8192MB". Blade is a 2020 Razer with an RTX 2080 Super Max-Q 8GB. There is no RTX 4090 on Blade. The reply's own header says it had no tools and its claims are unverified. | ask_dav1d call 2026-11-19 ~14:22 EST, returned in 38.8 s, engine ollama, model dav1d:e2b, host "Blade Node (Stadium)" |
| `ask_dav1d` transport | The fleet MCP client hard-times-out at 45 s (`client.py:68`, `opener.open(..., timeout=45)`). Two cold attempts failed at ~46 s each ("MCP request did not complete"). Only a short probe answered. Cold model loads take 5–60 s, so this route fails exactly when it is needed. | Two failed calls, 46,491 ms and 46,031 ms; client.py line 68 |
| `nougenmsg` / `nougenmsg_send` to @blade | Not configured from this connector. `nougenmsg_peers` returns only @phoebus and @whoart. A send to @blade would return not-delivered. Separately, Claude on Blade does not read the fleet bus (established 2026-11-19 ~01:41 EST), so a bus message would not reach him anyway. | nougenmsg_peers 2026-11-19 ~14:22 EST |
| `app_ask` | Reaches only the phoebus Muse (`app_list` returns one adapter: muse on phoebus). Wrong box. | app_list 2026-11-19 ~14:22 EST |
| Federation health | GREEN, all 3 routes serving, blade route ok. The failure is not federation health. | shards_status 2026-11-19 14:21:36 EST |

**Consequence:** the only execution route that can run a measurement on Blade
is the sharp `dav1d_exec`, which Dave's standing rules forbid without his
explicit word. Execution stops here. The war-game below is therefore
provisional: published-benchmark reasoning plus the packaged test set, with
the live measurement prepared as the one open step.

**Standing warning for every future Blade job:** never accept `ask_dav1d`
output as a receipt. It narrated an RTX 4090 for a box that has a 2080
Super Max-Q — the same failure mode as dav1d narrating a fake successful
restart earlier (alignment synthesis). If a dav1d answer is the only evidence
for a claim, the claim is unmeasured.

## Blade — the target box (stated facts, not measured this run)

- Razer Blade 15 Advanced (2020), RTX 2080 Super Max-Q, **8 GB VRAM**.
- 64 GB DDR4 as 2×32 GB, **one stick failing**, replacement not ordered.
  The box is degraded; any load measurement must be read against that.
- Runs Claude (the architect) and fleet work. The vision lane must not
  degrade the workhorse; contention was not observed because no measurement ran.
- Ollama exists on the node: the `ask_dav1d` tool description (server-side,
  not persona narration) states dav1d:e2b runs "on the Stadium's ollama lane".
  That is why the prepared runner uses Ollama on localhost:11434.
- Federation GREEN this morning; Blade serving (shards_status, above).

## Candidate facts — re-verified by search 2026-11-19

- **Qwen2.5-VL 3B**: Q4 ~2.0–2.1 GB file, ~3 GB VRAM at 8K context
  (~4.2 GB at 32K). OCRBench **828** (HF Open VLM Leaderboard, 285 models,
  #108, avg 64.5). DocVQA 93.9 (Shakti comparison table). Apache 2.0.
  Correction: OCRBench **864 is the 7B**, not the 3B — do not cite 864 for
  the 3B. Correction 2: the text-only Qwen2.5-3B-Instruct is Qwen Research
  License (non-commercial); the **VL** 3B is Apache 2.0. Do not confuse them.
- **Qwen3-VL 2B**: ~2.8 GB download, 256K context, grounds objects to boxes,
  returns JSON reliably; the 2–4B tier "beats 2023's 13B models on almost
  everything" (mid-2026 landscape). 4B step-up at ~4 GB VRAM.
- **Moondream 2B**: ~1.7 GB, ~2 GB VRAM, 3–5 s/image, weakest reasoning
  (avg 43.0 on the leaderboard). The bulk sweeper, not the thinker.
- **InternVL3-2B**: ~2 GB VRAM, OCR 831 — a coin-flip alternative to the
  Qwen 3B, not run.
- **Qwythos 9B v2** (Empero AI fine-tune of Qwen 3.5 9B): Q4_K_M 5.74 GB +
  ~0.9 GB projector, ~20 tok/s on an RTX 3070 8GB (XDA, 2026-11-19).
  Blade's Max-Q will be slower — measure, don't assume. No verified Ollama
  tag or HF repo was confirmed for it: its pull command is deliberately not
  written in the run package.
- **SmolVLM 2.2B**: weaker (OCR 725), dropped from Ollama's library
  (community re-uploads only). Skipped unless it wins a measurement.

VRAM arithmetic that matters: the 9B needs ~6.6 GB of Blade's 8 GB (no
headroom, nothing else runs); the 3B needs ~3 GB (half the card free);
Moondream needs ~2 GB. On a degraded box, that is the whole ballgame.

## Per-lane verdicts

### 1. Eye Watch frame reader — PROVISIONAL ADAPT — NOT MEASURED

The job: real vehicle counts + conditions from live Eye frames, replacing
the volume proxy (a heuristic, mean 1.5 vehicles/frame at Forest Hill & I-95,
labelled as a proxy). The published numbers support reading text and
conditions; nothing published supports counting vehicles at night in the rain
from one oblique angle. The ground truth itself is the warning: a human
reviewing all 31 distinct Congress frames classified only **1 of 15**
vehicles with confidence (14 unclassified — night rain, droplets on the lens,
one angle, 5 s cadence, three feed stalls of 15/20/40 s hiding exits).
A 3B may count visible blobs, but it cannot recover what the frames do not
show, and per-frame counts cannot be summed into a turning-movement total
(a vehicle spanning 6 frames is one vehicle, not six). The volume proxy stays
until the measurement lands. Receipt needed: per-frame MAE on the 31-frame
Congress set (see the open step).

### 2. Private screenshot reader — PROVISIONAL ADOPT (design) — Blade fit/speed NOT MEASURED

The job: Dave's own screenshots (logins, statements, private shots) read on
Blade, nothing leaves the house. The privacy property is architectural — a
local model, no network call — and does not need a GPU measurement to assert
as a design fact. The capability is the best-supported of the four lanes:
OCRBench 828 and DocVQA 93.9 say the 3B reads text in images well, and the
XDA piece's finding (a 9B matched Opus line-for-line on text screenshots)
is in the same direction at a smaller size. VRAM ~3 GB of 8 GB is arithmetic.
What is NOT measured: actual tok/s on Blade's Max-Q, and behaviour while the
failing RAM stick is in play. This is the lowest-risk lane and the first one
to run once the open step lands.

### 3. Photo archive tagger — PROVISIONAL ADAPT — NOT MEASURED

The job: Dave's 15-year photo archive, described/tagged locally. The shape
fits Moondream (fast, cheap, 3–5 s/image) as a first pass, with the 3B
refining the interesting frames — bulk description is exactly what the small
models are good at. Two things block a firmer verdict: the archive's
location and size on Blade are **unconfirmed** (the recon that would have
answered it never ran), and there is no timed sample. Note the connection,
do not spend on it: archive ingest is also a Claude-credits sink candidate
($100 expires Nov 27) — the local tagger is the alternative to renting it
out, not a reason to spend credits. Receipt needed: archive path/size on
Blade + a 20-photo timed sample with the 3B and Moondream.

### 4. Eye read_photo backup — VERDICT WITHHELD — NOT MEASURED

The job: Blade as the house's own box for the Eye's local vision reads. The
current Eye vision backend's host is **unconfirmed** (the Eye connector doc
does not state where read_photo / guess_photo_location run). If it already
runs on Blade, this lane is moot. If it runs elsewhere, Blade-as-backup
needs the Eye's traffic shape (calls/day, latency needs) which was not
established. No verdict until those two facts exist. Receipt needed: where
read_photo runs today + its call volume.

## Top 5 by leverage

1. **Run the prepared Blade-side measurement (the open step below).** It is
   the single action that converts all four lanes from provisional to real.
   Everything else on this list is commentary until it lands.
2. **Qwen2.5-VL 3B first.** The 3 GB fit is the decision: it leaves half of
   Blade's 8 GB free on a degraded box, and if it reads the frames, the 9B
   never needs to load. (Qwen3-VL 2B is the newer-generation alternate if the
   3B disappoints.)
3. **Moondream 2B as the bulk sweeper.** 3–5 s/image is the archive job and
   the burst-sweep job — run it across a whole set first, send only the
   interesting frames to the 3B.
4. **Never accept ask_dav1d output as a receipt.** The RTX 4090
   hallucination is the proof. dav1d narrates; it does not measure. Any
   future Blade claim resting only on a dav1d answer is unmeasured.
5. **Fix the 45 s MCP client timeout before the next live Blade job.**
   `client.py:68` caps every call at 45 s; cold model loads (5–60 s) will
   always fail through it, which is exactly what happened twice here.

## The one open step (exact)

Everything is packaged and ready at
[blade-vision-wargame/](sandbox://workspace/blade-vision-wargame/) —
`README.md` (how to run), `run-on-blade.py` (stdlib-only Ollama runner),
`test-set/manifest.json` + 43 frames (31 Congress with per-frame ground
truth, 12 Military descriptive-only), all sha256-verified against the source
manifests. Blade's Claude (or Dave), ON Blade, from that folder:

```
ollama list
ollama pull qwen2.5vl:3b     # ~2 GB; verify the tag first
python run-on-blade.py --model qwen2.5vl:3b
ollama pull moondream        # ~1.7 GB
python run-on-blade.py --model moondream
```

Expected outputs: VRAM before/after load (the load receipt), tok/s on the
fixed prompt + fixed frame fh-001.jpg (report the measured number, not the
article's 20 tok/s), and per-frame model replies with timing for all 43
frames. Scoring is per-frame MAE on Congress (31 frames) — NOT a summed
15-vehicle total, which a single-frame prompt cannot produce. The 9B runs
only if the 3B fails the accuracy bar, and its pull command must be resolved
at run time (no verified tag). Do not spend Claude credits. Do not run it
through ask_dav1d.

## Provenance ledger

| Claim | Source | Status |
|---|---|---|
| Federation GREEN, blade route serving | shards_status 2026-11-19 14:21:36 EST | Measured |
| ask_dav1d cannot measure (no tools, narrates) | ask_dav1d probe ~14:22 EST: "RTX 4090, 24576 MB" vs known 2080S Max-Q 8 GB; header states no tools | Measured (negative) |
| MCP client 45 s timeout | client.py:68; two ask_dav1d calls failed at ~46 s | Measured |
| nougenmsg @blade not configured here | nougenmsg_peers: phoebus + whoart only | Measured |
| app_ask is phoebus-only | app_list: one adapter (muse) | Measured |
| Claude on Blade does not read the bus | Established 2026-11-19 ~01:41 EST (prior session) | Stated, prior |
| Qwen2.5-VL 3B ~3 GB VRAM, OCRBench 828, DocVQA 93.9, Apache 2.0 | Web search 2026-11-19 (HF Open VLM Leaderboard; Shakti table; Qwen model pages) | Published, re-verified |
| Qwen3-VL 2B/4B, Moondream, InternVL3-2B, SmolVLM figures | Web search 2026-11-19 (landscape + maki docs) | Published, re-verified |
| Qwythos 9B: 5.74 GB + 0.9 GB projector, ~20 tok/s on RTX 3070 | XDA article 2026-11-19 10:30 EST | Published |
| Congress ground truth: 15 vehicles, 1 through, 14 unclassified, 31 distinct frames | turning-counts.json (human review, 2026-11-19) | Measured (human) |
| Test set: 43 frames, sha256-verified | Built 2026-11-19, this run | Measured |
| Blade GPU load / VRAM used / tok/s on Blade | — | NOT MEASURED — awaiting Blade-side run |
| Per-frame accuracy on the test set | — | NOT MEASURED — awaiting Blade-side run |
| Photo archive location/size on Blade | — | NOT MEASURED — recon never ran |
| Eye read_photo backend host + call volume | — | NOT MEASURED |
| Blade RAM usable / failing-stick state | — | NOT MEASURED — recon never ran |
| Contention with Blade's running fleet work | — | NOT OBSERVED — no measurement ran |

## Honest limits

- No live Blade numbers exist in this doc. Every load, speed and accuracy
  claim is provisional until the open step runs.
- The 3B Ollama tag `qwen2.5vl:3b` comes from third-party docs (maki); verify
  it with `ollama list`/search before pulling.
- The per-frame ground truth counts a vehicle in every frame it is visible
  in (30 sightings of 15 vehicles). Score per-frame MAE, not a summed total.
- The Military set has no hand count; its numbers are descriptive only.
- The "Stadium" host label in the dav1d reply is unverified narration, like
  the RTX 4090 claim in the same reply. Blade's hardware is as Dave stated
  it (2020 Razer, 2080 Super Max-Q 8 GB) until a real `nvidia-smi` receipt
  says otherwise.
