// NouGenTube content script: panel injected beside the YouTube player.
(() => {
  const S = { vid: null, lines: [], title: "", tab: "transcript", follow: true, summary: "", chat: [], hl: {}, port: null };
  const fmt = s => { s = Math.floor(s); const h = s / 3600 | 0, m = (s % 3600) / 60 | 0, x = s % 60; return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(x).padStart(2, "0"); };
  const parseTs = t => t.split(":").map(Number).reduce((a, b) => a * 60 + b, 0);
  const esc = t => String(t ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const video = () => document.querySelector("video.html5-main-video, video");
  const seek = t => { const v = video(); if (v) { v.currentTime = t; v.play(); } };

  // ---------- transcript fetch (two tiers) ----------
  async function playerResponse(vid) {
    const html = await (await fetch("/watch?v=" + vid, { credentials: "include" })).text();
    const grab = k => { const i = html.indexOf(k + " = {"); if (i < 0) return null; let d = 0, s = html.indexOf("{", i);
      // Braces inside JSON strings ("Foo } bar" in a title) are not delimiters: track string state and \ escapes.
      let str = false, bs = false;
      for (let j = s; j < html.length; j++) { const c = html[j];
        if (str) { if (bs) bs = false; else if (c === "\\") bs = true; else if (c === '"') str = false; continue; }
        if (c === '"') str = true; else if (c === "{") d++;
        else if (c === "}" && --d === 0) { try { return JSON.parse(html.slice(s, j + 1)); } catch { return null; } } }
      return null; };
    return { pr: grab("ytInitialPlayerResponse"), data: grab("ytInitialData"), key: (html.match(/"INNERTUBE_API_KEY":"([^"]+)"/) || [])[1],
             ver: (html.match(/"INNERTUBE_CLIENT_VERSION":"([^"]+)"/) || [])[1] };
  }
  async function viaTimedtext(pr) {
    const tracks = pr?.captions?.playerCaptionsTracklistRenderer?.captionTracks || [];
    if (!tracks.length) return null;
    const pref = await chrome.storage.sync.get("lang"); const want = pref.lang || "en";
    const t = tracks.find(t => t.languageCode === want && t.kind !== "asr") || tracks.find(t => t.languageCode === want) || tracks.find(t => t.languageCode?.startsWith("en")) || tracks[0];
    const r = await fetch(t.baseUrl + "&fmt=json3"); const txt = await r.text(); if (!txt) return null;
    const j = JSON.parse(txt);
    const out = (j.events || []).filter(e => e.segs).map(e => ({ t: e.tStartMs / 1000, text: e.segs.map(s => s.utf8).join("").replace(/\s+/g, " ").trim() })).filter(l => l.text);
    return out.length ? { lines: out, lang: t.name?.simpleText || t.languageCode } : null;
  }
  async function viaInnertube(p) {
    const s = JSON.stringify(p.data || {}); const params = (s.match(/"getTranscriptEndpoint":\{"params":"([^"]+)"/) || [])[1];
    if (!params || !p.key) return null;
    const r = await fetch("/youtubei/v1/get_transcript?key=" + p.key, { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ context: { client: { clientName: "WEB", clientVersion: p.ver || "2.20250101" } }, params }) });
    const j = await r.json(); const segs = JSON.stringify(j).match(/"transcriptSegmentRenderer":\{.*?"startMs":"\d+".*?\}\}\]\}/g) || [];
    const out = [];
    const walk = o => { if (!o || typeof o !== "object") return; if (o.transcriptSegmentRenderer) { const x = o.transcriptSegmentRenderer;
      const text = (x.snippet?.runs || []).map(r => r.text).join("").trim(); if (text) out.push({ t: +x.startMs / 1000, text }); return; }
      for (const k in o) walk(o[k]); };
    walk(j); return out.length ? { lines: out, lang: "auto" } : null;
  }
  // Tier 0: YouTube's own transcript panel (carries the player's PO token, so it survives API gating).
  // Resolved at page runtime: a MutationObserver follows YouTube as it renders, clicks
  // "Show transcript" whenever that button exists for the current video, and reads the rows
  // once their count holds still. No fixed waits, so in-app navigation can't race it.
  // Handles both layouts: classic (ytd-transcript-segment-renderer, target-id*=transcript)
  // and modern (transcript-segment-view-model, often no target-id).
  const EP = "ytd-engagement-panel-section-list-renderer";
  const PANELS = [`${EP}[target-id*=transcript]`, `${EP}:has(transcript-segment-view-model)`,
    `${EP}:has(ytd-transcript-segment-renderer)`, `${EP}:has(textarea[placeholder*="ranscript"])`].join(",");
  const SEGS = "ytd-transcript-segment-renderer, transcript-segment-view-model";
  const BTN = "ytd-video-description-transcript-section-renderer button";
  let lastFirst = "";   // first row of the previous video, so a stale list is never read as the new one
  // Some pages hold BOTH layouts at once. Reading both doubled the transcript, so use one:
  // whichever has more rows.
  const oneLayout = () => { const a = document.querySelectorAll("ytd-transcript-segment-renderer"), b = document.querySelectorAll("transcript-segment-view-model");
    return [...(a.length >= b.length ? a : b)]; };
  // Transcript times only move forward. If they jump back by more than a minute, what follows
  // is a second copy (older saved transcripts can contain one): keep the first.
  const monotonic = lines => { for (let i = 1; i < lines.length; i++) if (lines[i].t < lines[i - 1].t - 60) return lines.slice(0, i); return lines; };
  const readRows = () => oneLayout().map(s => {
    const [ts, tx] = s.tagName === "YTD-TRANSCRIPT-SEGMENT-RENDERER"
      ? [s.querySelector(".segment-timestamp")?.textContent, s.querySelector(".segment-text")?.textContent]
      : [s.querySelector(".ytwTranscriptSegmentViewModelTimestamp")?.textContent, s.querySelector(".ytAttributedStringHost, span")?.textContent];
    return { t: parseTs((ts || "0").trim()), text: (tx || "").replace(/\s+/g, " ").trim() };
  }).filter(l => l.text);

  // False once the extension has been reloaded under this tab (the old copy is orphaned).
  const alive = () => { try { return !!chrome.runtime?.id; } catch { return false; } };

  // ---- Player tier: inject.js (page world) forwards the caption track the player itself
  // downloads. Works in background tabs and when YouTube's transcript panel misbehaves.
  const TT = {};   // video id -> raw caption track body
  window.addEventListener("message", e => {
    if (e.source !== window || e.data?.__ngt !== "timedtext") return;
    try { const v = new URL(e.data.url, location.origin).searchParams.get("v");
      if (v && (!TT[v] || e.data.body.length > TT[v].length)) TT[v] = e.data.body; } catch {}
  });
  function pageInfo() {   // which caption tracks does the player say this video has?
    return new Promise(res => { const id = Math.random().toString(36).slice(2);
      const on = e => { if (e.source === window && e.data?.__ngt === "info" && e.data.id === id) { window.removeEventListener("message", on); res(e.data); } };
      window.addEventListener("message", on); window.postMessage({ __ngt: "info?", id }, location.origin);
      setTimeout(() => { window.removeEventListener("message", on); res(null); }, 1200); });
  }
  function parseTrack(body) {
    const clean = t => t.replace(/\s+/g, " ").trim();
    if (body.trim().startsWith("{")) {   // json3
      return (JSON.parse(body).events || []).filter(ev => ev.segs)
        .map(ev => ({ t: (ev.tStartMs || 0) / 1000, text: clean(ev.segs.map(x => x.utf8 || "").join("")) })).filter(l => l.text);
    }
    const doc = new DOMParser().parseFromString(body, "text/xml");   // srv1 <text start=> / srv3 <p t=>
    return [...doc.querySelectorAll("text, p")].map(n => ({
      t: n.hasAttribute("start") ? parseFloat(n.getAttribute("start")) : (parseInt(n.getAttribute("t"), 10) || 0) / 1000,
      text: clean(n.textContent) })).filter(l => l.text);
  }
  // The track the player has already downloaded for this video, if any (no clicks needed).
  const captured = vid => { try { const l = TT[vid] && parseTrack(TT[vid]); return l && l.length ? { lines: l, lang: "YouTube captions" } : null; } catch { return null; } };
  async function viaPlayer(vid) {
    const wait = ms => new Promise(r => setTimeout(r, ms));
    const got = () => captured(vid);
    let r = got(); if (r) return r;
    const cc = document.querySelector(".ytp-subtitles-button");
    if (!cc || cc.getAttribute("aria-disabled") === "true" || getComputedStyle(cc).display === "none") return null;
    // Switching captions on makes the player download the track; put the button back afterwards.
    const wasOn = cc.getAttribute("aria-pressed") === "true";
    if (wasOn) { cc.click(); await wait(250); }
    cc.click();
    for (let i = 0; i < 40 && !(r = got()); i++) await wait(200);
    if (!wasOn && cc.getAttribute("aria-pressed") === "true") cc.click();
    return r;
  }

  // ---- Saved transcripts: the 40 most recent videos, so a revisit is instant and offline-safe.
  const cacheGet = async vid => { const k = "t:" + vid, v = (await chrome.storage.local.get(k))[k];
    return v?.lines?.length ? { lines: v.lines, lang: "saved" } : null; };
  async function cachePut(vid, r) {
    try {
      const { tIdx = [] } = await chrome.storage.local.get("tIdx");
      const idx = [vid, ...tIdx.filter(x => x !== vid)], drop = idx.splice(40);
      await chrome.storage.local.set({ ["t:" + vid]: { lines: r.lines, at: Date.now() }, tIdx: idx });
      if (drop.length) await chrome.storage.local.remove(drop.map(x => "t:" + x));
    } catch (e) { console.warn("[NouGenTube] could not save transcript", e); }
  }

  function viaPanel(vid, limitMs = 45000) {
    const curVid = () => new URLSearchParams(location.search).get("v");
    document.querySelectorAll("style[data-nougentube]").forEach(x => x.remove());
    const userOpen = !!document.querySelector(SEGS) && [...document.querySelectorAll(PANELS)].some(p => p.getAttribute("visibility") === "ENGAGEMENT_PANEL_VISIBILITY_EXPANDED");
    const style = document.createElement("style"); style.dataset.nougentube = "1";
    style.textContent = `${PANELS}{opacity:0!important;pointer-events:none!important}`;
    if (!userOpen) document.head.append(style);
    return new Promise(resolve => {
      let clickedAt = 0, lastCount = -1, stableSince = 0, done = false, raf = 0; const t0 = performance.now();
      const finish = rows => {
        if (done) return; done = true; try { document.removeEventListener("visibilitychange", kick); } catch {} obs.disconnect(); clearInterval(tick); clearTimeout(limit);
        if (!userOpen) {
          document.querySelector(`${PANELS.split(",")[0]} #visibility-button button`)?.click();
          style.textContent = `${PANELS}{display:none!important}`;   // newer panels render even when "HIDDEN"
          const release = e => { if (e.isTrusted && e.target.closest?.("ytd-video-description-transcript-section-renderer")) { style.remove(); document.removeEventListener("click", release, true); } };
          document.addEventListener("click", release, true);
          document.addEventListener("yt-navigate-start", () => { style.remove(); document.removeEventListener("click", release, true); }, { once: true });
        }
        if (rows?.length) lastFirst = rows[0].text;
        resolve(rows?.length ? { lines: rows, lang: "YouTube" } : null);
      };
      const step = () => {
        raf = 0;
        if (done) return;
        if (curVid() !== vid) return finish(null);           // viewer moved on
        if (document.hidden) return setStage("Waiting for this tab to be visible");   // YouTube renders nothing off-screen
        const rows = readRows();
        const fresh = rows.length && rows[0].text !== lastFirst;
        if (fresh) {
          setStage(`Reading ${rows.length} lines`);
          if (rows.length !== lastCount) { lastCount = rows.length; stableSince = performance.now(); }
          else if (performance.now() - stableSince > 500) return finish(rows);
          return;
        }
        const b = document.querySelector(BTN);
        if (b && performance.now() - clickedAt > 4000) { clickedAt = performance.now(); b.click(); setStage("Opening YouTube's transcript"); }
        else if (!b) { setStage("Waiting for YouTube's page");
          // No transcript button after 6s, or the player already has the captions: let the next source answer.
          if (performance.now() - t0 > 6000 || (performance.now() - t0 > 1500 && captured(vid))) return finish(null); }
      };
      const kick = () => { if (!raf) raf = requestAnimationFrame(step); };
      const obs = new MutationObserver(kick);
      obs.observe(document.body, { childList: true, subtree: true });
      const tick = setInterval(kick, 600);                    // also re-check when the DOM is quiet
      document.addEventListener("visibilitychange", kick);
      const limit = setTimeout(() => finish(null), document.hidden ? 864e5 : limitMs);
      kick();
    });
  }
  // merge tiny caption events into readable ~20s paragraphs
  function paragraphs(lines) {
    const out = []; let cur = null;
    for (const l of lines) { if (!cur || l.t - cur.t > 20 || cur.text.length > 320) { cur = { t: l.t, text: l.text }; out.push(cur); } else cur.text += " " + l.text; }
    return out;
  }

  // ---------- UI ----------
  // Colorways come from the generated design package (design-tokens.js <- designs/mono-violet/design.json),
  // never inline copies. Short names keep the panel CSS terse; "dark" is the default, others key off data-theme.
  const TOKEN_MAP = { bg: "--bg", card: "--surface", raised: "--raised", ln: "--border", lns: "--border-strong", tx: "--text",
    mu: "--muted", ac: "--accent", ac2: "--extra", ok: "--good", warn: "--warn", bad: "--bad", ink: "--control-ink",
    focus: "--focus", r: "--radius-control", rp: "--radius-panel", ow: "--outline-width" };
  const PALETTES = Object.entries(NGT_TOKENS.themes).sort(([a], [b]) => (a === "dark" ? -1 : b === "dark" ? 1 : a < b ? -1 : 1))
    .map(([name, t]) => (name === "dark" ? ".p{" : `.p[data-theme=${name}]{`) + Object.entries(TOKEN_MAP).map(([k, v]) => `--${k}:${t[v]}`).join(";") + "}")
    .join("\n  ");
  let host, root;
  const CSS = `
  :host{all:initial} *{box-sizing:border-box}
  .p{font:14px/1.5 "Geist","Roboto",system-ui,sans-serif;color:var(--tx);background:var(--bg);border:var(--ow) solid var(--ln);border-radius:var(--rp);margin:0 0 12px;overflow:hidden;display:flex;flex-direction:column;max-height:calc(100vh - 140px)}
  ${PALETTES}
  .p[data-theme=hardcade] .tabs button{text-transform:uppercase;letter-spacing:.06em;font-size:12px}
  @supports (corner-shape:squircle){.p[data-theme=arcade],.p[data-theme=arcade] :is(button,select,input,textarea,.chip,.msg,.vf,.card,.menu,.ib){corner-shape:squircle}}
  @media (prefers-contrast:more){.p[data-theme]{--ln:var(--lns);--mu:var(--tx)}.p :is(button,select,input,textarea,.chip,.vf,.msg,.card,.menu){border-width:2px}.p :is(button,select,input,a,summary,[tabindex]):focus-visible{outline-width:3px}}
  @media (forced-colors:active){:is(button,select,input,textarea,.chip,.vf,.msg,.card,.menu){border:1px solid ButtonText}.tabs button.on,.chip.on,button.go{outline:2px solid Highlight;outline-offset:-2px}a,.t{color:LinkText}.vok{color:Highlight}.bar::after{background:Highlight}}
  .p{color-scheme:dark;accent-color:var(--ac)}.p[data-theme=light]{color-scheme:light}
  :host([data-flow=below]) .p{height:min(640px,calc(100dvh - 120px))}
  :is(button,select,input,a,summary,[tabindex]):focus-visible{outline:2px solid var(--focus);outline-offset:2px}
  .hd{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--ln)}
  .lg{width:26px;height:26px;border-radius:var(--r);background:linear-gradient(135deg,var(--ac),var(--ac2));display:grid;place-items:center;font-weight:800;color:var(--ink);font-size:13px}
  .ti{font-weight:700;font-size:15px;flex:1 1 0;min-width:0;line-height:1.25}.ti small{display:block;color:var(--mu);font-weight:400;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  button,select,input{font:inherit;color:inherit}
  .ib{background:none;border:0;cursor:pointer;color:var(--mu);padding:4px 6px;border-radius:6px}.ib:hover{background:var(--card);color:var(--tx)}
  .tabs{display:flex;border-bottom:1px solid var(--ln)}.tabs button{flex:1 1 auto;background:none;border:0;padding:10px 2px;font-size:13px;cursor:pointer;color:var(--mu);font-weight:600;border-bottom:2px solid transparent}
  .tabs button.on{color:var(--tx);border-color:var(--ac)}
  .tb{display:flex;gap:6px;padding:8px 12px;align-items:center;border-bottom:1px solid var(--ln)}
  .tb input{flex:1;background:var(--card);border:1px solid var(--ln);border-radius:var(--r);padding:6px 10px}
  .tb select{background:var(--card);border:1px solid var(--ln);border-radius:var(--r);padding:5px;max-width:150px}
  .chip{background:var(--card);border:1px solid var(--ln);border-radius:calc(var(--r) * 99);padding:4px 10px;cursor:pointer;font-size:12px;white-space:nowrap}.chip.on{border-color:var(--ac);color:var(--ac)}
  .bd{overflow-y:auto;overscroll-behavior:contain;flex:1 1 auto;min-height:0;padding:6px 4px 12px;scrollbar-width:thin}
  #wrap{display:flex;flex-direction:column;flex:1 1 auto;min-height:0}#wrap[hidden]{display:none}
  .p{height:min(calc(100dvh - 140px),1400px);min-height:360px}
  .ln{display:flex;gap:10px;padding:7px 10px;border-radius:8px;cursor:pointer;position:relative}
  .ln:hover{background:var(--card)}.ln.now{background:color-mix(in srgb,var(--ac) 16%,transparent)}
  .ln.hl{box-shadow:inset 3px 0 var(--ac2)}
  /* YouTube red & gold (Figma: NouGenTube — YouTube Red & Gold) */
  .p[data-theme=youtube] .lg{background:var(--ac);border-radius:8px}
  .p[data-theme=youtube] .ti small{color:var(--ac2);font-weight:500}
  .p[data-theme=youtube] #hs{background:var(--ac);border-color:var(--ac);color:var(--ink);font-weight:600}
  .p[data-theme=youtube] .tabs button.on{border-bottom-color:transparent;border-image:linear-gradient(90deg,var(--ac),var(--ac2)) 1;font-weight:700}
  .p[data-theme=youtube] .chip.on{border-color:var(--ac2);color:var(--ac2)}
  .p[data-theme=youtube] .ts{font-weight:500}
  .p[data-theme=youtube] .ln.now{background:var(--raised);box-shadow:inset 3px 0 var(--ac)}
  .p[data-theme=youtube] .ln.hl{background:color-mix(in srgb,var(--ac2) 12%,transparent);box-shadow:inset 3px 0 var(--ac2)}
  .ts{color:var(--ac2);font-variant-numeric:tabular-nums;font-size:12px;min-width:42px;padding-top:2px;cursor:pointer;background:none;border:0;text-align:left}
  .st{position:absolute;right:6px;top:6px;opacity:0}.ln:hover .st{opacity:1}
  mark{background:var(--warn);color:var(--ink);border-radius:2px}
  .md{padding:8px 14px}
  .mm{margin-left:calc(var(--d) * 14px);border-left:2px solid color-mix(in srgb,var(--ac) 45%,transparent);padding:2px 0 2px 10px}
  .mm>summary{cursor:pointer;font-weight:600;list-style:none}.mm>summary::before{content:"▸ ";color:var(--ac)}.mm[open]>summary::before{content:"▾ "}
  .mm.leaf{font-weight:400}.mmw>details[style*="--d:0"]>summary{font-size:15px;color:var(--ac2)}
  .menu{position:absolute;right:10px;top:44px;background:var(--card);border:1px solid var(--ln);border-radius:var(--r);padding:4px;z-index:9;display:flex;flex-direction:column;min-width:170px}
  .menu[hidden]{display:none}.menu button{background:none;border:0;text-align:left;padding:7px 10px;border-radius:6px;cursor:pointer}.menu button:hover{background:var(--bg)}
  .hd{position:relative}.md h3{font-size:14px;margin:12px 0 4px}.md ul{padding-left:18px;margin:4px 0}.md li{margin:3px 0}
  .md a.t{color:var(--ac2);cursor:pointer;text-decoration:none;font-variant-numeric:tabular-nums}
  .mu{color:var(--mu);font-size:12px;padding:10px 14px}
  .go{background:var(--ac);color:var(--ink);border:0;border-radius:var(--r);padding:7px 14px;cursor:pointer;font-weight:600}
  .ld{padding:12px 14px}
  .lst{display:flex;align-items:center;gap:8px;color:var(--mu);font-size:12.5px}.lst b{color:var(--tx);font-weight:600}
  .lst .el{margin-left:auto;font-variant-numeric:tabular-nums;color:var(--mu)}
  .bar{height:3px;border-radius:3px;background:var(--ln);overflow:hidden;position:relative;margin:10px 0 6px}
  .bar::after{content:"";position:absolute;top:0;bottom:0;left:0;width:40%;background:linear-gradient(90deg,transparent,var(--ac),var(--ac2),transparent);animation:ngt-slide 1.2s ease-in-out infinite}
  @keyframes ngt-slide{from{transform:translateX(-100%)}to{transform:translateX(250%)}}
  .spin{width:14px;height:14px;flex:none;border:2px solid color-mix(in srgb,var(--ac) 30%,transparent);border-top-color:var(--ac);border-radius:50%;animation:ngt-rot .8s linear infinite;display:inline-block;vertical-align:-2px}
  .go .spin{border-color:color-mix(in srgb,var(--ink) 35%,transparent);border-top-color:var(--ink);margin-right:6px}
  @keyframes ngt-rot{to{transform:rotate(360deg)}}
  .skel{height:11px;border-radius:6px;margin:12px 14px;background:linear-gradient(90deg,var(--card) 0%,var(--ln) 50%,var(--card) 100%);background-size:200% 100%;animation:ngt-sh 1.3s linear infinite}
  .skel.ts{width:38px;display:inline-block;margin:0 0 0 14px}
  @keyframes ngt-sh{to{background-position:-200% 0}}
  .dots span{display:inline-block;width:6px;height:6px;margin:0 2px;border-radius:50%;background:var(--mu);animation:ngt-bo 1s infinite}
  .dots span:nth-child(2){animation-delay:.15s}.dots span:nth-child(3){animation-delay:.3s}
  @keyframes ngt-bo{0%,80%,100%{opacity:.25;transform:translateY(0)}40%{opacity:1;transform:translateY(-3px)}}
  .tail{padding:2px 14px 10px}
  @media (prefers-reduced-motion:reduce){.bar::after,.spin,.skel,.dots span{animation:none}}
  .note{padding:7px 12px;font-size:12.5px;border-bottom:1px solid var(--ln);color:var(--ok)}.note.bad{color:var(--warn)}.note[hidden]{display:none}
  .hd .chip{font:inherit;font-size:12px;color:var(--tx)}
  .acts{display:flex;flex-wrap:wrap;gap:6px;padding:10px 12px 2px}
  .vf{margin:6px 12px 12px;padding:10px 12px;border:1px solid var(--ln);border-radius:var(--r);background:var(--card);font-size:12.5px}
  .vh{font-weight:700;margin-bottom:6px}.vr{display:flex;gap:8px;padding:2px 0}.vr a,.md a[target]{color:var(--ac2);text-decoration:none}.vr a:hover,.md a[target]:hover{text-decoration:underline}.vok{color:var(--ok);font-weight:700}.vno{color:var(--warn);font-weight:700}
  .md table{border-collapse:collapse;margin:6px 0;font-size:12.5px}.md td,.md th{border:1px solid var(--ln);padding:4px 6px;text-align:left}
  .msg{margin:8px 12px;padding:8px 12px;border-radius:var(--r);background:var(--card)}.msg.u{background:color-mix(in srgb,var(--ac) 20%,transparent);margin-left:40px}
  .ft{display:flex;gap:6px;padding:8px 12px;border-top:1px solid var(--ln)}.ft input{flex:1;background:var(--card);border:1px solid var(--ln);border-radius:var(--r);padding:7px 10px}
  .err{color:var(--bad)}`;

  // YouTube hides its side column in the one-column layout (narrow windows, high browser zoom). The panel then sits
  // under the player instead of vanishing with the column. Like Electron's screen API: fit what is actually available.
  function slot() {
    const sec = document.querySelector("#secondary-inner, #secondary");
    if (sec && sec.getClientRects().length) return { el: sec, flow: "side" };
    const below = document.querySelector("#below");
    return below ? { el: below, flow: "below" } : null;
  }
  function place() {
    if (!host) return;
    const s = slot(); if (!s) return;
    if (host.parentElement !== s.el) s.el.prepend(host);
    host.dataset.flow = s.flow; host.style.position = s.flow === "side" ? "sticky" : "relative"; host.style.top = s.flow === "side" ? "72px" : "0";
  }
  function mount() {
    if (host?.isConnected) return true;
    const where = slot(); if (!where) return false;
    host = document.createElement("div"); host.id = "nougentube"; host.style.cssText = "top:72px;z-index:5;display:block"; where.el.prepend(host); place();
    root = host.attachShadow({ mode: "open" });
    // Actionable chips are native <button type=button>: focusable, Enter/Space for free, no role shims.
    root.innerHTML = `<style>${CSS}</style><div class="p">
      <div class="hd"><div class="lg">N</div><div class="ti">NouGenTube<small id="mdl"></small></div>
        <button class="chip" id="hs" title="Save this video to NouGenShards: the full transcript, plus the summary if you have made one">Shard</button><button class="ib" id="th" title="Theme">◐</button><button class="ib" id="key" title="Settings: provider keys and routes">⚙</button><button class="ib" id="cp" title="Copy transcript">⧉</button><button class="ib" id="dl" title="Export">⤓</button><div class="menu" id="menu" hidden><button data-x="md">Markdown (everything)</button><button data-x="txt">Transcript .txt</button><button data-x="srt">Subtitles .srt</button><button data-x="plain">Transcript, no timestamps</button><button data-x="obsidian">Obsidian note .md</button><button data-x="html">Readable page .html</button><button data-x="csv">Highlights + transcript .csv</button><button data-x="json">Everything .json</button></div>
        <button class="ib" id="col" title="Collapse">▾</button></div>
      <div class="note" id="note" hidden></div><div id="wrap"><div class="tabs"><button data-t="transcript">Transcript</button><button data-t="summary">Summary</button><button data-t="chat">Chat</button><button data-t="highlights">Highlights</button><button data-t="morph">Morph</button><button data-t="batch">Batch</button></div>
      <div class="tb" id="tb"></div><div class="bd" id="bd"></div><div id="ft"></div></div></div>`;
    applyTheme();   // the first paint already has the right colours; the saved choice arrives a moment later
    root.querySelector(".tabs").onclick = e => { const t = e.target.dataset.t; if (t) { S.tab = t; render(); } };
    root.getElementById("col").onclick = () => { const w = root.getElementById("wrap"); w.hidden = !w.hidden; root.querySelector(".p").style.height = w.hidden ? "auto" : ""; };
    root.getElementById("cp").onclick = () => navigator.clipboard.writeText(S.tr && !S.tr.busy && S.tr.out.some(Boolean) ? copyTextTr() : copyText()).then(() => { const b = root.getElementById("cp"); b.textContent = "✓"; setTimeout(() => b.textContent = "⧉", 1200); });
    root.getElementById("dl").onclick = e => { e.stopPropagation(); const m = root.getElementById("menu"); m.hidden = !m.hidden; };
    root.getElementById("menu").onclick = e => { const x = e.target.dataset.x; if (x) { root.getElementById("menu").hidden = true; download(x); } };
    root.getElementById("hs").onclick = () => shardIt("hs");
    root.getElementById("th").onclick = () => { const i = THEMES.indexOf(S.theme || "auto"); S.theme = THEMES[(i + 1) % THEMES.length];
      chrome.storage.sync.set({ theme: S.theme }); applyTheme(); toast("Theme: " + THEME_NAMES[S.theme]); };
    chrome.storage.sync.get(["theme", "keepAwake"]).then(v => { S.theme = v.theme || "auto"; S.keepAwake = v.keepAwake !== false; applyTheme(); });
    chrome.storage.onChanged.addListener((ch, area) => { if (area !== "sync") return; if (ch.keepAwake) S.keepAwake = ch.keepAwake.newValue !== false; if (ch.theme) { S.theme = ch.theme.newValue || "auto"; applyTheme(); } });
    new MutationObserver(applyTheme).observe(document.documentElement, { attributes: true, attributeFilter: ["dark"] });
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);   // the system changed while the page is open
    if (!mount.watching) {   // the window or zoom changed: YouTube may have switched between one and two columns
      mount.watching = true; let t; const again = () => { clearTimeout(t); t = setTimeout(place, 150); };
      addEventListener("resize", again); const flexy = document.querySelector("ytd-watch-flexy"); if (flexy) new MutationObserver(again).observe(flexy, { attributes: true });
    }
    root.getElementById("key").onclick = () => chrome.runtime.sendMessage({ type: "openOptions" });
    root.addEventListener("click", e => { const a = e.target.closest("[data-seek]"); if (a) { e.preventDefault(); e.stopPropagation(); seek(+a.dataset.seek); } });
    chrome.runtime.sendMessage({ type: "models" }, r => { if (r?.ok) { S.models = r.models; S.model = r.current; S.labels = r.labels || {}; S.bridge = r.nougenopen; S.ollamaErr = r.ollamaErr; } root.getElementById("mdl").textContent = label(S.model || ""); render(); });
    return true;
  }
  const $ = id => root.getElementById(id);
  // Mono Violet colorways. Auto follows YouTube's own light or dark setting.
  const THEMES = ["auto", "dark", "light", "arcade", "hardcade", "youtube"];
  const THEME_NAMES = { auto: "Auto (matches YouTube)", dark: "Mono Violet dark", light: "Mono Violet light", arcade: "Arcade", hardcade: "Hardcade", youtube: "YouTube red & gold" };
  function applyTheme() { const p = root && root.querySelector(".p"); if (!p) return; const t = S.theme || "auto";
    p.dataset.theme = t === "auto" ? NGT_THEME.resolveAuto({ ytBackground: getComputedStyle(document.documentElement).getPropertyValue("--yt-spec-base-background"), ytDarkAttr: document.documentElement.hasAttribute("dark"), osDark: matchMedia("(prefers-color-scheme: dark)").matches }) : t;
    const b = root.getElementById("th"); if (b) b.title = "Theme: " + THEME_NAMES[t] + " (click to change)"; }
  function toast(text) { const n = root.getElementById("note"); if (!n) return; n.textContent = text; n.hidden = false; n.className = "note";
    clearTimeout(toast.t); toast.t = setTimeout(() => note(), 1600); }

  // timestamps like [12:34] in model output -> clickable seek links
  function md(t) {
    let h = esc(t).replace(/\[?\b(\d{1,2}:\d{2}(?::\d{2})?)\b(?:,\s*)?\]?/g, (m, ts) => `<a class="t" href="#" role="button" data-seek="${parseTs(ts)}">${ts}</a>${/,/.test(m) ? " " : ""}`)
      .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/^#{1,4} (.+)$/gm, "<h3>$1</h3>");
    // Tables. Some models put a whole table on one line ("| a | b | |---|---| | x | y |"): split it into rows first.
    h = h.replace(/^\|.*\|\s*:?-{3,}.*$/gm, l => l.replace(/\|\s+\|/g, "|\n|"));
    h = h.replace(/(?:^\|.+\|[ \t]*(?:\n|$))+/gm, blk => {
      const rows = blk.trim().split("\n").map(r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim()));
      const body = rows.filter(r => !r.every(c => /^:?-{3,}:?$/.test(c)));
      if (body.length < 2) return blk;
      return "<table>" + body.map((r, i) => "<tr>" + r.map(c => i ? `<td>${c}</td>` : `<th>${c}</th>`).join("") + "</tr>").join("") + "</table>\n";
    });
    h = h.replace(/(?:^[-*] .+(?:\n|$))+/gm, b => "<ul>" + b.trim().split("\n").map(l => "<li>" + l.slice(2) + "</li>").join("") + "</ul>");
    // Numbered lists ("1. text"), keeping the number the list starts at.
    h = h.replace(/(?:^\d{1,2}[.)] .+(?:\n|$))+/gm, b => "<ol start=\"" + parseInt(b, 10) + "\">" + b.trim().split("\n").map(l => "<li>" + l.replace(/^\d{1,2}[.)] /, "") + "</li>").join("") + "</ol>");
    return h.replace(/\n{2,}/g, "<br><br>");
  }

  // mind map: indented bullet outline -> collapsible tree
  function tree(t) {
    const rows = t.split("\n").filter(l => /^\s*[-*] /.test(l)).map(l => ({ d: (l.match(/^\s*/)[0].length / 2) | 0, x: l.replace(/^\s*[-*] /, "") }));
    if (rows.length < 3) return null; let h = "", st = [];
    rows.forEach((r, i) => { const kids = rows[i + 1] && rows[i + 1].d > r.d;
      while (st.length && st[st.length - 1] >= r.d) { h += "</details>"; st.pop(); }
      if (kids) { h += `<details open class="mm" style="--d:${r.d}"><summary>${md(r.x)}</summary>`; st.push(r.d); } else h += `<div class="mm leaf" style="--d:${r.d}">${md(r.x)}</div>`; });
    return h + "</details>".repeat(st.length);
  }
  function show(t) { const m = S.sty === "mindmap" && tree(t); const foot = (t.match(/\n\n— .+$/) || [""])[0];
    return m ? `<div class="md mmw">${m}<div class="mu">${esc(foot)}</div></div>` : `<div class="md">${md(t)}</div>`; }
  function prefs() { chrome.storage.sync.set({ sty: S.sty, len: S.len, lng: S.lng, custom: S.custom }); }

  // Honest progress: a real stage name plus elapsed seconds, never a made-up percentage.
  function loader(stage, sub = "", t0 = Date.now()) {
    return `<div class="ld"><div class="lst"><span class="spin"></span><b>${esc(stage)}</b><span class="el" data-t0="${t0}">0s</span></div>
      <div class="bar"></div>${sub ? `<div class="mu" style="padding:0">${esc(sub)}</div>` : ""}</div>`;
  }
  const DOTS = '<span class="dots" aria-label="Thinking"><span></span><span></span><span></span></span>';
  const WRITING = '<div class="tail lst"><span class="spin"></span>Writing…</div>';
  setInterval(() => { if (root && !alive() && !S.dead) { S.dead = true; render(); } }, 2000);
  setInterval(() => { if (!root) return; root.querySelectorAll(".el[data-t0]").forEach(e => {
    const s = Math.max(0, Math.round((Date.now() - +e.dataset.t0) / 1000)); e.textContent = s < 60 ? s + "s" : (s / 60 | 0) + "m " + (s % 60) + "s"; }); }, 500);
  function transcriptLoading() {
    const skel = [92, 78, 85, 64, 88, 70].map(w => `<div><span class="skel ts"></span><div class="skel" style="width:calc(${w}% - 80px);margin-left:66px;margin-top:-11px"></div></div>`).join("");
    const stage = document.hidden ? "Waiting for this tab to be visible" : (S.tStage || "Loading transcript");
    const sub = document.hidden ? "YouTube only builds the transcript while the tab is on screen." : "";
    return loader(stage, sub, S.tT0) + skel;
  }
  function setStage(stage) {
    if (S.tStage === stage) return; S.tStage = stage;
    if (root && !S.lines.length && !S.err && S.tab === "transcript") { const bd = $("bd"); if (bd) bd.innerHTML = transcriptLoading(); }
  }

  function render() {
    if (!root) return;
    root.querySelectorAll(".tabs button").forEach(b => b.classList.toggle("on", b.dataset.t === S.tab));
    const tb = $("tb"), bd = $("bd"), ft = $("ft"); ft.innerHTML = ""; tb.innerHTML = ""; tb.hidden = false;
    // The extension was updated or reloaded while this tab stayed open: this copy can no longer
    // reach its background page, so say so instead of failing in confusing ways.
    if (!alive()) { bd.innerHTML = `<div class="mu">NouGenTube was updated. Refresh this tab to keep using it.</div><div class="mu"><button class="go" id="rf">Refresh tab</button></div>`; $("rf").onclick = () => location.reload(); return; }
    if (S.tab === "batch") return renderBatch();
    if (S.err) { bd.innerHTML = `<div class="mu err">${esc(S.err)}</div><div class="mu"><button class="go" id="rt">Try again</button></div>`; $("rt").onclick = () => { S.vid = null; S.fresh = true; load(); }; return; }
    if (!S.lines.length) { bd.innerHTML = transcriptLoading(); return; }
    if (S.tab === "transcript") {
      tb.innerHTML = `<input id="q" placeholder="Search transcript…" value="${esc(S.q || "")}"><button type="button" class="chip ${S.follow ? "on" : ""}" id="fl" title="Auto-scroll with the video">Follow</button><select id="trl" title="Show the transcript in another language, translated by your model">${"<option value=\"\">" + (S.tr ? "Original language" : "Translate…") + "</option>"}${LANGS.filter(l => l !== "Auto").map(l => `<option ${S.tr && S.tr.lang === l ? "selected" : ""}>${l}</option>`).join("")}</select>${S.lang === "audio" ? `<span class="chip" title="This transcript was made by speech-to-text on this computer, so names and numbers may be wrong">from audio</span>` : ""}${S.lang === "saved" ? `<button type="button" class="chip" id="rl" title="This transcript was saved from an earlier visit. Click to fetch it from YouTube again.">saved ↻</button>` : `<span class="mu" style="padding:0">${S.lang || ""}</span>`}`;
      if ($("rl")) $("rl").onclick = () => { S.vid = null; S.fresh = true; load(); };
      $("q").oninput = e => { S.q = e.target.value; drawLines(); }; $("fl").onclick = () => { S.follow = !S.follow; render(); }; tb.style.flexWrap = "wrap"; $("trl").onchange = e => (e.target.value ? withAwake(() => translateTranscript(e.target.value)) : translateTranscript(""));
      drawLines();
    } else if (S.tab === "summary") {
      tb.style.flexWrap = "wrap";
      tb.innerHTML = modelPicker() + `<select id="sty">${Object.entries(STYN).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
        <select id="len" title="Length"><option value="short">Short</option><option value="medium">Medium</option><option value="long">Long</option></select>
        <select id="lng" title="Output language">${LANGS.map(l => `<option>${l}</option>`).join("")}</select>
        <button class="go" id="gen">${S.summary ? "Regenerate" : "Summarize"}</button>
        ${(S.sty || "intel") === "custom" ? `<input id="cp2" style="flex-basis:100%" placeholder="Your own prompt, e.g. Write a LinkedIn post from this video" value="${esc(S.custom || "")}">` : ""}`;
      wirePicker(); $("sty").value = S.sty || "intel"; $("len").value = S.len || "medium"; $("lng").value = S.lng || "Auto";
      $("sty").onchange = e => { S.sty = e.target.value; prefs(); render(); }; $("len").onchange = e => { S.len = e.target.value; prefs(); }; $("lng").onchange = e => { S.lng = e.target.value; prefs(); };
      if ($("cp2")) $("cp2").oninput = e => { S.custom = e.target.value; prefs(); };
      $("gen").onclick = summarize;
      const canShard = (S.models || []).includes("nougenopen:auto");
      const failed = S.summary.trim().startsWith("⚠");
      bd.innerHTML = failed ? `<div class="mu err">${esc(S.summary.trim())}</div><div class="mu">Nothing was written. Pick another model above or press Regenerate.</div>` : S.summary
        ? `<div class="acts"><button type="button" class="chip on" id="cAll" title="Report, then the full transcript, ready to paste anywhere">Copy report + transcript</button><button type="button" class="chip" id="cRep">Copy report</button>${canShard ? `<button type="button" class="chip" id="shd" title="Save the report and the full transcript to NouGenShards">Shard it</button>` : ""}</div>` + show(S.summary) + checkCard(S.summary)
        : `<div class="mu">Summaries run on your own models. Timestamps in the result jump the video. The Intelligence report ends with the full transcript when you copy or shard it.</div><div class="acts"><button type="button" class="chip" id="cAI" title="Copies the Media Intelligence Architect instructions plus this transcript, to paste into Gemini, ChatGPT or Claude">Copy prompt + transcript for another AI</button></div>`;
      const flash = (id, text) => navigator.clipboard.writeText(text).then(() => { const e = $(id), o = e.textContent; e.textContent = "Copied ✓"; setTimeout(() => { if (e.isConnected) e.textContent = o; }, 1300); });
      if ($("cAll")) $("cAll").onclick = () => flash("cAll", reportDoc());
      if ($("cRep")) $("cRep").onclick = () => flash("cRep", S.summary);
      if ($("cAI")) $("cAI").onclick = () => flash("cAI", ARCHITECT + "\n\n---\n\n" + copyText());
      if ($("shd")) $("shd").onclick = shardIt;
    } else if (S.tab === "morph") {
      renderMorph();
    } else if (S.tab === "chat") {
      tb.innerHTML = modelPicker() + `<button type="button" class="chip ${S.scope !== "lib" ? "on" : ""}" id="sv" title="Ask about the video you are watching">This video</button><button type="button" class="chip ${S.scope === "lib" ? "on" : ""}" id="sl" title="Ask across every video you have saved to your vault">My library</button><button type="button" class="chip" data-p="What are the main takeaways?">Takeaways</button><button type="button" class="chip" data-p="List every tool, product or resource mentioned, with timestamps.">Resources</button><button type="button" class="chip" data-p="What claims here might be wrong or need checking?">Fact-check</button>`;
      wirePicker(); tb.querySelectorAll("[data-p]").forEach(c => { c.onclick = () => ask(c.dataset.p); if (S.scope === "lib") c.style.display = "none"; });
      $("sv").onclick = () => { S.scope = "video"; render(); }; $("sl").onclick = () => { S.scope = "lib"; render(); };
      bd.innerHTML = S.chat.filter(m => (m.scope || "video") === (S.scope || "video")).map(m => `<div class="msg ${m.role === "user" ? "u" : ""}">${m.role === "user" ? esc(m.content) : (m.content ? md(m.content) + srcLine(m) : DOTS)}</div>`).join("") || (S.scope === "lib" ? `<div class="mu">Ask across every video you have saved to your NouGenShards vault. Answers cite the saved report they came from.</div>` : `<div class="mu">Ask anything about this video. Answers cite timestamps.</div>`);
      ft.innerHTML = `<div class="ft"><input id="ci" placeholder="${S.scope === "lib" ? "Ask across every video in your library…" : "Ask about this video…"}"><button class="go" id="cs">Send</button></div>`;
      const go = () => { const v = $("ci").value.trim(); if (v) (S.scope === "lib" ? askLibrary(v) : ask(v)); }; $("cs").onclick = go; $("ci").onkeydown = e => e.key === "Enter" && go();
      bd.scrollTop = bd.scrollHeight;
    } else {
      const ks = Object.keys(S.hl).map(Number).sort((a, b) => a - b);
      tb.innerHTML = `<span class="mu" style="padding:0;flex:1">${ks.length} highlight${ks.length === 1 ? "" : "s"} · click ☆ on a transcript line</span><button class="ib" id="hc">Copy</button>`;
      $("hc").onclick = () => navigator.clipboard.writeText(ks.map(k => `[${fmt(k)}] ${S.hl[k]}`).join("\n"));
      bd.innerHTML = ks.map(k => `<div class="ln hl" data-seek="${k}"><span class="ts">${fmt(k)}</span><span style="flex:1">${esc(S.hl[k])}</span><button class="ib" data-del="${k}">✕</button></div>`).join("") || `<div class="mu">No highlights yet.</div>`;
      bd.querySelectorAll("[data-del]").forEach(b => b.onclick = e => { e.stopPropagation(); delete S.hl[b.dataset.del]; saveHl(); render(); });
    }
  }
  function label(m) { return (S.labels && S.labels[m]) || (m === "nougenopen:auto" ? "NouGenOpen · free fleet" : m); }
  const kindOf = m => m === "auto" ? "auto" : m.startsWith("nougenopen:") ? "bridge" : m.startsWith("prov:") ? "key" : "local";
  function modelPicker() { return S.models ? `<select id="mp" title="Model route">${S.models.map(m => `<option value="${esc(m)}" ${m === S.model ? "selected" : ""}>${esc(label(m))}${kindOf(m) === "bridge" ? " ($0, parallel)" : kindOf(m) === "local" ? " (local)" : ""}</option>`).join("")}</select>` : ""; }
  function wirePicker() { const p = $("mp"); if (p) p.onchange = e => { S.model = e.target.value;
    chrome.storage.sync.set(kindOf(S.model) === "local" ? { model: S.model, localModel: S.model } : { model: S.model }); $("mdl").textContent = label(S.model); }; }

  function drawLines() {
    const bd = $("bd"), q = (S.q || "").toLowerCase();
    const rows = S.paras.map((l, i) => ({ l, i })).filter(({ l, i }) => !q || l.text.toLowerCase().includes(q) || trOf(l, i).toLowerCase().includes(q));
    bd.innerHTML = trNote() + rows.map(({ l, i }) => {
      let t = esc(trOf(l, i)); if (q) t = t.replace(new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), m => `<mark>${m}</mark>`);
      return `<div class="ln ${S.hl[l.t] ? "hl" : ""}" data-i="${i}" data-seek="${l.t}"><span class="ts">${fmt(l.t)}</span><span style="flex:1">${t}</span><button class="ib st" data-star="${i}" title="Highlight">${S.hl[l.t] ? "★" : "☆"}</button></div>`;
    }).join("") || `<div class="mu">No matches.</div>`;
    bd.querySelectorAll("[data-star]").forEach(b => b.onclick = e => { e.stopPropagation(); const p = S.paras[b.dataset.star];
      if (S.hl[p.t]) delete S.hl[p.t]; else S.hl[p.t] = p.text; saveHl(); drawLines(); });
    S.cur = -1; tick();
  }
  function tick() {
    if (!root || S.tab !== "transcript" || !S.paras) return; const v = video(); if (!v) return;
    let i = 0; while (i + 1 < S.paras.length && S.paras[i + 1].t <= v.currentTime + 0.3) i++;
    if (i === S.cur) return; S.cur = i;
    root.querySelectorAll(".ln.now").forEach(e => e.classList.remove("now"));
    const el = root.querySelector(`.ln[data-i="${i}"]`); if (el) { el.classList.add("now"); if (S.follow && !S.q) el.scrollIntoView({ block: "center", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); }
  }
  setInterval(tick, 500);

  // ---------- AI ----------
  const tx = (max = 48000) => { let s = S.paras.map(l => `[${fmt(l.t)}] ${l.text}`).join("\n"); return s.length > max ? s.slice(0, max) + "\n[…truncated]" : s; };
  const SYS = () => `You are NouGenTube, analysing the YouTube video "${vtitle()}". Ground every statement in the transcript: state only what the speaker actually says, never outside knowledge; if a point has no basis in the transcript, drop it (shorter is better than invented). Cite moments as [m:ss] or [h:mm:ss] timestamps copied from the transcript. Be concise. Markdown only.\n\nTRANSCRIPT:\n${tx()}`;
  const STYN = { intel: "Intelligence report", brief: "Key points", deep: "Deep dive", chapters: "Chapters", mindmap: "Mind map", steps: "Step-by-step", tldr: "TL;DR", quiz: "Quiz", custom: "Custom prompt…" };
  const LANGS = ["Auto", "English", "Español", "Français", "Kreyòl ayisyen", "Português", "Deutsch", "Italiano", "日本語", "한국어", "中文", "العربية", "हिन्दी"];
  const LEN = { short: "Keep it tight: about 120 words.", medium: "About 300 words.", long: "Thorough: up to 800 words." };
  // Media Intelligence Architect report. The model writes the five analysis sections only; the
  // extension appends the full transcript archive itself, so the archive is always complete
  // and verbatim and costs no tokens.
  const INTEL = "Write an intelligence report with exactly these five sections, in this order, using these exact headings. No intro or outro.\n" +
    "### Executive Summary\n2-3 dense sentences: the video's main value and core thesis.\n" +
    "### Key Insights & Technical Milestones\nBullets, each with its [m:ss] timestamp. Cover what matters, how it works (mechanics, step-by-step logic), why it matters, and specifics: processes, tools, examples, numbers, claims, frameworks. Bold key terms. Use a table when several options or tools are compared.\n" +
    "### Strategic Action Items\nConcrete next steps a professional could take immediately, based only on the transcript.\n" +
    "### Quality Control / Fact-Check\nFlag unsupported or weak claims, missing proof, logical gaps, contradictions, missing context, and anything needing outside verification. Never call something verified when the transcript alone does not prove it.\n" +
    "### Notable Quotes\n2-3 short quotes copied word for word from the transcript, in double quotes, each with its [m:ss].\n" +
    "Do not reproduce the transcript; the full transcript archive is attached after your report automatically.";
  const STY = { intel: INTEL, chapters: "Split the whole video into 5-12 chapters in order. For each: a line \"[m:ss] **Chapter title**\" then one sentence on what it covers.",
    mindmap: "Produce a mind map as a nested markdown bullet outline (2-space indents, max 4 levels). Root = the video topic. Branches = main themes in order, leaves = concrete details with [m:ss]. Output ONLY the outline.",
    quiz: "Write 5 multiple-choice questions testing the key ideas. Each: question, options A-D, then \"Answer: X — [m:ss]\".",
    custom: "", brief: "Give a one-line gist, then 5-8 key points as bullets, each with its timestamp.", deep: "Give a sectioned deep-dive: ### headings per topic in order, bullets under each with timestamps, then 'Recommended to watch' (the 3 most valuable moments as [m:ss] links with why), 'Notable quotes' and 'Action items'.", steps: "Extract the procedure as numbered steps with timestamps, plus prerequisites and gotchas.", tldr: "Three sentences max, plus the single most important timestamp." };
  // bound: a job that writes into the open video's state (summary, chat). Navigating away cancels
  // it and drops its late output; unbound jobs (batch, morph) keep running and always settle.
  function stream(messages, onDelta, onDone, bound) {
    // Generation token as well as the id: A -> B -> A gives the same id back, but a new generation, so a stream
    // started on the first visit can never write into the second one (or save() it under v:<id>).
    const v0 = S.vid, g0 = S.gen, od = onDelta, oe = onDone, mine = () => S.vid === v0 && S.gen === g0;
    const onStage = S.onStage, onReset = S.onReset;
    if (bound) { onDelta = d => { if (mine()) od(d); }; onDone = (e, m) => { if (mine()) oe(e, m); }; }
    // Only bound (per-video summary/chat) streams share S.port; unbound jobs
    // (morph, batch) keep isolated ports so concurrent streams never cancel each other.
    if (bound && S.port) { S.port.cancel?.(); try { S.port.disconnect(); } catch {} }
    let fin = false, port = null, ka = null, retried = false;
    const end = (e, m) => { if (fin) return; fin = true; clearInterval(ka); if (bound && S.port === port) S.port = null; onDone(e, m); };
    // If Chrome stops the background worker mid-answer (a slow local model can run for minutes), reconnect once
    // and ask again from the start, dropping the partial text, before telling the user anything.
    const open = () => {
      const p = port = chrome.runtime.connect({ name: "chat" });
      p.bound = !!bound;
      if (bound) S.port = p;
      // Chrome stops an idle background page after ~30s even mid-request; a message every 15s keeps it up.
      clearInterval(ka); ka = setInterval(() => { try { p.postMessage({ ping: 1 }); } catch {} }, 15000);
      p.cancel = () => end("\n\n⚠ Cancelled: another request took over.");   // our own disconnect fires no onDisconnect here
      p.onMessage.addListener(m => { if (port !== p) return; if (m.stage && onStage) onStage(m.stage); if (m.reset && onReset) onReset(); if (m.delta) onDelta(m.delta); if (m.error) end("\n\n⚠ " + m.error); if (m.done) end("", m); });
      p.onDisconnect.addListener(() => {
        if (fin || port !== p) return;
        if (!retried && (!bound || mine())) { retried = true; if (onStage) onStage("The background page restarted; asking again"); if (onReset) onReset(); return open(); }
        end("\n\n⚠ The extension's background page stopped twice before the answer arrived. Press Regenerate, or pick a faster model.");
      });
      p.postMessage({ messages });
    };
    open();
  }
  // Split on topic boundaries: a >=3s silence gap or a transition phrase, near a target size.
  const TRANS = /\b(moving on|let'?s talk about|next up|now let'?s|the next (thing|step|part)|another thing|so that'?s it|in conclusion|to sum up|first of all|secondly|finally)\b/i;
  function chunks(lines, target = 9000, hard = 12000) {
    const out = []; let cur = [], len = 0;
    lines.forEach((l, i) => {
      const prev = lines[i - 1], gap = prev ? l.t - prev.t : 0;
      const boundary = len > target * 0.6 && (gap >= 3 || TRANS.test(l.text));
      if (cur.length && (boundary || len > hard)) { out.push(cur); cur = []; len = 0; }
      cur.push(l); len += l.text.length + 8;
    });
    if (cur.length) out.push(cur);
    return out.map(c => ({ from: c[0].t, to: c[c.length - 1].t, text: c.map(l => `[${fmt(l.t)}] ${l.text}`).join("\n") }));
  }
  const fullLen = () => S.lines.reduce((a, l) => a + l.text.length + 8, 0);

  // Long video: map chunk notes in parallel across the free fleet, then reduce with the chosen style.
  async function mapNotes(bd) {
    const cs = chunks(S.lines);
    bd.innerHTML = loader(`Mapping ${cs.length} topic chunks in parallel`, "Long video: each part is summarized on a free-fleet lane, then combined.", S.sT0);
    const sys = `You take grounded notes on one part of the YouTube video "${vtitle()}". Only facts the speaker states. Keep every useful [m:ss] timestamp.`;
    const prompts = cs.map((c, i) => `Part ${i + 1}/${cs.length} (${fmt(c.from)}-${fmt(c.to)}). Write 4-8 terse bullet notes, each ending with its [m:ss]. Then add one line starting with QUOTE: holding one short passage copied word for word from this part, in double quotes, followed by its [m:ss].\n\n${c.text}`);
    const mapCall = ps => new Promise(res => { const p = chrome.runtime.connect({ name: "map" }); const ka = setInterval(() => { try { p.postMessage({ ping: 1 }); } catch {} }, 15000);
      p.onMessage.addListener(m => { clearInterval(ka); res(m); p.disconnect(); }); p.onDisconnect.addListener(() => { clearInterval(ka); res({ ok: false, error: "background stopped" }); }); p.postMessage({ prompts: ps, system: sys }); });
    const r = await mapCall(prompts);
    if (!r?.ok) throw new Error(r?.error || "map failed");
    const results = r.results.slice(), good = x => x && x.ok && (x.content || "").trim();
    // No part of the video may silently drop out. Failed chunks get a second try; any that
    // still fail are handed to the final step as their own transcript text.
    let bad = results.map((x, i) => good(x) ? -1 : i).filter(i => i >= 0);
    if (bad.length) {
      bd.innerHTML = loader(`Retrying ${bad.length} of ${cs.length} chunks`, "Some free-fleet lanes failed; trying them again.", S.sT0);
      const r2 = await mapCall(bad.map(i => prompts[i]));
      if (r2?.ok) bad.forEach((i, k) => { if (good(r2.results[k])) results[i] = r2.results[k]; });
      bad = results.map((x, i) => good(x) ? -1 : i).filter(i => i >= 0);
    }
    const okN = cs.length - bad.length;
    if (!okN) throw new Error("every chunk failed on the free fleet");
    S.mapInfo = `${okN}/${cs.length} chunks summarized via ${[...new Set(results.filter(good).map(x => x.provider))].join(", ")}` + (bad.length ? `, ${bad.length} passed through as transcript` : "");
    return results.map((x, i) => `### Part ${i + 1} (${fmt(cs[i].from)}-${fmt(cs[i].to)})\n${good(x) ? x.content : "(not summarized; transcript of this part follows)\n" + cs[i].text.slice(0, 5000)}`).join("\n\n");
  }

  // ---- Checker pass. A second look at the model's work, done by code so it cannot be talked
  // round: every quoted passage must appear in the transcript, every timestamp must be real.
  const norm = s => s.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  function check(text) {
    const hay = norm(S.lines.map(l => l.text).join(" ")), end = (S.lines[S.lines.length - 1]?.t || 0) + 30;
    const quotes = [...text.matchAll(/["“]([^"”\n]{15,400})["”]/g)].map(m => m[1].trim());
    const q = quotes.map(x => ({ x, ok: hay.includes(norm(x)) }));
    const ts = [...text.replace(/\n\n— .+$/, "").matchAll(/\b(\d{1,2}:\d{2}(?::\d{2})?)\b/g)].map(m => m[1]);
    return { q, ts: ts.length, bad: ts.filter(t => parseTs(t) > end) };
  }
  function checkCard(text) {
    const c = check(text), okQ = c.q.filter(x => x.ok).length, missed = c.q.filter(x => !x.ok);
    const row = (ok, t) => `<div class="vr"><span class="${ok ? "vok" : "vno"}">${ok ? "✓" : "!"}</span><span>${t}</span></div>`;
    return `<div class="vf"><div class="vh">Checked against the transcript</div>` +
      (c.q.length ? row(!missed.length, `${okQ} of ${c.q.length} quoted passages appear word for word`) : row(S.sty !== "intel", S.sty === "intel" ? "The report contains no quoted passages, although the format asks for 2-3" : "No quoted passages to check")) +
      missed.map(m => row(false, `Not in the transcript as written: “${esc(m.x.slice(0, 110))}${m.x.length > 110 ? "…" : ""}”`)).join("") +
      row(!c.bad.length && (c.ts > 0 || S.sty !== "intel"), c.bad.length ? `${c.bad.length} of ${c.ts} timestamps fall outside the video: ${esc(c.bad.join(", "))}` : (c.ts ? `${c.ts} timestamps cited, all inside the video` : "No timestamps cited, so nothing can be traced back to the video")) +
      `<div class="mu" style="padding:6px 0 0">This checks wording and times only. Whether the speaker's claims are true still needs outside sources.</div></div>`;
  }
  function checkText(text) {
    const c = check(text), missed = c.q.filter(x => !x.ok);
    return `### Automatic check against the transcript\n- Quoted passages found word for word: ${c.q.length - missed.length} of ${c.q.length}\n` +
      missed.map(m => `- NOT found as written: "${m.x}"\n`).join("") +
      `- Timestamps cited: ${c.ts}; outside the video: ${c.bad.length ? c.bad.join(", ") : "none"}\n`;
  }
  // Report first, full transcript archive second. The archive is built here from the
  // transcript itself, never by the model, so it is always complete and word for word.
  const reportDoc = () => `${vtitle()} - YouTube\nhttps://www.youtube.com/watch?v=${S.vid}\n\n${S.summary.trim()}\n\n${checkText(S.summary)}\n---\n\n### Full Transcript Archive\n\n` +
    S.paras.map(l => `(${pad(l.t)}) ${l.text}`).join("\n") + "\n";
  // For pasting into another assistant: the operator's Media Intelligence Architect instructions.
  const ARCHITECT = "You are the Media Intelligence Architect. Analyze the FULL transcript below and include the FULL transcript in your final output. Treat the transcript as the primary source of truth. Output zero intro or outro filler; start with the first heading.\n\n" +
    "Required output, in this exact order:\n\n### Executive Summary\n2-3 dense sentences on the video's main value and core thesis.\n\n" +
    "### Key Insights & Technical Milestones\nBullets with timestamps. What matters, how it works, why it matters, and specifics: processes, tools, examples, numbers, claims, frameworks. Use a table when comparing options.\n\n" +
    "### Strategic Action Items\nPractical, concrete next steps a professional could take immediately.\n\n" +
    "### Quality Control / Fact-Check\nFlag unsupported or weak claims, missing proof, logical gaps, contradictions, missing context, and claims needing outside verification. Do not pretend something is verified if the transcript alone does not prove it.\n\n" +
    "### Notable Quotes\n2-3 short verbatim quotes with timestamps.\n\n---\n\n### Full Transcript Archive\nThe complete transcript exactly as provided: keep timestamps, speaker names, order and wording; do not paraphrase, shorten or omit anything, including sponsor reads. " +
    "If it does not fit in one response, end with the exact line \"Transcript continues in next part.\" and resume from that point in the next response. If only part of a transcript was provided, title the section \"### Partial Transcript Archive\". If no transcript is provided, give a troubleshooting guide for obtaining one instead of a report.";
  function note() { const n = root.getElementById("note"); if (!n) return; n.textContent = S.shardMsg || ""; n.hidden = !S.shardMsg; n.className = "note" + (/^(Could not|Nothing)/.test(S.shardMsg || "") ? " bad" : ""); }
  async function shardIt(id) {
    const b = $(typeof id === "string" ? id : "shd"); if (!b || b.dataset.busy) return;
    if (!S.lines.length) { S.shardMsg = "Nothing to save yet: the transcript has not loaded."; return note(); }
    const v0 = S.vid;
    const label = b.textContent; b.dataset.busy = "1"; b.innerHTML = '<span class="spin"></span> Saving';
    const has = !!S.summary.trim();
    const doc = {
      title: `${vtitle()} — NouGenTube ${has ? (STYN[S.sty] || "summary") : "transcript"}`.slice(0, 190), content: has ? reportDoc() : copyText(),
      tags: ["nougentube", "tube-report:" + v0, has ? (S.sty || "summary") : "transcript"], source_uri: "https://www.youtube.com/watch?v=" + v0 };
    // Saving can take a while; use a kept-alive connection and retry once. A repeat is safe:
    // the vault recognises identical content and does not store it twice.
    const once = () => new Promise(res => { const p = chrome.runtime.connect({ name: "shard" }); const ka = setInterval(() => { try { p.postMessage({ ping: 1 }); } catch {} }, 15000);
      const fin = v => { clearInterval(ka); res(v); try { p.disconnect(); } catch {} };
      p.onMessage.addListener(fin); p.onDisconnect.addListener(() => fin(null)); p.postMessage({ doc }); });
    // The bridge or its node can blip for a few seconds (a restart, a sleeping service worker):
    // retry with short pauses before calling it down. Repeats are safe; the vault dedupes by content.
    let r = null;
    for (const wait of [0, 1500, 4000, 8000]) { if (wait) await new Promise(res => setTimeout(res, wait)); r = await once(); if (r) break; }
    if (b.isConnected) { delete b.dataset.busy; b.textContent = label; }
    if (S.vid !== v0) return;   // navigated away while saving: do not overwrite the new video's state
    S.shardMsg = r?.ok ? `Saved to NouGenShards: ${r.parts.length} shard${r.parts.length === 1 ? "" : "s"} (${r.parts.map(p => p.shard_id != null ? `${p.shard_id}@db${p.db_index}` : (p.captured ? "new" : "already stored")).join(", ")}).`
      : `Could not save to NouGenShards: ${r?.error || "the local bridge did not answer"}`;
    save(); render(); note();
  }

  // ---------- Morph: turn the video's ideas into something to build, using what the vault already holds ----------
  const TARGETS = { best: "Best fit", code: "Code architecture", app: "App", site: "Website", skill: "Skill or workflow", custom: "Something else…" };
  const tname = M => M.target === "custom" ? (M.custom || "Custom") : TARGETS[M.target];
  const isVid = h => (h.tags || []).some(t => TUBE_TAG.test(t));
  const TARGET_ASK = {
    best: "Choose the single most valuable thing to build from this video given what the vault already holds, and say in one line why that form fits best.",
    code: "Design a code architecture: modules, their responsibilities, the data that flows between them, and where existing vault work plugs in.",
    app: "Design an app: who it is for, its screens or commands, the core loop, the data it stores, and which vault pieces it reuses.",
    site: "Design a website: its pages, what each page must do, the content it needs, and which vault pieces supply it.",
    skill: "Design a reusable skill or workflow: its trigger, inputs, ordered steps, outputs, stopping condition, and which vault pieces it calls." };
  const NL = String.fromCharCode(10);
  const { V21_ASK, checkPlan, report: planReport, safeUrl, body: planBody } = NGT_MORPH;
  const TUBE_TAG = /^tube-(report|morph):/;
  const refOf = h => `${h.id}@db${h.db}`;
  // One whole answer from the current route (the Auto fallback applies here too).
  const ask1 = messages => new Promise((res, rej) => { let out = ""; S.onStage = null; S.onReset = () => { out = ""; };
    stream(messages, d => { out += d; }, (e, fin) => e ? rej(new Error(e.replace(/^[\s⚠]+/, ""))) : res({ text: out, fin })); });
  const portCall = (name, payload) => new Promise(res => { const p = chrome.runtime.connect({ name }); const ka = setInterval(() => { try { p.postMessage({ ping: 1 }); } catch {} }, 15000);
    const fin = v => { clearInterval(ka); res(v); try { p.disconnect(); } catch {} };
    p.onMessage.addListener(fin); p.onDisconnect.addListener(() => fin(null)); p.postMessage(payload); });
  const morphSource = () => { const ok = S.summary && !S.summary.trim().startsWith("⚠");
    return ok ? "REPORT ON THE VIDEO:\n" + S.summary.trim().slice(0, 9000) + "\n\nTRANSCRIPT (start):\n" + tx(9000) : "TRANSCRIPT:\n" + tx(20000); };

  async function morph() {
    const custom = ($("tgc")?.value || "").trim().slice(0, 160);
    if ($("tg").value === "custom" && !custom) return $("tgc")?.focus();
    const M = S.morph = { target: $("tg").value, custom, text: "", shards: [], prior: [], queries: [], t0: Date.now(), busy: true, err: "", vaultOff: "", web: [], webOff: "", webVia: "", v21: true };
    const release = holdAwake(); let step = 0;
    const v0 = S.vid, here = () => S.vid === v0 && S.morph === M;   // navigation replaces S; a stale run writes nowhere
    const bd = $("bd"), stage = (t, sub = "") => { progress(++step + "/4"); if (here() && S.tab === "morph") bd.innerHTML = loader(t, sub, M.t0); };
    renderMorph();
    try {
      // 1. What is this video really teaching? Reduce it to phrases the vault can be searched for.
      stage("Reading the video's intents", "Naming the ideas in it that could be built.");
      let phrases = [];
      try {
        const r = await ask1([{ role: "system", content: `You read a YouTube video and name what it teaches that could be BUILT. Video: "${vtitle()}".\n\n${morphSource()}` },
          { role: "user", content: "List 6 short search phrases, 3 to 7 words each, one per line, no numbering and no commentary. Each names one concrete technique, system, tool or pattern from this video that could be built into software or a workflow." }]);
        phrases = r.text.split("\n").map(l => l.replace(/^[\s\-*•\d.)]+/, "").replace(/["*`]/g, "").trim()).filter(l => l.length >= 6 && l.length <= 90).slice(0, 6);
      } catch (e) { console.warn("[NouGenTube] intent step failed, using the title", e); }
      if (phrases.length < 2) phrases = [vtitle(), ...phrases];
      M.queries = [...new Set([...phrases, vtitle()])].slice(0, 7);

      // 2. Cross-reference the vault. The video's own saved report is not prior knowledge about it.
      stage(`Cross-referencing your vault`, `Searching NouGenShards for ${M.queries.length} ideas from the video.`);
      // Over-fetch, then keep older vault knowledge and other saved videos as separate groups, so a run of
      // fresh video reports cannot crowd out the deeper material the plan should build on.
      const body = { queries: M.queries, limit: 5, fetch: 20, max: 60, exclude_tags: ["tube-report:" + S.vid] };
      // The live web is searched at the same time, so the plan can be checked against what is current, not only what was saved.
      const wbody = { queries: M.queries.slice(0, 3), limit: 5, read: 3, max: 6, max_chars: 1800, freshness: "last_year" };
      const webP = portCall("web", { body: wbody }).then(w => w?.ok ? w : portCall("web", { body: wbody }));
      let rc = await portCall("recall", { body });
      if (!rc?.ok) rc = await portCall("recall", { body });
      stage("Checking the latest on the web", "Searching for current sources on the same ideas.");
      const wr = await Promise.race([webP, new Promise(r => setTimeout(() => r({ ok: false, error: "the web search took longer than 100 seconds" }), 100000))]);
      if (wr?.ok) { M.web = wr.results.map((h, i) => ({ ref: "w" + (i + 1), url: h.url, title: h.title, snippet: h.snippet, text: h.text || "", matched: h.matched || [] })); M.webVia = (wr.providers || []).join(", "); }
      else M.webOff = wr?.error || "the NouGenOpen bridge did not answer";
      if (rc?.ok) {
        M.prior = rc.shards.filter(h => (h.tags || []).includes("tube-morph:" + S.vid));
        const rest = rc.shards.filter(h => !M.prior.includes(h)), seen = new Set();
        const vids = rest.filter(isVid).filter(h => { const k = (h.tags || []).find(t => TUBE_TAG.test(t)).replace(TUBE_TAG, ""); return seen.has(k) ? false : seen.add(k); }).slice(0, 4);
        M.shards = [...rest.filter(h => !isVid(h)).slice(0, 10).map(h => ({ ...h, kind: "know" })), ...vids.map(h => ({ ...h, kind: "video" }))];
      } else {
        // Failsafe: the vault is unreachable, so write the plan from the video alone and say so.
        M.vaultOff = rc?.error || "the NouGenOpen bridge did not answer";
      }
      const know = M.shards.filter(h => h.kind !== "video"), vids = M.shards.filter(h => h.kind === "video");

      // 3. Write the plan, citing only shards the vault really returned.
      stage("Writing the morph plan", M.vaultOff ? "The vault could not be read, so this plan uses the video alone." : `${know.length} vault shards and ${vids.length} other saved videos matched.`);
      const list = a => a.map(h => `[${refOf(h)}] ${h.title}\n${h.snippet}`).join("\n\n");
      const vault = M.vaultOff ? "(the vault could not be read for this run; cite no shards)" :
        `VAULT KNOWLEDGE (existing work, notes, code and docs):\n${list(know) || "(nothing related)"}\n\nOTHER SAVED VIDEOS (reports on different videos):\n${list(vids) || "(none related)"}`;
      const sys = `You are NouGenTube Morph. You reverse a video's intent: not "what was said" but "what this lets us build", and you build on what the user's vault of saved knowledge (shards) already holds.\n` +
        `Rules: cite a shard only by a reference that appears below, exactly as written, like [${M.shards[0] ? refOf(M.shards[0]) : "123@db4"}]. Never invent a shard. Prefer VAULT KNOWLEDGE as the thing to build on; use OTHER SAVED VIDEOS only as supporting ideas. Cite video moments as [m:ss]. If the vault has nothing relevant for a point, say so plainly. Markdown only, no intro or outro.\n\n` +
        (M.web.length ? `Cite a web source only by its tag below, like [w1]. Never invent a web source or a URL.\n\n` : `\n`) +
        `VIDEO: "${vtitle()}"\n${morphSource()}\n\n${vault}` +
        (M.web.length ? `\n\nLATEST ON THE WEB (fetched just now; newer than the video and the vault):\n` + M.web.map(w => `[${w.ref}] ${w.title} (${w.url})\n${(w.text || w.snippet).slice(0, 1800)}`).join("\n\n") : "");
      const ask = M.target === "custom" ? `Design this: ${M.custom}. Cover its parts, how they work together, what it stores or produces, and which vault pieces it reuses.` : TARGET_ASK[M.target];
      const task = `${ask}\n\nUse exactly these sections:\n### Intent of the video\nWhat it is really teaching, restated as 3-5 capabilities someone could build, each with its [m:ss].\n` +
        `### What the vault already has\nBullets. Each cites one shard reference and says how it connects to an intent above.\n` +
        (M.web.length ? `### Latest on the web\nBullets. What current sources add, confirm or contradict compared with the video, each citing its [w] tag. Say plainly if something in the video looks out of date.\n` : "") + `### Morph plan\nThe design for the target above: its parts, how data moves between them, and which cited shards are reused or extended.\n` +
        `### First build steps\n5-8 ordered, concrete steps, each small enough to finish in one sitting.\n### Gaps\nWhat the vault lacks for this build and what to capture or learn next.` + V21_ASK + (S.lng && S.lng !== "Auto" ? `\nWrite in ${S.lng}.` : "");
      S.onStage = t => { if (!M.text) stage(t); }; S.onReset = () => { M.text = ""; };
      await new Promise((res, rej) => stream([{ role: "system", content: sys }, { role: "user", content: task }],
        d => { M.text += d; if (here() && S.tab === "morph") bd.innerHTML = `<div class="md">${md(M.text)}</div>` + WRITING; },
        (e, fin) => { if (e) return rej(new Error(e.replace(/^[\s⚠]+/, "")));
          M.text += `\n\n— ${fin.model}, ${fin.tokens} tokens, ${Math.round((Date.now() - M.t0) / 1000)}s, ${fin.where}${fin.failed && fin.failed.length ? ` · after ${fin.failed.length} failed route${fin.failed.length === 1 ? "" : "s"}` : ""}`; res(); }));
    } catch (e) { M.err = String(e.message || e); }
    release(); M.busy = false; if (here()) { save(); renderMorph(); }
  }
  // Shards cited must be ones the vault returned, web tags ones the search found, all 21 steps present in order, timestamps inside the video.
  function morphCheck(M) {
    const k = checkPlan(M, refOf), c = check(planBody(M.text));
    return { ...k, ts: c.ts, badTs: c.bad, lines: planReport(M, k, { ts: c.ts, bad: c.bad }) };
  }
  function morphDoc(M) {
    const k = morphCheck(M);
    return `${vtitle()} - YouTube\nhttps://www.youtube.com/watch?v=${S.vid}\nMorph target: ${tname(M)}${M.v21 ? " (Valerion 21 steps)" : ""}\n\n${M.text.trim()}\n\n### Automatic check\n${k.lines.map(r => "- " + (r.ok ? "OK" : "WARNING") + ": " + r.text).join("\n")}\n\n` +
      `### Web sources fetched${M.webVia ? " (" + M.webVia + ")" : ""}${NL}${(M.web || []).map(w => `- [${w.ref}] ${w.title} ${w.url}`).join(NL) || "- none"}${NL}${NL}` +
      `### Vault shards cross-referenced\n${M.shards.map(h => `- [${refOf(h)}] ${h.title}${h.kind === "video" ? " [other saved video]" : ""} (matched: ${h.matched.join("; ")})`).join("\n") || "- none"}\n\n### Search phrases\n${M.queries.map(q => "- " + q).join("\n")}\n`;
  }
  function renderMorph() {
    if (S.tab !== "morph" || !root) return;
    const tb = $("tb"), bd = $("bd"), M = S.morph;
    tb.style.flexWrap = "wrap";
    tb.innerHTML = modelPicker() + `<select id="tg" title="What to morph it into">${Object.entries(TARGETS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select><input id="tgc" style="flex-basis:100%" placeholder="Morph into… e.g. a Discord bot, a course, a pricing page" value="${esc(M?.custom || S.tgc || "")}" hidden><button class="go" id="mgo">${M?.text ? "Morph again" : "Morph"}</button>`;
    wirePicker(); $("tg").value = M?.target || S.tgt || "best"; const tgc = $("tgc"), sync = () => { tgc.hidden = $("tg").value !== "custom"; }; sync(); $("tg").onchange = e => { S.tgt = e.target.value; sync(); if (!tgc.hidden) tgc.focus(); }; tgc.oninput = () => { S.tgc = tgc.value; }; tgc.onkeydown = e => { e.stopPropagation(); if (e.key === "Enter") morph(); };
    $("mgo").onclick = morph; if (M?.busy) { $("mgo").disabled = true; $("mgo").innerHTML = '<span class="spin"></span>Working'; return; }
    if (M?.err && !M.text) { bd.innerHTML = `<div class="mu err">${esc(M.err)}</div><div class="mu">Nothing was written. Press Morph to try again.</div>`; return; }
    if (!M?.text) { bd.innerHTML = `<div class="mu">Morph reverses the video's intent: it names what the video lets you build, looks up related shards in your vault, and writes a plan that builds on what you already have. Pick a target and press Morph.</div>${S.bridge ? "" : `<div class="mu">The NouGenOpen bridge is not running, so the vault cannot be read. Morph will still write a plan from the video alone. Start <b>nougen-open serve</b> to build on your shards.</div>`}`; return; }
    const k = morphCheck(M), row = (ok, t) => `<div class="vr"><span class="${ok ? "vok" : "vno"}">${ok ? "✓" : "!"}</span><span>${t}</span></div>`;
    const kn = M.shards.filter(h => h.kind !== "video"), vd = M.shards.filter(h => h.kind === "video");
    const W = M.web || [], wmap = Object.fromEntries(W.map(w => [w.ref, w]));
    const wlink = h => h.replace(/\[(w\d+)\]/g, (m, r) => {
      const w = wmap[r], u = w ? safeUrl(w.url) : "";
      return u ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer" title="${esc(w.title || "")}">[${esc(r)}]</a>` : m;
    });
    const wgrp = W.length ? `<div class="mu" style="padding:6px 0 2px">Latest on the web${M.webVia ? " (" + esc(M.webVia) + ")" : ""}</div>` + W.map(w => {
      const u = safeUrl(w.url);
      const lbl = esc(w.title || w.url || "");
      return `<div class="vr"><span class="vok">${esc(w.ref)}</span><span>${u ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">${lbl}</a>` : lbl}</span></div>`;
    }).join("") : "";
    const grp = (t, a) => a.length ? `<div class="mu" style="padding:6px 0 2px">${t}</div>` + a.map(h => `<div class="vr"><span class="vok">${esc(refOf(h))}</span><span>${esc(h.title)}</span></div>`).join("") : "";
    bd.innerHTML = `<div class="acts"><button type="button" class="chip on" id="mc">Copy morph plan</button><button type="button" class="chip" id="mb" title="Copy the plan as a prompt you can paste into a coding agent">Copy build prompt</button><button type="button" class="chip" id="ms" title="Save this plan to NouGenShards">Shard it</button></div>` +
      (M.prior.length ? `<div class="mu">This video was morphed before: ${M.prior.map(h => esc(refOf(h))).join(", ")}.</div>` : "") +
      `<details class="vf"><summary class="vh" style="cursor:pointer">${M.vaultOff ? "Vault not read for this plan" : `Cross-referenced ${kn.length} vault shard${kn.length === 1 ? "" : "s"} and ${vd.length} other saved video${vd.length === 1 ? "" : "s"}`}${W.length ? `, ${W.length} web source${W.length === 1 ? "" : "s"}` : ""}</summary>${M.vaultOff ? `<div class="mu" style="padding:4px 0">${esc(M.vaultOff)}. Start the bridge and press Morph again to build on your shards.</div>` + wgrp : (grp("Vault knowledge", kn) + grp("Other saved videos", vd) + wgrp || `<div class="mu" style="padding:4px 0">The vault returned nothing related to this video.</div>`)}</details>` +
      `<div class="md">${wlink(md(M.text))}</div><div class="vf"><div class="vh">Checked against your vault, the web and the transcript</div>` +
      k.lines.map(r => row(r.ok, esc(r.text))).join("") + `</div>`;
    $("mc").onclick = () => navigator.clipboard.writeText(morphDoc(M)).then(() => { const e = $("mc"); e.textContent = "Copied ✓"; setTimeout(() => { if (e.isConnected) e.textContent = "Copy morph plan"; }, 1300); });
    $("mb").onclick = () => navigator.clipboard.writeText(["Build what this plan describes. Work through First build steps in order, one step at a time, and report after each. Recall each cited shard from NouGenShards by its reference before reusing it, and treat Gaps as open questions to resolve, not as work to invent.", "", morphDoc(M)].join(String.fromCharCode(10))).then(() => { const e = $("mb"); e.textContent = "Copied ✓"; setTimeout(() => { if (e.isConnected) e.textContent = "Copy build prompt"; }, 1300); });
    $("ms").onclick = async () => { const b = $("ms"); if (b.dataset.busy) return; const v0 = S.vid; b.dataset.busy = "1"; b.innerHTML = '<span class="spin"></span> Saving';
      const doc = { title: `${vtitle()} — NouGenTube morph (${tname(M)})`.slice(0, 190), content: morphDoc(M), tags: ["nougentube", "tube-morph:" + v0, "morph-" + M.target], source_uri: "https://www.youtube.com/watch?v=" + v0 };
      let r = await portCall("shard", { doc }); if (!r) r = await portCall("shard", { doc });
      if (b.isConnected) delete b.dataset.busy;
      if (S.vid !== v0 || S.morph !== M) return;   // navigated away or re-morphed while saving
      S.shardMsg = r?.ok ? `Morph plan saved to NouGenShards: ${r.parts.map(p => p.shard_id != null ? `${p.shard_id}@db${p.db_index}` : "stored").join(", ")}.` : `Could not save to NouGenShards: ${r?.error || "the local bridge did not answer"}`;
      save(); renderMorph(); note(); };
  }

  async function summarize() {
    const v0 = S.vid;
    S.summary = ""; S.shardMsg = ""; S.sty = $("sty").value; S.len = $("len").value; S.lng = $("lng").value;
    if (S.sty === "custom" && !(S.custom || "").trim()) return $("cp2")?.focus();
    const task = (S.sty === "custom" ? S.custom : STY[S.sty]) + " " + (S.sty === "mindmap" || S.sty === "chapters" || S.sty === "intel" ? "" : LEN[S.len]) + (S.lng !== "Auto" ? ` Write the answer in ${S.lng}.` : ""); render(); const bd = $("bd"), b = $("gen"); b.disabled = true; b.innerHTML = '<span class="spin"></span>Working'; S.sT0 = Date.now();
    const m = S.model || "";
    const k = kindOf(m);
    bd.innerHTML = k === "auto" ? loader("Finding the best available route", "Tries each route in order and moves on if one fails.", S.sT0)
      : k === "bridge" ? loader("Asking the NouGenOpen free fleet", "", S.sT0)
      : k === "key" ? loader("Asking " + label(m), "", S.sT0)
      : loader(`Running locally on ${m}`, "The first request after a while also loads the model into memory.", S.sT0);
    S.onStage = t => { if (!S.summary && S.tab === "summary") bd.innerHTML = loader(t, "", S.sT0); };
    S.onReset = () => { S.summary = ""; };
    let sys = SYS(); S.mapInfo = "";
    if ((S.model === "nougenopen:auto" || (S.model === "auto" && S.bridge)) && fullLen() > 14000) {
      try { const notes = await withAwake(() => mapNotes(bd));
        if (S.vid !== v0) return;   // navigated away while mapping: these notes belong to the old video
        bd.innerHTML = loader("Combining the notes into your summary", S.mapInfo, S.sT0);
        sys = `You are NouGenTube, writing about the YouTube video "${vtitle()}". Below are grounded, timestamped notes covering the whole video in order. Use only these notes; keep [m:ss] timestamps. When you quote, use only passages that appear inside double quotes on the QUOTE: lines, exactly as written. Markdown only.\n\nNOTES:\n${notes}`;
      } catch (e) { if (S.vid !== v0) return; if (S.model === "auto") { sys = SYS(); S.mapInfo = ""; bd.innerHTML = loader("Finding the best available route", "", S.sT0); } else { S.summary = "⚠ " + e.message; b.disabled = false; b.textContent = "Regenerate"; return render(); } } }
    stream([{ role: "system", content: sys }, { role: "user", content: task }], d => { S.summary += d; if (S.tab === "summary") bd.innerHTML = show(S.summary) + WRITING; },
      (e, fin) => { S.summary += e; if (fin) S.summary += `\n\n— ${fin.model}, ${fin.tokens} tokens, ${Math.round((Date.now() - S.sT0) / 1000)}s, ${fin.where}${S.mapInfo ? " · map: " + S.mapInfo : ""}${fin.failed && fin.failed.length ? ` · after ${fin.failed.length} failed route${fin.failed.length === 1 ? "" : "s"}` : ""}`; save(); render(); }, true);
  }
  function ask(q) {
    S.chat.push({ role: "user", content: q }, { role: "assistant", content: "" }); render(); const a = S.chat[S.chat.length - 1];
    S.onStage = null; S.onReset = () => { a.content = ""; };
    stream([{ role: "system", content: SYS() + (S.lng && S.lng !== "Auto" ? `\nAlways answer in ${S.lng}.` : "") }, ...S.chat.slice(0, -1).filter(m => m.scope !== "lib").slice(-10)], d => { a.content += d; const ms = S.tab === "chat" && S.scope !== "lib" ? $("bd")?.querySelectorAll(".msg") : null, el = ms?.[ms.length - 1]; if (el) { el.innerHTML = md(a.content); $("bd").scrollTop = 1e9; } },
      e => { a.content += e; save(); render(); }, true);
  }

  // ---------- Translate the transcript (Glasp: "in the language you choose"; NoteGPT: 60+ languages) ----------
  const trOf = (l, i) => (S.tr && S.tr.out[i]) || l.text;
  const trNote = () => !S.tr ? "" : '<div class="mu" style="padding:0 0 6px">' + (S.tr.err ? '<span class="err">' + esc(S.tr.err) + "</span> Pick another model in Summary and choose the language again."
    : S.tr.busy ? "Translating to " + esc(S.tr.lang) + "… " + S.tr.done + " of " + S.paras.length + " lines" : "Showing the transcript in " + esc(S.tr.lang) + ". Copy and the .txt, .md, .html, .csv and .json exports use this version.") + "</div>";
  const copyTextTr = () => vtitle() + " - YouTube\nhttps://www.youtube.com/watch?v=" + S.vid + "\n\nTranscript (" + S.tr.lang + "):\n" + S.paras.map((l, i) => "(" + pad(l.t) + ") " + trOf(l, i)).join("\n");
  async function translateTranscript(lang) {
    if (!lang) { S.tr = null; save(); render(); return; }
    const total = S.paras.length, size = 30, T = S.tr = { lang, out: [], done: 0, busy: true, err: "" };
    render();
    for (let i = 0; i < total && S.tr === T; i += size) {
      const batch = S.paras.slice(i, i + size);
      const prompt = "Translate each numbered line into " + lang + ". Keep the numbering and put one translated line per number, formatted as N|text. Return only those lines.\n" + batch.map((l, j) => (i + j + 1) + "|" + l.text).join("\n");
      let got = 0;
      for (let attempt = 0; attempt < 2 && got < batch.length * 0.6; attempt++) {
        try {
          const r = await ask1([{ role: "system", content: "You are a precise subtitle translator. Keep names, numbers and technical terms. No commentary and no extra lines." }, { role: "user", content: prompt }]);
          for (const m of r.text.matchAll(/^\s*(\d+)\s*\|\s*(.+)$/gm)) { const n = +m[1] - 1; if (n >= i && n < i + batch.length && m[2].trim()) { if (!T.out[n]) got++; T.out[n] = m[2].trim(); } }
        } catch (e) { T.err = String(e.message || e); break; }
      }
      if (S.tr !== T) return;
      if (T.err) break;
      T.done = Math.min(total, i + size);
      progress(Math.round(100 * T.done / total) + "%");
      if (S.tab === "transcript") drawLines();
    }
    if (S.tr !== T) return;
    T.busy = false;
    if (!T.err && !T.out.some(Boolean)) T.err = "The model returned no translated lines.";
    save(); render();
  }

  // ---------- Ask your library (Glasp: "chat with your highlights"): one question across every video saved to the vault ----------
  const srcLine = m => {
    if (!m.refs || !m.refs.length) return "";
    const cited = new Set(NGT_MORPH.citations(m.content).shards), known = new Set(m.refs.map(r => r.ref)), bad = [...cited].filter(c => !known.has(c));
    return '<div class="mu" style="font-size:12px;margin-top:6px">Library sources: ' + m.refs.map(r => (cited.has(r.ref) ? "✓ " : "") + esc(r.ref) + " " + esc(String(r.title).replace(/ — NouGenTube.*$/, "").slice(0, 60))).join(" · ") +
      (bad.length ? '<br><span class="err">Cited but not in the library results: ' + esc(bad.join(", ")) + "</span>" : "") + "</div>";
  };
  async function askLibrary(q) {
    const a = { role: "assistant", content: "", scope: "lib", refs: [] };
    S.chat.push({ role: "user", content: q, scope: "lib" }, a); render();
    const fail = msg => { a.content = "⚠ " + msg; save(); render(); };
    const body = { queries: [q], limit: 6, fetch: 20, max: 8, snippet_chars: 2500, include_tag_prefixes: ["tube-report:", "tube-morph:"] };
    let rc = await portCall("recall", { body });
    if (!rc?.ok) rc = await portCall("recall", { body });
    if (!rc?.ok) return fail("Your library is read through the NouGenOpen bridge, which did not answer (" + (rc?.error || "no reply") + "). Start nougen-open serve.");
    a.refs = rc.shards.map(h => ({ ref: refOf(h), title: h.title }));
    if (!a.refs.length) { a.content = "Your library has no saved video matching this question yet. Press Shard on a video's Summary tab to add it."; save(); render(); return; }
    const ctx = rc.shards.map(h => "[" + refOf(h) + "] " + h.title + "\n" + h.snippet).join("\n\n");
    S.onStage = null; S.onReset = () => { a.content = ""; };
    const sys = "You answer questions from the user's own library of saved YouTube video reports (shards). Use ONLY the LIBRARY below. Cite the shard behind every claim with its reference exactly as written, like [" + a.refs[0].ref + "]. " +
      "Name the video each point comes from. If the library does not contain the answer, say so plainly. Markdown, concise.\n\nLIBRARY:\n" + ctx + (S.lng && S.lng !== "Auto" ? "\nAlways answer in " + S.lng + "." : "");
    const hist = S.chat.filter(m => m.scope === "lib").slice(0, -1).slice(-6).map(m => ({ role: m.role, content: m.content }));
    stream([{ role: "system", content: sys }, ...hist], d => {
      a.content += d;
      if (S.tab === "chat" && S.scope === "lib") { const ms = $("bd").querySelectorAll(".msg"), el = ms[ms.length - 1]; if (el) el.innerHTML = md(a.content) + srcLine(a); }
    }, e => { if (e) return fail(e.replace(/^[\s⚠]+/, "")); save(); render(); }, true);
  }

  // ---------- Batch: many videos or a playlist, one summary each (NoteGPT: "batch summarize up to 20 videos") ----------
  // Keeps the computer awake (not the screen) while a long job runs; the returned function lets go. The hold lives in the
  // background page and ends the moment this port does. Pings keep that page alive; a dropped port is opened again.
  const sayers = new Set();   // every open hold's way of showing progress on the toolbar button
  const progress = text => sayers.forEach(say => say(text));
  function holdAwake() {
    if (S.keepAwake === false) return () => {};
    let port = null, done = false, ka = null, last = "";
    const say = text => { last = text; try { if (port) port.postMessage({ progress: text }); } catch {} };
    sayers.add(say);
    const open = () => {
      if (done) return;
      try { port = chrome.runtime.connect({ name: "awake" }); } catch { return; }
      port.postMessage({ start: "prevent-app-suspension" });
      if (last) port.postMessage({ progress: last });
      clearInterval(ka); ka = setInterval(() => { try { port.postMessage({ ping: 1 }); } catch {} }, 15000);
      port.onDisconnect.addListener(() => { clearInterval(ka); if (!done) setTimeout(open, 1000); });
    };
    open();
    return () => { done = true; sayers.delete(say); clearInterval(ka); try { if (port) port.disconnect(); } catch {} };
  }
  const withAwake = async fn => { const release = holdAwake(); try { return await fn(); } finally { release(); } };
  const tubeCall = (kind, body) => portCall("tube", { kind, body });
  const BATCH_MAX = 20, BATCH_STYLES = ["brief", "tldr", "deep", "intel", "chapters", "steps"];
  const { idOf, isVideoId, shardContent } = NGT_BATCH;
  const lineText = ls => ls.map(l => "[" + fmt(l.t) + "] " + l.text).join("\n");
  const sysFor = (title, body) => "You are NouGenTube, analysing the YouTube video \"" + title + "\". Ground every statement in the transcript: state only what the speaker actually says, never outside knowledge; if a point has no basis in the transcript, drop it (shorter is better than invented). Cite moments as [m:ss] or [h:mm:ss] timestamps copied from the transcript. Be concise. Markdown only.\n\nTRANSCRIPT:\n" + body;
  const stylePrompt = sty => STY[sty] + " " + (["intel", "mindmap", "chapters"].includes(sty) ? "" : LEN[S.len || "medium"]) + (S.lng && S.lng !== "Auto" ? " Write the answer in " + S.lng + "." : "");
  // Timestamps in a summary that fall after the video's last line (plus two minutes).
  const stampsOutside = (text, lastT) => [...String(text).matchAll(/\b(\d{1,2}:\d{2}(?::\d{2})?)\b/g)].filter(m => parseTs(m[1]) > lastT + 120).length;
  // One video's summary. Long transcripts are read in chunks first, then the notes are combined.
  async function summarizeLines(lines, title, sty, onStage) {
    const full = lineText(lines), user = { role: "user", content: stylePrompt(sty) };
    if (full.length <= 24000) { onStage("Summarizing"); const r = await ask1([{ role: "system", content: sysFor(title, full) }, user]); return { text: r.text.trim(), model: r.fin && r.fin.model }; }
    const cs = chunks(lines), notes = [];
    for (let i = 0; i < cs.length; i++) {
      onStage("Reading part " + (i + 1) + " of " + cs.length);
      const r = await ask1([{ role: "system", content: sysFor(title, cs[i].text) }, { role: "user", content: "Write concise bullet notes on every distinct point in this part, keeping exact names, numbers and the [m:ss] timestamps." }]);
      notes.push(r.text.trim());
    }
    onStage("Combining the notes");
    const r = await ask1([{ role: "system", content: sysFor(title, notes.join("\n\n")) }, user]);
    return { text: r.text.trim(), model: r.fin && r.fin.model };
  }
  const btSave = () => { try { chrome.storage.local.set({ batch: { items: S.bt.items, sty: S.bt.sty, shardAll: S.bt.shardAll } }); } catch {} };
  const btPaint = () => { if (S.tab === "batch") renderBatch(); };
  async function batchShard(it) {
    const lines = S.bt.mem[it.id], url = "https://www.youtube.com/watch?v=" + it.id;
    const { content, summaryOnly } = shardContent(it, url, lines ? paragraphs(lines).map(l => "(" + pad(l.t) + ") " + l.text).join("\n") : "");
    it.shardNote = summaryOnly ? "Saved the summary only: the transcript is not kept after a reload." : "";
    const doc = { title: (it.title + " — NouGenTube " + (STYN[S.bt.sty] || "summary")).slice(0, 190), content, tags: ["nougentube", "tube-report:" + it.id, S.bt.sty || "brief", "batch"], source_uri: url };
    let r = await portCall("shard", { doc }); if (!r) r = await portCall("shard", { doc });
    it.shard = r && r.ok ? r.parts.map(p => p.shard_id != null ? p.shard_id + "@db" + p.db_index : "stored").join(", ") : "";
    it.shardErr = r && r.ok ? "" : (r && r.error) || "no answer from the bridge";
    btSave(); btPaint();
  }
  async function batchOne(it) {
    const stage = t => { it.stage = t; btPaint(); };
    it.status = "transcript"; it.err = ""; stage("Getting the transcript (captions first, then audio on this computer)");
    const t = await tubeCall("transcript", { video_id: it.id, audio: "auto", max_minutes: 150 });
    if (!t || !t.ok) throw new Error((t && t.error) || "the NouGenOpen bridge did not answer");
    if (!t.lines?.length) throw new Error("no transcript lines came back");
    it.title = it.title || t.title || it.id; it.src = t.source === "whisper" ? "audio" : "captions"; S.bt.mem[it.id] = t.lines;
    it.status = "summary";
    const r = await summarizeLines(t.lines, it.title, S.bt.sty || "brief", stage);
    it.text = r.text; it.model = r.model || ""; it.outside = stampsOutside(r.text, t.lines[t.lines.length - 1].t);
    it.status = "done"; it.stage = ""; btSave(); btPaint();
    if (S.bt.shardAll) await batchShard(it);
  }
  async function runBatch() {
    const B = S.bt; if (B.running) return;
    B.running = true; B.stop = false; btPaint();
    const release = holdAwake();
    const tally = () => progress(B.items.filter(i => i.status === "done").length + "/" + B.items.length);
    try {
    tally();
    for (const it of B.items) {
      if (B.stop) break;
      if (it.status !== "queued" && it.status !== "error") continue;
      try { await batchOne(it); tally(); } catch (e) { it.status = "error"; it.err = String(e.message || e).replace(/^[\s⚠]+/, ""); it.stage = ""; btSave(); btPaint(); }
    }
    } finally { release(); B.running = false; btSave(); btPaint(); }
  }
  async function batchAdd(text) {
    const B = S.bt, notes = [], have = new Set(B.items.map(i => i.id));
    let capped = false;
    const add = (id, title) => { if (!isVideoId(id) || have.has(id)) return false; if (B.items.length >= BATCH_MAX) { capped = true; return false; } have.add(id); B.items.push({ id, title: title || "", status: "queued" }); return true; };
    for (const raw of String(text).split(/[\n,\s]+/).map(s => s.trim()).filter(Boolean)) {
      if (/[?&]list=/.test(raw) && !/[?&]v=/.test(raw)) {
        const p = await tubeCall("playlist", { url: raw });
        if (p && p.ok) { let n = 0; for (const v of p.videos) if (add(v.id, v.title)) n++; notes.push("Added " + n + " of " + p.videos.length + " from the playlist" + (p.title ? " " + p.title : "") + "."); }
        else notes.push("Could not read the playlist: " + ((p && p.error) || "no answer from the bridge"));
      } else if (!add(idOf(raw))) { if (!idOf(raw)) notes.push("Skipped \"" + raw.slice(0, 40) + "\": not a YouTube link."); }
    }
    if (capped) notes.push("Only " + BATCH_MAX + " videos fit in one batch.");
    B.notes = notes.join(" "); btSave(); btPaint();
  }
  async function batchPlaylistHere() {
    if (!/[?&]list=/.test(location.href)) { S.bt.notes = "This video was not opened from a playlist. Paste a playlist link above instead."; return btPaint(); }
    S.bt.notes = "Reading the playlist…"; btPaint();
    await batchAdd("https://www.youtube.com/playlist?list=" + new URLSearchParams(location.search).get("list"));
  }
  const batchDoc = () => S.bt.items.filter(i => i.status === "done").map(i => "## " + i.title + "\nhttps://www.youtube.com/watch?v=" + i.id + "\n\n" + i.text).join("\n\n---\n\n") + "\n";
  function renderBatch() {
    const tb = $("tb"), bd = $("bd"), ft = $("ft"); ft.innerHTML = ""; tb.hidden = false; tb.style.flexWrap = "wrap";
    if (!S.bt) {
      S.bt = { items: [], mem: {}, sty: "brief", shardAll: true, loading: true };
      chrome.storage.local.get("batch").then(d => { const b = d.batch || {}; S.bt = { items: (b.items || []).filter(i => isVideoId(i.id)).map(i => (i.status === "transcript" || i.status === "summary") ? { ...i, status: "queued", stage: "" } : i), mem: {}, sty: b.sty || "brief", shardAll: b.shardAll !== false }; if (S.tab === "batch") renderBatch(); }).catch(() => { S.bt.loading = false; });
      bd.innerHTML = '<div class="mu">Loading…</div>'; tb.innerHTML = ""; return;
    }
    const B = S.bt, done = B.items.filter(i => i.status === "done").length, errs = B.items.filter(i => i.status === "error").length, queued = B.items.filter(i => i.status === "queued" || i.status === "error").length;
    tb.innerHTML = modelPicker() + '<select id="bs" title="What each summary looks like">' + BATCH_STYLES.map(k => '<option value="' + k + '">' + STYN[k] + "</option>").join("") + "</select>" +
      '<button type="button" class="chip ' + (B.shardAll ? "on" : "") + '" id="bsa" title="Save each finished summary and its transcript to your NouGenShards vault">Shard each</button>' +
      '<button class="go" id="bgo"' + (!S.bridge || (!queued && !B.running) ? " disabled" : "") + ">" + (B.running ? '<span class="spin"></span>Stop' : done && queued ? "Continue" : "Summarize all") + "</button>";
    wirePicker(); $("bs").value = B.sty || "brief"; $("bs").onchange = e => { B.sty = e.target.value; btSave(); };
    $("bsa").onclick = () => { B.shardAll = !B.shardAll; btSave(); btPaint(); };
    $("bgo").onclick = () => { if (B.running) { B.stop = true; $("bgo").disabled = true; } else runBatch(); };
    const pct = B.items.length ? Math.round(100 * done / B.items.length) : 0;
    const row = it => {
      const icon = it.status === "done" ? '<span class="vok">✓</span>' : it.status === "error" ? '<span class="vno">!</span>' : it.status === "queued" ? '<span class="mu">·</span>' : '<span class="spin"></span>';
      const head = '<span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(it.title || it.id) + "</span>";
      const meta = it.status === "done" ? '<div class="mu" style="font-size:12px">' + (it.src === "audio" ? "Transcribed from the audio on this computer, so check names and numbers. " : "") + (it.outside ? '<span class="err">' + it.outside + " timestamp" + (it.outside === 1 ? "" : "s") + " fall outside the video.</span> " : "Timestamps inside the video. ") + (it.shard ? "Saved " + esc(it.shard) + "." + (it.shardNote ? " " + esc(it.shardNote) : "") : it.shardErr ? '<span class="err">Not saved: ' + esc(it.shardErr) + "</span>" : "") + (it.model ? " · " + esc(it.model) : "") + "</div>" : it.status === "error" ? '<div class="mu err" style="font-size:12px">' + esc(it.err) + "</div>" : it.stage ? '<div class="mu" style="font-size:12px">' + esc(it.stage) + "</div>" : "";
      const body = it.status === "done" ? '<details class="vf"><summary class="vh" style="cursor:pointer">Read the summary</summary><div class="md">' + md(it.text) + '</div><div class="acts"><button type="button" class="chip" data-cp="' + esc(it.id) + '">Copy</button>' + (it.shard ? "" : '<button type="button" class="chip" data-sh="' + esc(it.id) + '">Shard</button>') + "</div></details>" : "";
      return '<div style="padding:6px 0;border-bottom:1px solid var(--ln)"><div class="vr">' + icon + head + '<a class="mu" href="https://www.youtube.com/watch?v=' + esc(it.id) + '" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer" title="Open the video">↗</a><button type="button" class="chip" data-rm="' + esc(it.id) + '" title="Remove">×</button></div>' + meta + body + "</div>";
    };
    bd.innerHTML = (S.bridge ? "" : '<div class="mu err">Batch needs the NouGenOpen bridge, which fetches transcripts and transcribes audio on this computer. Start <b>nougen-open serve</b> and reopen this tab.</div>') +
      '<textarea id="bl" rows="3" style="width:100%;box-sizing:border-box;background:var(--bg);color:inherit;border:1px solid var(--ln);border-radius:var(--r);padding:8px;font:inherit" placeholder="Paste YouTube links, one per line (up to ' + BATCH_MAX + '), or a playlist link">' + esc(B.draft || "") + "</textarea>" +
      '<div class="acts"><button type="button" class="chip on" id="ba">Add links</button><button type="button" class="chip" id="bc">Add this video</button><button type="button" class="chip" id="bp" title="Add every video of the playlist this video was opened from">Add this playlist</button></div>' +
      (B.notes ? '<div class="mu">' + esc(B.notes) + "</div>" : "") +
      (B.items.length ? '<div style="margin:8px 0 4px;height:4px;background:var(--ln);border-radius:2px"><div style="height:4px;width:' + pct + '%;background:var(--ac);border-radius:2px"></div></div><div class="mu" style="font-size:12px">' + done + " of " + B.items.length + " done" + (errs ? ", " + errs + " failed" : "") + (B.running && S.keepAwake !== false ? " · keeping this computer awake" : "") + "</div>" : '<div class="mu">Each video gets its own summary. Videos without captions are transcribed from their audio on this computer (up to 150 minutes each).</div>') +
      B.items.map(row).join("") +
      (done ? '<div class="acts" style="margin-top:8px"><button type="button" class="chip on" id="bcopy">Copy all summaries</button><button type="button" class="chip" id="bshall">Shard unsaved</button><button type="button" class="chip" id="bclr">Clear</button></div>' : B.items.length ? '<div class="acts" style="margin-top:8px"><button type="button" class="chip" id="bclr">Clear</button></div>' : "");
    $("bl").oninput = e => { B.draft = e.target.value; };
    $("ba").onclick = async () => { const t = $("bl").value; B.draft = ""; await batchAdd(t); };
    $("bc").onclick = () => batchAdd(S.vid ? "https://www.youtube.com/watch?v=" + S.vid : "");
    $("bp").onclick = batchPlaylistHere;
    bd.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { B.items = B.items.filter(i => i.id !== b.dataset.rm); delete B.mem[b.dataset.rm]; btSave(); btPaint(); });
    bd.querySelectorAll("[data-cp]").forEach(b => b.onclick = () => { const it = B.items.find(i => i.id === b.dataset.cp); navigator.clipboard.writeText(it.title + " - YouTube\nhttps://www.youtube.com/watch?v=" + it.id + "\n\n" + it.text).then(() => { b.textContent = "Copied ✓"; setTimeout(() => { if (b.isConnected) b.textContent = "Copy"; }, 1300); }); });
    bd.querySelectorAll("[data-sh]").forEach(b => b.onclick = async () => { b.innerHTML = '<span class="spin"></span> Saving'; await batchShard(B.items.find(i => i.id === b.dataset.sh)); });
    if ($("bcopy")) $("bcopy").onclick = () => navigator.clipboard.writeText(batchDoc()).then(() => { const e = $("bcopy"); e.textContent = "Copied ✓"; setTimeout(() => { if (e.isConnected) e.textContent = "Copy all summaries"; }, 1300); });
    if ($("bshall")) $("bshall").onclick = async () => { for (const it of B.items) if (it.status === "done" && !it.shard) await batchShard(it); };
    if ($("bclr")) $("bclr").onclick = () => { if (B.running) return; B.items = []; B.mem = {}; B.notes = ""; btSave(); btPaint(); };
  }

  // ---------- persistence / export ----------
  const key = () => "v:" + S.vid;
  function save() { chrome.storage.local.set({ [key()]: { summary: S.summary, chat: S.chat, hl: S.hl, shardMsg: /^(Could not|Nothing)/.test(S.shardMsg || "") ? "" : (S.shardMsg || ""), morph: S.morph && !S.morph.busy ? S.morph : null, tr: S.tr && !S.tr.busy && !S.tr.err ? { lang: S.tr.lang, out: S.tr.out, done: S.tr.out.length } : null } }); }
  const saveHl = save;
  // Copy format: "<title> - YouTube\n<url>\n\nTranscript:\n(mm:ss) paragraph"
  const pad = t => { t = Math.floor(t); const h = t / 3600 | 0, m = String((t % 3600) / 60 | 0).padStart(2, "0"), x = String(t % 60).padStart(2, "0"); return h ? `${h}:${m}:${x}` : `${m}:${x}`; };
  const vtitle = () => (S.title = document.querySelector("ytd-watch-metadata h1, h1.ytd-watch-metadata")?.textContent.trim() || (S.title !== "YouTube" && S.title) || document.title.replace(/ - YouTube$/, ""));
  const copyText = () => `${vtitle()} - YouTube\nhttps://www.youtube.com/watch?v=${S.vid}\n\nTranscript:\n` + S.paras.map(l => `(${pad(l.t)}) ${l.text}`).join("\n");
  function srtTime(t) { const ms = Math.round(t * 1000), h = ms / 3600000 | 0, m = (ms % 3600000) / 60000 | 0, s = (ms % 60000) / 1000 | 0;
    return [h, m, s].map(n => String(n).padStart(2, "0")).join(":") + "," + String(ms % 1000).padStart(3, "0"); }
  function save2(ext, text, type) { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type }));
    a.download = (S.title || S.vid).replace(/[\\/:*?"<>|]+/g, "_").slice(0, 80) + ext; a.click(); }
  function download(kind = "md", front = "") {
    if (kind === "plain") return save2(".txt", S.paras.map((l, i) => trOf(l, i)).join("\n\n") + "\n", "text/plain");
    const url = "https://www.youtube.com/watch?v=" + S.vid, when = new Date().toISOString().slice(0, 10);
    const hl = Object.keys(S.hl).map(Number).sort((a, b) => a - b).map(k => ({ seconds: k | 0, time: fmt(k), text: S.hl[k] }));
    const tr = S.paras.map((l, i) => ({ seconds: l.t | 0, time: fmt(l.t), text: trOf(l, i) }));
    if (kind === "json") return save2(".json", JSON.stringify({ title: vtitle(), url, videoId: S.vid, captured: when, language: S.tr ? S.tr.lang : null, summary: S.summary || "", highlights: hl, transcript: tr,
      chat: S.chat.filter(m => m.content).map(m => ({ role: m.role, content: m.content, scope: m.scope || "video" })), morph: S.morph && S.morph.text ? { target: tname(S.morph), plan: S.morph.text } : null }, null, 2), "application/json");
    if (kind === "csv") {
      const q = v => '"' + String(v).replace(/"/g, '""') + '"', row = (type, r) => [type, r.seconds, r.time, q(r.text), url + "&t=" + r.seconds].join(",");
      return save2(".csv", ["type,seconds,time,text,link"].concat(hl.map(h => row("highlight", h)), tr.map(r => row("transcript", r))).join("\n") + "\n", "text/csv");
    }
    if (kind === "html") {
      const link = r => '<a class="t" href="' + url + "&t=" + r.seconds + '">' + r.time + "</a>";
      return save2(".html", '<!doctype html><meta charset="utf-8"><title>' + esc(vtitle()) + '</title><style>body{font:16px/1.6 system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;color:#211a2f}a{color:#6941c6}.t{font-variant-numeric:tabular-nums;margin-right:.6em}</style><h1>' + esc(vtitle()) + '</h1><p><a href="' + url + '">' + url + "</a> · saved " + when + "</p>" +
        (S.summary ? "<h2>Summary</h2>" + md(S.summary) : "") + (hl.length ? "<h2>Highlights</h2><ul>" + hl.map(h => "<li>" + link(h) + esc(h.text) + "</li>").join("") + "</ul>" : "") +
        "<h2>Transcript</h2>" + tr.map(r => "<p>" + link(r) + esc(r.text) + "</p>").join(""), "text/html");
    }
    if (kind === "obsidian") return download("md", "---\ntitle: " + JSON.stringify(vtitle()) + "\nsource: " + url + "\ntype: youtube\ncaptured: " + when + "\ntags: [youtube, nougentube]\n---\n\n");
    if (kind === "txt") return save2(".txt", copyText() + "\n", "text/plain");
    if (kind === "srt") return save2(".srt", S.lines.map((l, i) => `${i + 1}\n${srtTime(l.t)} --> ${srtTime(S.lines[i + 1] ? Math.min(S.lines[i + 1].t, l.t + 7) : l.t + 4)}\n${l.text}\n`).join("\n"), "application/x-subrip");
    const hk = Object.keys(S.hl).map(Number).sort((a, b) => a - b);
    const out = `# ${S.title}\nhttps://www.youtube.com/watch?v=${S.vid}\n\n` + (S.summary ? `## Summary\n${S.summary}\n\n` : "") +
      (hk.length ? `## Highlights\n${hk.map(k => `- [${fmt(k)}](https://youtu.be/${S.vid}?t=${k | 0}) ${S.hl[k]}`).join("\n")}\n\n` : "") +
      `## Transcript\n${S.paras.map((l, i) => `[${fmt(l.t)}] ${trOf(l, i)}`).join("\n\n")}\n`;
    save2(".md", front + out, "text/markdown");
  }

  // ---------- lifecycle (YouTube is an SPA) ----------
  async function load() {
    const vid = new URLSearchParams(location.search).get("v");
    if (location.pathname !== "/watch" || !vid) { host?.remove(); host = null; return; }
    if (!mount()) return setTimeout(load, 500);
    if (!alive()) return render();
    if (vid === S.vid) return;
    if (S.port?.bound) { S.port.cancel(); try { S.port.disconnect(); } catch {} S.port = null; }
    Object.assign(S, { vid, gen: (S.gen || 0) + 1, lines: [], paras: [], err: null, summary: "", chat: [], hl: {}, q: "", tT0: Date.now(), tStage: "", shardMsg: "", morph: null, tr: null }); render();
    const st = (await chrome.storage.local.get(key()))[key()]; if (st) Object.assign(S, st);
    Object.assign(S, await chrome.storage.sync.get(["sty", "len", "lng", "custom"])); render(); note();
    try {
      const to = (pr, ms) => Promise.race([Promise.resolve(pr).catch(e => (console.warn("[NouGenTube]", e), null)), new Promise(r => setTimeout(() => r(null), ms))]);
      const wait = ms => new Promise(r => setTimeout(r, ms));
      const gone = () => vid !== S.vid || !alive();
      S.title = document.title.replace(/^\(\d+\)\s*/, "").replace(/ - YouTube$/, "");

      // 0. Saved copy from an earlier visit: instant, and immune to YouTube having a bad moment.
      let r = S.fresh ? null : await to(cacheGet(vid), 1500);
      S.fresh = false;

      // 1-4. Independent ways to get the transcript, tried in order, the whole ladder up to 3
      // times. One source failing never ends in an error while another can still answer.
      const TRIES = 3; let info = null;
      for (let n = 1; n <= TRIES && !r && !gone(); n++) {
        if (n > 1) { setStage(`Trying again (${n} of ${TRIES})`); await wait(1200 * n); if (gone()) return; }
        // A background tab can't render YouTube's panel, but the player still serves captions.
        if (document.hidden) r = await to(viaPlayer(vid), 12000);
        if (!r && n > 1) r = captured(vid);
        if (!r && !gone()) r = await to(viaPanel(vid, 18000), document.hidden ? 864e5 : 20000);
        if (!r && !gone()) { setStage("Asking the video player for its captions"); r = await to(viaPlayer(vid), 12000); }
        if (!r && !gone()) { setStage("Trying YouTube's caption service");
          const p = await to(playerResponse(vid), 10000);
          if (p) { S.title = p.pr?.videoDetails?.title || S.title; r = (await to(viaTimedtext(p.pr), 8000)) || (await to(viaInnertube(p), 8000)); } }
        if (!r && !gone()) {   // stop early only when YouTube itself says there is nothing to get
          info = await pageInfo();
          if (info && info.vid === vid && !info.tracks.length && !document.querySelector(BTN)) break;
        }
      }
      // 5. Nothing from YouTube: the NouGenOpen bridge can transcribe the audio on this computer.
      S.audioErr = "";
      if (!r && !gone() && S.bridge) {
        setStage("Transcribing the audio on this computer. A long video can take a few minutes");
        const t = await withAwake(() => tubeCall("transcript", { video_id: vid, audio: "auto", max_minutes: 150 }));
        if (t && t.ok && t.lines && t.lines.length) r = { lines: t.lines, lang: t.source === "whisper" ? "audio" : "bridge" };
        else S.audioErr = (t && t.error) || "the bridge did not answer";
      }
      if (gone()) return;
      if (r) { r.lines = monotonic(r.lines); S.lines = r.lines; S.lang = r.lang; S.paras = paragraphs(r.lines); if (r.lang !== "saved") cachePut(vid, r); }
      else S.err = (info && info.vid === vid && !info.tracks.length && !document.querySelector(BTN))
        ? "This video has no captions, so there is no transcript to read." + (S.audioErr ? " Audio transcription: " + S.audioErr : S.bridge ? "" : " Start the NouGenOpen bridge (nougen-open serve) to transcribe the audio on this computer.")
        : "YouTube has captions for this video but didn't return them after 3 tries." + (S.audioErr ? " Audio transcription: " + S.audioErr : "");
    } catch (e) { S.err = "Transcript fetch failed: " + e.message; }
    render();
  }
  document.addEventListener("yt-navigate-finish", load);
  // The toolbar button asks this tab to bring the panel forward.
  chrome.runtime.onMessage.addListener((m, _from, reply) => {
    if (!m || m.type !== "focus-panel") return;
    if (!host || !host.isConnected) return reply({ ok: false });
    host.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    const wrap = root.getElementById("wrap"); if (wrap && wrap.hidden) root.getElementById("col").click();
    reply({ ok: true });
  });
  // Closing the tab while a batch, a Morph or a translation is running would lose it; ask first (Electron: preventDefault on close).
  addEventListener("beforeunload", e => { if ((S.bt && S.bt.running) || (S.tr && S.tr.busy) || (S.morph && S.morph.busy)) { e.preventDefault(); e.returnValue = ""; } });
  load();
})();
