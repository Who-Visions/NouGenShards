/**
 * Open-World Evolution Engine (OpenSkill Implementation). (TS mimic of evolution.py)
 * Bootstraps skills and verification signals from open-world resources.
 *
 * EXPERIMENTAL / PREVIEW: the knowledge-acquisition and virtual-verification stages
 * below are currently simulated stubs, not a live open-world research + verification
 * loop. The scaffolding mirrors the OpenSkill design so it can be wired to real
 * retrieval (Exa / deep research) and real test generation later. Do not present
 * this as production self-evolution.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import * as path from "node:path";
import * as core from "./core.js";
import * as nougen_sandbox from "./nougen_sandbox.js";
import { get_best_available_client } from "./models_client.js";

export class EvolutionEngine {
  /**
   * Implements the OpenSkill framework for autonomous skill construction.
   */
  workspace: string;
  client: any;
  verbose: boolean;

  constructor(workspace_path: string | null = null, verbose: boolean = true) {
    // core.GLOBAL_DIR is a string in the TS port; join instead of Path '/'.
    this.workspace = workspace_path || path.join(core.GLOBAL_DIR, "evolution_sandbox");
    mkdirSync(this.workspace, { recursive: true });
    // get_best_available_client may be async-aware in the TS port; resolved lazily
    // by callers that await evolve_skill. We capture the (possibly Promise) handle here.
    this.client = get_best_available_client();
    this.verbose = verbose;
  }

  /**
   * Stage 1: Open-World Knowledge Acquisition.
   * Queries the 'Intelligence Wing' for external documentation and verification anchors.
   */
  acquire_knowledge(task_instruction: string): string {
    // In a real implementation, this would call Exa or Gemini Deep Research.
    // For the local substrate, we simulate the 'Wing' output.
    const query = `API documentation and best practices for: ${task_instruction}`;
    if (this.verbose) {
      console.log(`[*] Wings: Querying open-world resources for '${query}'...`);
    }

    // Simulated grounding from 'Intelligence Wing'
    return `Grounding for '${task_instruction}': Standard implementations involve using FTS5 for search and trigram tokenization for fuzzy matching.`;
  }

  /**
   * Stage 2: Self-Built Virtual Tasks.
   * Creates a test script that validates the skill without target-task supervision.
   */
  build_virtual_task(instruction: string, grounding: string): string {
    if (this.verbose) {
      console.log(`[*] Evolution: Generating virtual verification task for '${instruction}'...`);
    }
    // The generated virtual test asserts the pipeline actually produced usable
    // grounding for this instruction. An empty or off-topic Wing result fails
    // verification here instead of trivially passing — so a "Virtual Task
    // Passed" result means the acquisition stage did its job.
    const test_script = [
      "import sys",
      `GROUNDING = ${JSON.stringify(grounding)}`,
      `INSTRUCTION = ${JSON.stringify(instruction)}`,
      "def test_invariant():",
      "    assert GROUNDING.strip(), 'no grounding produced'",
      "    assert len(GROUNDING) > 40, 'grounding too thin to build a skill'",
      "    tokens = [t for t in INSTRUCTION.lower().split() if len(t) > 3]",
      "    assert (not tokens) or any(t in GROUNDING.lower() for t in tokens), 'grounding unrelated to instruction'",
      "test_invariant()",
      "print('Virtual Task Passed')",
      "",
    ].join("\n");
    return test_script;
  }

  /**
   * The core OpenSkill loop: Acquire -> Refine -> Verify -> Deploy.
   * (async in the TS port: get_best_available_client and execute_sandboxed may be async-aware)
   */
  async evolve_skill(instruction: string): Promise<Record<string, any>> {
    // Resolve the client handle in case it is a Promise (async-aware port).
    this.client = await this.client;

    // 1. Acquire
    const grounding = this.acquire_knowledge(instruction);

    // 2. Build Verifier
    const virtual_task = this.build_virtual_task(instruction, grounding);

    // 3. Refine (Simulated)
    if (this.verbose) {
      console.log("[*] Evolution: Refining skill against virtual verifier...");
    }
    const skill_content = `# SKILL: ${instruction}\n\n## Grounding\n${grounding}\n\n## Implementation\nFollow the verified invariants.`;

    // 4. Verify (trusted: this runs the engine's own generated stub, not user input)
    const result = await nougen_sandbox.execute_sandboxed(virtual_task, "python", 10, true);
    const verified = result.includes("Virtual Task Passed");

    if (verified) {
      // 5. Deploy
      // Sanitize the instruction into a safe slug: strip path separators and any
      // char outside [a-z0-9_-] so a crafted instruction (e.g. "../etc/x") can't
      // traverse outside the skills/ directory.
      const skill_id =
        instruction
          .toLowerCase()
          .trim()
          .replace(/[^a-z0-9_-]+/g, "_")
          .replace(/^_+|_+$/g, "") || "skill";
      const skill_dir = path.resolve(path.join(core.GLOBAL_DIR, "skills"));
      const skill_path = path.resolve(path.join(skill_dir, `${skill_id}.md`));
      // Defense in depth: refuse anything that resolves outside skills/.
      if (skill_path !== path.join(skill_dir, `${skill_id}.md`) || !skill_path.startsWith(skill_dir + path.sep)) {
        throw new Error(`Unsafe skill path rejected: ${skill_id}`);
      }
      mkdirSync(path.dirname(skill_path), { recursive: true });
      writeFileSync(skill_path, skill_content, { encoding: "utf-8" });

      // Store the evolution event as a shard
      core.capture("SKILL_EVOLVED", `Evolved Skill: ${instruction}`, skill_content, [
        "evolution",
        "openskill",
        "verified",
      ]);

      return {
        skill_id,
        path: skill_path,
        verified: true,
        experimental: true,
        grounding_source: "Open-World Intelligence Wing (simulated)",
      };
    }

    return { verified: false, experimental: true, error: "Virtual verification failed." };
  }
}

/** Entry point for the autonomous evolution loop. */
export async function run_autonomous_evolution(
  instruction: string,
  verbose: boolean = true,
): Promise<Record<string, any>> {
  const engine = new EvolutionEngine(null, verbose);
  return await engine.evolve_skill(instruction);
}
