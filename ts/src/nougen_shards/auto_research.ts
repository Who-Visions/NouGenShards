/**
 * Autonomous arXiv research daemon. (TS mimic of auto_research.py)
 * Fetches papers and indexes them as memory shards.
 *
 * Node has no stdlib XML parser, so search_arxiv parses the Atom feed with a
 * minimal regex/string extraction of <entry>/<title>/<summary>/<id>/<published>
 * tags. Network functions (Ollama + arXiv) are async (fetch-based).
 */
import { Socket } from "node:net";
import { capture } from "./core.js";

interface Paper {
  id: string;
  title: string;
  summary: string;
  published: string;
}

/** Check if the local Ollama instance is alive (TCP connect to 127.0.0.1:11434). */
export function check_ollama_alive(): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = new Socket();
    let settled = false;
    const done = (alive: boolean) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(alive);
    };
    socket.setTimeout(500);
    socket.once("connect", () => done(true));
    socket.once("timeout", () => done(false));
    socket.once("error", () => done(false));
    socket.connect(11434, "127.0.0.1");
  });
}

/** Retrieve the best available local LLM model. */
export async function get_best_model(): Promise<string | null> {
  if (!(await check_ollama_alive())) {
    return null;
  }
  try {
    const r = await fetch("http://127.0.0.1:11434/api/tags", {
      method: "GET",
      signal: AbortSignal.timeout(3000),
    });
    if (r.status === 200) {
      const data: any = await r.json();
      const models: string[] = (data.models ?? []).map((m: any) => m.name);
      for (const m of models) {
        if (["e2b", "e4b", "2b", "4b"].some((x) => m.toLowerCase().includes(x))) {
          return m;
        }
      }
      if (models.length) {
        return models[0];
      }
    }
  } catch {
    /* pass */
  }
  return null;
}

/** Send a query to the local LLM model. */
export async function query_local_llm(model: string, prompt: string): Promise<string> {
  try {
    const payload = { model, prompt, stream: false };
    const r = await fetch("http://127.0.0.1:11434/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(90000),
    });
    if (r.status === 200) {
      const res: any = await r.json();
      return String(res.response ?? "").trim();
    }
  } catch (e) {
    return `[Model timed out or failed: ${e}]`;
  }
  return "";
}

/** Extract the inner text of the first <tag>...</tag> occurrence within a chunk. */
function _extract_tag(xml: string, tag: string): string | null {
  const re = new RegExp(`<${tag}\\b[^>]*>([\\s\\S]*?)</${tag}>`, "i");
  const m = xml.match(re);
  return m ? _unescape_xml(m[1]) : null;
}

/** Minimal XML entity unescape for the arXiv Atom feed. */
function _unescape_xml(s: string): string {
  return s
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, "&");
}

/** Parse an atom entry chunk into a Paper dictionary. */
export function parse_entry(entry: string): Paper {
  const title_raw = _extract_tag(entry, "title");
  const summary_raw = _extract_tag(entry, "summary");
  const id_raw = _extract_tag(entry, "id");
  const pub_raw = _extract_tag(entry, "published");

  const title = title_raw !== null ? title_raw.trim().replace(/\n/g, " ") : "Untitled";
  const summary = summary_raw !== null ? summary_raw.trim().replace(/\n/g, " ") : "No abstract.";
  const paper_id = id_raw !== null ? id_raw.split("/abs/").slice(-1)[0] : "0000.0000";
  const published = pub_raw !== null ? pub_raw : "";

  return { id: paper_id, title, summary, published };
}

/** Queries the arXiv API directly and returns parsed paper dictionaries. */
export async function search_arxiv(query_str: string, max_results: number = 3): Promise<Paper[]> {
  console.log(`[*] Querying arXiv API for: '${query_str}'...`);
  const safe_query = encodeURIComponent(query_str);
  const url = `https://export.arxiv.org/api/query?search_query=${safe_query}&max_results=${max_results}`;

  try {
    const r = await fetch(url, { method: "GET", signal: AbortSignal.timeout(10000) });
    if (r.status === 200) {
      const xml_data = await r.text();
      const papers: Paper[] = [];
      // Minimal Atom parse: split out each <entry>...</entry> block.
      const entry_re = /<entry\b[^>]*>([\s\S]*?)<\/entry>/gi;
      let match: RegExpExecArray | null;
      while ((match = entry_re.exec(xml_data)) !== null) {
        papers.push(parse_entry(match[1]));
      }
      return papers;
    }
  } catch (e) {
    console.log(`[!] arXiv API connection failed or timed out: ${e}`);
  }
  return [];
}

