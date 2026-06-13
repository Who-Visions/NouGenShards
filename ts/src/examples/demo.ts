/**
 * NouGenShards Demonstration Workflow. (TS mimic of examples/demo.py)
 *
 * Demonstrates querying an LLM with and without injected memory shards.
 * Python urllib + socket calls to the local Ollama server become node:net + fetch.
 * The four-phase flow and console output are preserved 1:1.
 */
import { connect } from "node:net";
import { capture, retrieve, compile_recall_packet } from "../nougen_shards/index.js";

/** Check if the local Ollama server is running. */
function check_ollama_alive(): Promise<boolean> {
  if (process.env.NOUGEN_SIMULATE_DEMO === "1") {
    return Promise.resolve(false);
  }
  return new Promise((resolve) => {
    const sock = connect({ host: "127.0.0.1", port: 11434 });
    const done = (alive: boolean): void => {
      sock.destroy();
      resolve(alive);
    };
    sock.setTimeout(500);
    sock.once("connect", () => done(true));
    sock.once("timeout", () => done(false));
    sock.once("error", () => done(false));
  });
}

/** Fetch the list of available models from the local Ollama server. */
async function get_available_models(): Promise<string[]> {
  if (!(await check_ollama_alive())) {
    return [];
  }
  try {
    const resp = await fetch("http://127.0.0.1:11434/api/tags", { method: "GET" });
    if (resp.status === 200) {
      const data = (await resp.json()) as { models?: { name: string }[] };
      return (data.models ?? []).map((m) => m.name);
    }
  } catch {
    /* URLError / JSONDecodeError / OSError equivalent */
  }
  return [];
}

/** Send a query to the local Ollama model and return its response. */
async function query_local_llm(model: string, prompt: string, system_prompt = ""): Promise<string> {
  if (!(await check_ollama_alive())) {
    return "[Local Ollama Offline - Simulating response based on context]";
  }

  try {
    const payload: Record<string, unknown> = { model, prompt, stream: false };
    if (system_prompt) {
      payload.system = system_prompt;
    }

    const resp = await fetch("http://127.0.0.1:11434/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (resp.status === 200) {
      const response_data = (await resp.json()) as { response?: string };
      return (response_data.response ?? "").trim();
    }
  } catch (exc) {
    return `[Model execution failed: ${exc}]`;
  }
  return "[No response]";
}

/** Select the appropriate model from the list of available models. */
async function get_selected_model(): Promise<string> {
  const models = await get_available_models();
  if (!models.length) {
    console.log("[!] Local Ollama is not active or no models found. Running in SIMULATED Mode.");
    return "";
  }

  for (const mod of models) {
    if (["e2b", "e4b", "2b", "4b"].some((x) => mod.toLowerCase().includes(x))) {
      console.log(`[*] Connected to Ollama. Selected Model: ${mod}`);
      return mod;
    }
  }

  console.log(`[*] Connected to Ollama. Selected Model: ${models[0]}`);
  return models[0];
}

/** Return a simulated response for the amnesia phase. */
function simulate_amnesia_response(): string {
  return (
    "This error occurs when Node.js is unable to spawn the child process. " +
    "Check your PATH environment variables, make sure python is correctly " +
    "installed, check file permissions, or ensure the executable exists."
  );
}

/** Return a simulated response for the recall phase. */
function simulate_recall_response(): string {
  return (
    "Based on the recalled memory (Shard #1), you need to normalize the backslashes " +
    "in process.env.PATH. Update your Next.js subprocess call to replace " +
    "backslashes with forward slashes, and call subprocess.Popen with shell=True " +
    "to successfully spawn the process on Windows."
  );
}

/** Run phase 1: Query the model without memory. */
async function phase_one_amnesia(selected_model: string, issue_query: string, base_system_prompt: string): Promise<void> {
  console.log("\n--- PHASE 1: Querying Agent B (Clean Environment / Amnesia) ---");
  console.log(`Query: ${issue_query}`);
  console.log("[*] Generating response without memory...");

  let response_without_recall: string;
  if (selected_model) {
    response_without_recall = await query_local_llm(selected_model, issue_query, base_system_prompt);
    if (response_without_recall.includes("Model execution failed") || response_without_recall.includes("timed out")) {
      console.log("[!] Local LLM timed out/failed. Falling back to simulated Amnesia response.");
      response_without_recall = simulate_amnesia_response();
    }
  } else {
    response_without_recall = simulate_amnesia_response();
  }
  console.log(`\n[Agent Response - Amnesia]:\n${response_without_recall}\n`);
}

