/**
 * The Dream State (Autonomous Metameric Evolution). (TS mimic of dream.py)
 * Implementation of TMEM: Parametric Memory through Fast-Weight Rollouts.
 */
import { existsSync, writeFileSync } from "node:fs";
import * as path from "node:path";
import * as core from "./core.js";
import type { Shard } from "./core.js";

/** Retrieve the top shards by utility score across the federated database cluster. */
export function fetch_high_utility_shards(limit: number = 50): Shard[] {
  let top_shards: Shard[] = [];
  for (let i = 1; i <= core.MAX_DB_COUNT; i++) {
    if (!existsSync(core.get_db_path(i))) {
      continue;
    }
    const conn = core.get_connection(i);
    try {
      const rows = conn
        .prepare("SELECT id, title, content, utility_score FROM shards ORDER BY utility_score DESC LIMIT ?")
        .all(limit) as Shard[];
      for (const row of rows) {
        top_shards.push({ ...row });
      }
    } catch {
      /* mirror sqlite3.OperationalError pass */
    } finally {
      conn.close();
    }
  }

  // Sort globally and take top N
  top_shards.sort((a, b) => (b.utility_score as number) - (a.utility_score as number));
  return top_shards.slice(0, limit);
}

/**
 * Phase 1: REM Cycle.
 * Formats the raw shards into SFT QA pairs suitable for LoRA fine-tuning.
 */
export function synthesize_invariants(shards: Shard[]): Array<{ instruction: string; output: string }> {
  const sft_data: Array<{ instruction: string; output: string }> = [];
  for (const shard of shards) {
    // In a full TMEM pipeline, we could invoke an LLM to distill this.
    // For efficiency, we map the structured shards directly to instruction/output pairs.
    sft_data.push({
      instruction: shard.title,
      output: shard.content,
    });
  }
  return sft_data;
}

/**
 * Phase 3: Parametric Fast-Weight Rollout.
 * Exports the SFT data for the local Edge Model to perform an SVD-initialized LoRA update.
 */
export function parametric_burn_in(
  sft_data: Array<{ instruction: string; output: string }>,
  output_path: string = "dream_sft.jsonl",
): string {
  // core.GLOBAL_DIR is a string in the TS port; join instead of Path '/'.
  const out_file = path.join(core.GLOBAL_DIR, output_path);
  const lines = sft_data.map((item) => JSON.stringify(item) + "\n").join("");
  writeFileSync(out_file, lines, { encoding: "utf-8" });
  return out_file;
}

/**
 * Executes the autonomous Dream cycle.
 * Returns a summary of actions taken during 'sleep'.
 */
export function wake(): Record<string, any> {
  // 1. Prune
  core.decay_utility_scores();

  // 2. Extract
  const top_shards = fetch_high_utility_shards(50);

  // 3. Distill
  const sft_pairs = synthesize_invariants(top_shards);

  // 4. Burn In
  const dataset_path = parametric_burn_in(sft_pairs);

  return {
    experimental: true,
    pruned: "Applied 0.95x utility decay to all shards.",
    shards_extracted: top_shards.length,
    sft_pairs_generated: sft_pairs.length,
    parametric_dataset_path: dataset_path,
    status:
      "Decay applied and SFT dataset exported. NOTE: this prepares a " +
      "training dataset; it does not itself perform a LoRA weight update.",
  };
}
