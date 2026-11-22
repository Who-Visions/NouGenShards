// Morph's pure logic: the 21 steps and the checks on a written plan. No DOM, no chrome.* calls, so it runs in node too.
// Loaded before content.js (manifest order); content.js reads it as NGT_MORPH.
(function (root) {
  const NL = String.fromCharCode(10);

  // The 21 steps of the NouGenMorph orchestration (NouGen docs/architecture.md), in order, by phase.
  const V21 = ["Metamers", "Activate Orchestration", "Deep Grep Latent Structure", "Surface Leverage", "Extract Invariants", "Copy Successful Topology",
    "Transpose Patterns", "Combine Compatible Systems", "Synthesize Coherent Signal", "Integrate Constraints", "Transform Architecture", "Refactor Complexity",
    "Compress Noise", "Expand Solution Space", "Remix Viable Patterns", "Invert Assumptions", "Reverse-Engineer Intent", "Reconstruct Coherence",
    "Stabilize Reasoning", "Iterate Recursively", "Orchestrate Convergence"];
  const V21_PHASE = ["Reconnaissance (1-4): find what is really there", "Extraction (5-8): pull out what holds true and map it over",
    "Substrate (9-12): make it solid and safe", "Dream state (13-19): compress, widen, remix, question, verify", "Loop (20-21): repeat and converge"];
  const V21_ASK = NL + "### Valerion pass" + NL + "Apply the 21 steps of NouGenMorph orchestration to this build. Write a numbered list of exactly 21 lines in this order. " +
    "Each line is: the number, the step name exactly as given, a colon, then ONE sentence saying what that step concretely means for turning this video and these vault and web sources into the target. " +
    "Cite [m:ss], shard references or web tags where they apply. Do not skip, merge or rename steps. The phases are: " + V21_PHASE.join("; ") + "." + NL +
    V21.map((n, i) => (i + 1) + ". " + n).join(NL);

  const norm = s => String(s).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

  // Every citation inside square brackets, including grouped ones: [12@db3], [12@db3, 14@db3], [w1, w2].
  function citations(text) {
    const shards = new Set(), web = new Set();
    for (const g of String(text).matchAll(/\[([^\[\]\n]{1,300})\]/g)) {
      for (const part of g[1].split(/[,;]/)) {
        const p = part.trim();
        if (/^\d+@db\d+$/.test(p)) shards.add(p);
        else if (/^w\d+$/.test(p)) web.add(p);
      }
    }
    return { shards: [...shards], web: [...web] };
  }

  // Numbered lines "N. Step name: ..." -> the step numbers found with the right name at the right number.
  function v21Found(text) {
    const found = new Set();
    let last = 0;     // a step only counts if it comes after the previous counted one, so a shuffled list cannot pass
    for (const m of String(text).matchAll(/^\s*(?:[-*]\s*)?(\d{1,2})[.)]\s*\**\s*([^:\n]{2,60}?)\s*\**\s*(?::|\s[-–—]\s|[–—])/gm)) {
      const n = +m[1];
      if (n >= 1 && n <= 21 && n > last && norm(m[2]).startsWith(norm(V21[n - 1]))) { found.add(n); last = n; }
    }
    return found;
  }

  // The model's route stamp is appended as a last line starting with a dash; it is not plan content.
  const body = text => String(text).replace(/\n+\s*— [^\n]*$/, "").trim();

  const hasHeading = (text, name) => new RegExp("^#{2,4}\\s*" + name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b", "im").test(text);

  // M: {text, shards:[{id,db}], web:[{ref, text}], v21, vaultOff, webOff}. refOf maps a shard to "id@dbN".
  function checkPlan(M, refOf) {
    const text = body(M.text || ""), cit = citations(text);
    const known = new Set((M.shards || []).map(refOf)), webs = new Map((M.web || []).map(w => [w.ref, w]));
    const sections = ["Intent of the video", "What the vault already has", "Morph plan", "First build steps", "Gaps"];
    if ((M.web || []).length) sections.splice(3, 0, "Latest on the web");
    if (M.v21) sections.push("Valerion pass");
    const missing = sections.filter(s => !hasHeading(text, s));
    // The last heading of the plan must have content under it, or the model stopped mid-sentence.
    const heads = [...text.matchAll(/^#{2,4}[^\n]*$/gm)];
    const last = heads.length ? text.slice(heads[heads.length - 1].index).replace(/^[^\n]*\n?/, "").trim() : "";
    const cutOff = heads.length > 0 && last.length < 20;
    const found = M.v21 ? v21Found(text) : new Set();
    const v21Missing = M.v21 ? V21.filter((_, i) => !found.has(i + 1)) : [];
    return {
      cited: cit.shards, bad: cit.shards.filter(c => !known.has(c)),
      web: cit.web, badWeb: cit.web.filter(w => !webs.has(w)), webRead: cit.web.filter(w => webs.get(w) && webs.get(w).text).length,
      missing, cutOff, v21Missing,
    };
  }

  // The checks as plain lines {ok, text}: shown in the panel and written into the saved or copied plan.
  function report(M, k, ts) {
    const out = [], plural = (n, w) => n + " " + w + (n === 1 ? "" : "s");
    if (M.vaultOff) out.push({ ok: false, text: "The vault could not be read, so this plan is built from the video alone" });
    out.push(k.bad.length ? { ok: false, text: plural(k.bad.length, "cited shard") + " not among those the vault returned: " + k.bad.join(", ") }
      : { ok: true, text: plural(k.cited.length, "shard") + " cited, all returned by the vault" });
    if (!k.cited.length && (M.shards || []).length && !M.vaultOff) out.push({ ok: false, text: "The plan cites no vault shards, so it does not yet build on what you have" });
    if (M.v21) out.push(k.v21Missing.length ? { ok: false, text: "The Valerion pass is missing " + k.v21Missing.length + " of 21 steps: " + k.v21Missing.slice(0, 4).join(", ") + (k.v21Missing.length > 4 ? " and more" : "") }
      : { ok: true, text: "The Valerion pass has all 21 steps, numbered in order" });
    if (k.missing.length || k.cutOff) out.push({ ok: false, text: "The plan looks incomplete." + (k.missing.length ? " Missing sections: " + k.missing.join(", ") + "." : "") + (k.cutOff ? " The last section is empty." : "") + " Press Morph again, or pick another model" });
    if (M.webOff) out.push({ ok: false, text: "The web could not be searched for this plan: " + M.webOff });
    else if ((M.web || []).length) out.push(k.badWeb.length ? { ok: false, text: plural(k.badWeb.length, "cited web source") + " not among those found: " + k.badWeb.join(", ") }
      : { ok: true, text: k.web.length + " of " + M.web.length + " web sources cited, all real (" + k.webRead + " of the cited were read in full, the rest are search snippets)" });
    out.push(ts.bad.length ? { ok: false, text: plural(ts.bad.length, "timestamp") + " fall outside the video" }
      : ts.ts ? { ok: true, text: ts.ts + " timestamps cited, all inside the video" } : { ok: false, text: "The plan cites no timestamps from the video" });
    return out;
  }

  // A link target from search results is only used as a link when it is http(s).
  const safeUrl = u => (/^https?:\/\//i.test(String(u)) ? u : "#");

  const api = { V21, V21_PHASE, V21_ASK, citations, v21Found, checkPlan, report, body, safeUrl };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.NGT_MORPH = api;
})(typeof self !== "undefined" ? self : globalThis);