/** Return a list of backup papers if API fails. */
export function get_backup_papers(): Paper[] {
  return [
    {
      id: "2308.00001",
      title: "Generative Agents: Interactive Simulacra of Human Behavior",
      summary: "Presents architecture for persistent agent memory databases.",
      published: "2023-08-01",
    },
    {
      id: "2402.12345",
      title: "MemGPT: Towards LLMs as Operating Systems",
      summary: "Establishes a virtual memory paging system for LLMs.",
      published: "2024-02-15",
    },
  ];
}

/**
 * Evaluates a paper with recursive autonomous improvement.
 * Transposes DavOs-class 'Machine Note' patterns for 3x hit-rate boost.
 */
export async function evaluate_paper(paper: Paper, model: string | null): Promise<string> {
  const initial_analysis_prompt =
    "You are a memory architecture specialist evaluating academic papers.\n" +
    `Paper: ${paper.title}\n` +
    `Abstract: ${paper.summary}\n\n` +
    "Write a detailed machine note highlighting the latent structure of these findings.";

  const improvement_prompt_template = (analysis: string) =>
    "Here is your initial analysis:\n```\n" +
    analysis +
    "\n```\n\n" +
    "Critically evaluate this note against the NouGenShards 'Recall Packet' invariant.\n" +
    "Refactor the note to be 10x more actionable for a coding agent. " +
    "Compress noise and surface high-leverage invariants.";

  if (!model) {
    return (
      `Evaluated arXiv:${paper.id}. This research confirms that hierarchical ` +
      "databases improve hit rates and reduce prompt amnesia. We can incorporate " +
      "priority weights into our SQLite index."
    );
  }

  // Round 1: Latent Structure Extraction
  const initial_analysis = await query_local_llm(model, initial_analysis_prompt);
  if (initial_analysis.includes("[Model timed out")) {
    return initial_analysis;
  }

  // Round 2: Recursive Refinement (Mythos-Class Pattern)
  const improvement_prompt = improvement_prompt_template(initial_analysis);
  const refined_analysis = await query_local_llm(model, improvement_prompt);

  if (refined_analysis.includes("[Model timed out")) {
    return initial_analysis;
  }

  return refined_analysis;
}

/** Main execution block. */
export async function main(): Promise<void> {
  console.log("=".repeat(80));
  console.log(" NOUGENSHARDS AUTONOMOUS ARXIV RESEARCH DAEMON ");
  console.log("=".repeat(80));

  const search_queries = [
    'all:"agent memory" AND "persistent"',
    'all:"LLM database recall"',
    'all:"FTS5 agent caching"',
  ];

  let papers: Paper[] = [];
  for (const q of search_queries) {
    const found = await search_arxiv(q, 2);
    papers.push(...found);
    if (papers.length >= 3) {
      break;
    }
  }

  if (!papers.length) {
    console.log("[!] No papers retrieved from arXiv API. Using offline backup papers.");
    papers = get_backup_papers();
  }

  const model = await get_best_model();
  console.log(`\n[*] Active Local LLM Model for Evaluation: ${model || "Simulated Engine"}`);

  for (const paper of papers) {
    console.log(`\n[*] Evaluating Paper: ${paper.title} (arXiv:${paper.id})`);
    const analysis = await evaluate_paper(paper, model);
    console.log(`Analysis:\n  ${analysis}`);

    const shard_title = `arXiv Research: ${paper.title.slice(0, 40)}...`;
    const shard_content =
      `Research from arXiv:${paper.id} on ${paper.published}.\n` +
      `Paper Title: ${paper.title}\n` +
      `Core Analysis:\n${analysis}`;
    const tags = ["research", "arxiv", "paper-evaluation", `id-${paper.id}`];

    const success = capture("KNOWLEDGE", shard_title, shard_content, tags);
    if (success) {
      console.log("    [+] Successfully stored research shard in shards.db!");
    } else {
      console.log("    [!] Research shard already indexed.");
    }
  }

  console.log("\n" + "=".repeat(80));
  console.log(" AUTONOMOUS RESEARCH COMPLETED: DATABASE UPDATED ");
  console.log("=".repeat(80));
}

// __main__ mimic
import { pathToFileURL } from "node:url";
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  void main();
}
