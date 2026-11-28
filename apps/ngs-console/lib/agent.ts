// The console agent. A deterministic planner over the engine's tools: it turns
// a message into engine calls, runs them, and writes a short reply from what
// came back. No language model runs here and no API key is read. An LLM agent
// (AI SDK or an agentcn recipe) can replace `plan()` later; the tool contract
// and the UI stay the same.

export type ToolName = "stats" | "remember" | "scan" | "get" | "verify" | "recall" | "bench" | "gates"

export type PlannedCall = {
  id: string
  tool: ToolName
  label: string
  args: string[]
  display: string
}

export type Plan = { calls: PlannedCall[]; intent: string; query?: string }

const KIND_HINTS: { kind: "episodic" | "procedural"; re: RegExp }[] = [
  { kind: "procedural", re: /\b(how to|steps?|always|never|run|use)\b/i },
  { kind: "episodic", re: /\b(today|yesterday|tonight|happened|shipped|merged|deployed|at \d)/i },
]

function kindFor(text: string) {
  for (const h of KIND_HINTS) if (h.re.test(text)) return h.kind
  return "semantic"
}

function parseCount(raw: string | undefined, fallback: number, max: number) {
  if (!raw) return fallback
  const s = raw.toLowerCase().replace(/,/g, "")
  const n = s.endsWith("k") ? Number(s.slice(0, -1)) * 1000 : Number(s)
  if (!Number.isFinite(n) || n <= 0) return fallback
  return Math.min(Math.round(n), max)
}

function q(s: string) {
  return /^[\w.:/-]+$/.test(s) ? s : JSON.stringify(s)
}

let seq = 0
function call(tool: ToolName, args: string[], label: string): PlannedCall {
  seq = (seq + 1) % 1_000_000
  return { id: `${tool}-${Date.now().toString(36)}-${seq}`, tool, label, args, display: ["ngs_cli", tool, ...args.map(q)].join(" ") }
}

export function plan(input: string): Plan {
  const text = input.trim()
  const lower = text.toLowerCase()

  const remember = text.match(/^(?:remember|store|save|note)(?:\s+that)?[:\s]+([\s\S]+)$/i)
  if (remember) {
    const body = remember[1].trim()
    const title = body.length > 80 ? body.slice(0, 77).trimEnd() + "..." : body
    const kind = kindFor(body)
    return {
      intent: "remember",
      calls: [
        call("remember", ["--ns", "console", "--kind", kind, "--title", title, "--body", body, "--tag", "console"], `Remember a ${kind} fact`),
        call("verify", [], "Verify the chain and signatures"),
      ],
    }
  }

  const id = lower.match(/\b[0-9a-f]{64}\b/)
  if (id) return { intent: "get", calls: [call("get", [id[0]], "Read the fact by id")] }

  if (/\b(verify|integrity|tamper|chain|signatures?)\b/.test(lower)) {
    return { intent: "verify", calls: [call("verify", [], "Verify the chain, signatures and a fresh checkpoint")] }
  }

  if (/\b(gates?|judge|tests?|checks?|conformance)\b/.test(lower)) {
    return { intent: "gates", calls: [call("gates", [], "Run the judge gates: header, unit, crash")] }
  }

  const benchM = lower.match(/\bbench(?:mark)?\b(?:\D{0,12}([\d,]+k?))?/)
  if (benchM) {
    const n = parseCount(benchM[1], 2000, 50000)
    return { intent: "bench", calls: [call("bench", [String(n)], `Bench ${n.toLocaleString("en-US")} facts on a scratch log`)] }
  }


  const recallM = text.match(/^(?:recall|search|find|look up|what do (?:we|you) know about)\s+([\s\S]+?)\??$/i)
  if (recallM) {
    const query = recallM[1].trim()
    return {
      intent: "recall",
      query,
      calls: [
        call("recall", ["--q", query, "--k", "5"], `Recall "${query}"`),
        call("scan", ["--limit", "500"], "Fall back to a keyword scan of the log"),
      ],
    }
  }

  const scanM = lower.match(/\b(?:last|recent|latest|list|show)\b(?:\D{0,10}(\d+))?/)
  if (scanM || /\bfacts?\b/.test(lower)) {
    const n = parseCount(scanM?.[1], 10, 100)
    return { intent: "scan", calls: [call("scan", ["--limit", String(n)], `Read the last ${n} facts`)] }
  }

  if (/\b(status|stats|health|engine|version|who)\b/.test(lower)) {
    return { intent: "stats", calls: [call("stats", [], "Read engine stats and node key")] }
  }

  return { intent: "help", calls: [] }
}