/** Run phase 2: Persist experience to NouGenShards. */
function phase_two_capture(): void {
  console.log("\n--- PHASE 2: Persisting Experience to NouGenShards ---");
  const shard_title = "Next.js Windows Python Spawn Helper Resolution";
  const shard_content =
    "RESOLVED: Next.js API routes on Windows fail to spawn Python child processes " +
    "if path slashes are unescaped. Fix this by normalizing the PATH using " +
    "forward slashes in your Next.js subprocess config or calling `subprocess.Popen` " +
    "with shell=True and replacing all backslashes in `process.env.PATH` with " +
    "forward slashes.";
  const tags = ["nextjs", "windows", "python", "subprocess", "spawn-helper"];

  const added = capture("BUG_FIX", shard_title, shard_content, tags);
  if (added) {
    console.log(`[+] Successfully captured shard: '${shard_title}'`);
  } else {
    console.log("[!] Shard already exists in database. Proceeding.");
  }
}

/** Run phase 3: Retrieve and rank the recall candidates. */
function phase_three_retrieve(): string {
  console.log("\n--- PHASE 3: Lexical & Ranked Recall Match (FTS5) ---");
  const retrieved_shards = retrieve("spawn helper Next.js Windows python");
  console.log(`[*] Retrieved ${retrieved_shards.length} matching shards.`);

  const recall_packet = compile_recall_packet(retrieved_shards);
  console.log("\nCompiled Recall Packet:");
  console.log("-".repeat(50));
  console.log(recall_packet);
  console.log("-".repeat(50));
  return recall_packet;
}

/** Run phase 4: Query the model with memory injected. */
async function phase_four_recall(
  selected_model: string,
  issue_query: string,
  base_system_prompt: string,
  recall_packet: string,
): Promise<void> {
  console.log("\n--- PHASE 4: Querying Agent B (With Recall Injected) ---");
  console.log("[*] Generating response with memory recall...");

  const system_prompt_with_recall = `${base_system_prompt}\n\n${recall_packet}`;

  let response_with_recall: string;
  if (selected_model) {
    response_with_recall = await query_local_llm(selected_model, issue_query, system_prompt_with_recall);
    if (response_with_recall.includes("Model execution failed") || response_with_recall.includes("timed out")) {
      console.log("[!] Local LLM timed out/failed. Falling back to simulated Recall response.");
      response_with_recall = simulate_recall_response();
    }
  } else {
    response_with_recall = simulate_recall_response();
  }
  console.log(`\n[Agent Response - Recall]:\n${response_with_recall}\n`);
}

/** Print the final scoreboard. */
function print_scoreboard(): void {
  const pad = (s: string, n: number): string => (s.length >= n ? s : s + " ".repeat(n - s.length));
  console.log("=".repeat(80));
  console.log("                      NOUGENSHARDS SCOREBOARD                     ");
  console.log("=".repeat(80));
  console.log(` ${pad("MODE", 25)} | ${pad("BEHAVIOR / EFFECTIVENESS", 50)}`);
  console.log("-".repeat(80));
  console.log(` ${pad("Amnesia (No Shard)", 25)} | ${pad("Generic/broad system tips. Lacks repo context.", 50)}`);
  console.log(
    ` ${pad("Recall (With NouGenShards)", 25)} | ` + `${pad("Retrieves exact slash normalization fix instantly.", 50)}`,
  );
  console.log("=".repeat(80));
}

/** Execute the full NouGenShards demonstration workflow. */
export async function main(): Promise<void> {
  console.log("=".repeat(80));
  console.log(" NOUGENSHARDS DEMONSTRATION WORKFLOW ");
  console.log("=".repeat(80));

  const selected_model = await get_selected_model();

  const issue_query =
    "How do we fix the 'spawn helper failed' RuntimeError when calling " +
    "python subprocesses inside our Windows Next.js API routes?";
  const base_system_prompt = "You are a senior coding assistant. Help the user solve their issue.";

  await phase_one_amnesia(selected_model, issue_query, base_system_prompt);
  phase_two_capture();
  const recall_packet = phase_three_retrieve();
  await phase_four_recall(selected_model, issue_query, base_system_prompt, recall_packet);
  print_scoreboard();
}

// Entry guard (mirror `if __name__ == "__main__": main()`)
const isMain = import.meta.url === `file://${process.argv[1]}` || import.meta.url.endsWith(process.argv[1]?.replace(/\\/g, "/") ?? "");
if (isMain) {
  void main();
}
