# Blade vision-model war-game — the one open step

Status: **NOT RUN.** The live Blade measurement is the one open step. Everything
below is the exact, ready-to-run package — no guessing left in it.

## What is in this folder

- `test-set/manifest.json` — the fixed test set: 43 frames, sha256 each.
  - Congress: 31 distinct frames (Forest Hill & S Congress, 03:27–03:31 EST
    2026-11-19, night rain), per-frame ground truth from the human review in
    `~/workspace/eye-turning/turning-counts.json` (15 unique vehicles: 1
    through, 14 unclassified; 30 vehicle-sightings across the 31 frames).
  - Military: 12 distinct frames (Forest Hill & Military, 02:29–02:30 EST),
    NO hand count — descriptive scoring only.
  - Frames live in `test-set/frames-congress/` and `test-set/frames-military/`.
- `run-on-blade.py` — stdlib-only runner (Ollama on localhost:11434).
  Writes `results-<model>.json` in this folder.
- `../blade-vision-wargame.md` — the full war-game doc (verdicts, receipts,
  ledger).

## Who runs it, and how

Blade's Claude (or Dave), ON Blade, from this folder:

```
ollama list
ollama pull qwen2.5vl:3b     # ~2 GB; verify the tag first — if it does not
                             # resolve, search Ollama/HF for the VL 3B tag
                             # and record the exact tag used
python run-on-blade.py --model qwen2.5vl:3b
```

Then the bulk comparison, same folder:

```
ollama pull moondream        # ~1.7 GB
python run-on-blade.py --model moondream
```

The 9B fallback (Qwythos 9B v2) runs ONLY if the 3B fails the accuracy bar.
Its pull command is deliberately NOT written here: no verified Ollama tag or
HF repo was confirmed for it — resolve it at run time from LM Studio search
and record the exact source. Do not guess a tag.

## Expected outputs (what "done" looks like)

`results-qwen2.5vl_3b.json` (and the matching moondream file) must contain:

1. `vram_before` / `vram_after_load` / `vram_after_loop` — nvidia-smi
   memory.used in MB. The load receipt is the after-load minus before delta.
2. `toks_per_sec` — eval_count / eval_duration on fh-001.jpg with the fixed
   prompt, plus wall seconds. (Blade's Max-Q will be slower than the RTX 3070
   20 tok/s in the article — report the measured number, do not quote the
   article's.)
3. `runs[]` — one entry per frame: model reply JSON, eval_count,
   eval_duration_s, wall_s, and the ground-truth count it is scored against.

## Scoring (do this on the results file, not from memory)

- Congress per-frame: model `vehicles` vs `ground_truth_count`. Exact match,
  over-count, under-count per frame; mean absolute error across the 31.
- Congress total: sum the model's per-frame counts? NO — a vehicle spanning
  6 frames is one vehicle, not six. Score the total as: the model does NOT get
  a total from per-frame counts. Instead, the run also needs a cross-frame
  judgement the single-frame prompt cannot give — record this as a limit:
  per-frame counting measures visibility, not a turning-movement total.
  The honest headline is the per-frame MAE, not a 15-vehicle total.
- Movement: only 1 of 15 vehicles is classified (through) by the human.
  Do not score movement except on that one vehicle.
- Military: descriptive only — no hand count exists. Compare against a hand
  count done at run time, or report the counts unvalidated.

## Do not

- Do not run this through ask_dav1d and report its answer as a result.
  The dav1d Ollama persona has no tools: it narrated an "RTX 4090, 24 GB"
  for Blade (a 2020 Razer with a 2080 Super Max-Q 8GB). Anything it says
  about Blade hardware is unverified narration, never a receipt.
- Do not spend Claude credits on this. The local run is the point.
- Do not load the 9B before the 3B has been scored. 3B first.