type Json = Record<string, unknown>

function n(x: unknown, digits = 0) {
  return typeof x === "number" ? x.toLocaleString("en-US", { maximumFractionDigits: digits }) : String(x)
}

export function keywordFilter(facts: Json[], query: string) {
  const words = query.toLowerCase().split(/\W+/).filter((w) => w.length > 2)
  return facts
    .map((f) => {
      const hay = `${f.title ?? ""} ${f.body ?? ""} ${(f.tags as string[] | undefined)?.join(" ") ?? ""}`.toLowerCase()
      const score = words.reduce((s, w) => s + (hay.includes(w) ? 1 : 0), 0)
      return { f, score }
    })
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 5)
    .map((x) => x.f)
}

// One short reply from the results. Plain sentences, no dashes.
export function reply(p: Plan, results: Json[]): string {
  const [a, b] = results
  if (p.intent === "help") {
    return [
      "I run the NGS engine for you. Try one of these:",
      "",
      "- **remember** that the Blade 502 stopgap comes out after PR 1200",
      "- **show** the last 10 facts",
      "- **verify** the chain",
      "- **run the judge gates**",
      "- **bench** 5,000 facts",
      "- **recall** Blade",
    ].join("\n")
  }
  if (a && a.ok === false && p.intent !== "recall") {
    return `The engine said no: ${a.code ?? "error"}. ${a.error ?? ""}`.trim()
  }
  switch (p.intent) {
    case "remember":
      return `Saved as a signed fact, durable on disk in ${n(a.ms, 2)} ms. ${
        b?.ok ? "The chain and every signature still verify." : "Verify did not pass, check the trace."
      }`
    case "get":
      return `Found it: **${(a.fact as Json)?.title ?? ""}**.`
    case "gates": {
      const t = a.totals as { passed: number; failed: number }
      return t.failed === 0
        ? `All gates pass: ${n(t.passed)} checks, 0 failed.`
        : `${n(t.failed)} checks failed out of ${n(t.passed + t.failed)}. The failures are open below.`
    }
    case "bench":
      return `${n(a.facts)} facts: ingest ${n(a.write_per_sec)}/s, scan ${n(a.scan_per_sec)}/s, full verify ${n(a.verify_per_sec)}/s. Ingest is bound by Ed25519 signing.`
    case "verify":
      return `Clean. Chain and signatures verify in ${n(a.verify_ms, 1)} ms, and a fresh ${n(a.checkpoint_bytes)} byte checkpoint verifies too.`
    case "recall": {
      const hits = keywordFilter(((b?.facts as Json[]) ?? []), p.query ?? "")
      const lead = a.ok
        ? `Recall returned ${(a.hits as unknown[]).length} hits.`
        : "Fused recall is not in this engine yet (it lands in M4), so I scanned the log by keyword instead."
      return hits.length
        ? `${lead}\n\n${hits.map((f) => `- **${f.title}** (${f.kind}, seq ${f.seq})`).join("\n")}`
        : `${lead} Nothing in the log matches "${p.query}".`
    }
    case "scan":
      return a.total === 0
        ? "The log is empty. Tell me something to remember."
        : `${n(a.total)} facts in the log. Here are the last ${(a.facts as unknown[]).length}.`
    case "stats":
      return `Engine ${a.version}, ${n(a.facts)} facts, node key ${String(a.node_pubkey).slice(0, 12)}.`
  }
  return ""
}
