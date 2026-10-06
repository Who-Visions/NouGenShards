// Deterministic, model-free page distillation. Extractive only: every shard sentence is
// a sentence from the page, in page order. No claims are invented.
const STOP = new Set("the a an and or but if then of to in on at by for with from as is are was were be been being it its this that these those you your we our they their them not no can will would should could may might also than so such into about over more most other some any all each which who whom what when where why how there here just very".split(" "));

export function splitSentences(text) {
  return String(text || "")
    .replace(/\s+/g, " ")
    .split(/(?<=[.!?])\s+(?=[A-Z0-9"“(])/)
    .map((s) => s.trim())
    .filter((s) => s.length >= 40 && s.length <= 400);
}

const tokens = (s) => s.toLowerCase().match(/[a-z][a-z0-9'-]{3,}/g)?.filter((w) => !STOP.has(w)) || [];

export function distill(text, { maxSentences = 12, perShard = 3 } = {}) {
  const sents = [...new Set(splitSentences(text))];
  if (!sents.length) return [];
  const tf = new Map();
  for (const s of sents) for (const w of tokens(s)) tf.set(w, (tf.get(w) || 0) + 1);
  const scored = sents.map((s, i) => {
    const t = tokens(s);
    const base = t.reduce((a, w) => a + (tf.get(w) || 0), 0) / Math.sqrt(t.length || 1);
    return { s, i, score: base * (i < 3 ? 1.15 : 1) };
  });
  const picked = scored.sort((a, b) => b.score - a.score).slice(0, maxSentences).sort((a, b) => a.i - b.i);
  const shards = [];
  for (let i = 0; i < picked.length; i += perShard) shards.push(picked.slice(i, i + perShard).map((p) => p.s).join(" "));
  return shards;
}

export function buildMorph({ url, title, text, goal, now = new Date() }) {
  const parts = distill(text);
  if (!parts.length) return null;
  let host = "";
  try { host = new URL(url).hostname; } catch { /* keep empty */ }
  const name = (title || host || "untitled").slice(0, 100);
  const shards = parts.map((body, i) => ({
    event_type: "KNOWLEDGE",
    title: `Morph: ${name} [${i + 1}/${parts.length}]`,
    content: `Source: ${url}\nMorphed: ${now.toISOString()}\nPart: ${i + 1}/${parts.length} (extractive distillation)\n\n${body}`,
    tags: ["nougenmorph", "chrome-capture", ...(host ? [host] : [])],
  }));
  const g = String(goal || "").trim();
  // A destiny exists only when the user states the goal; we never invent intent.
  const destiny = g.length >= 3 ? {
    title: `Morph: ${name}`.slice(0, 120),
    goal: g,
    trigger: `url:${url}`,
    verification: "Linked shards from this page exist and support the goal; review before marking fulfilled.",
    status: "dormant",
    actor: "nougen-chrome",
  } : null;
  return { shards, destiny };
}
