// NouGenTube page-world hook (runs in YouTube's own JS world at document_start).
// The player fetches its caption track from /api/timedtext with a token only it holds.
// This passes a copy of that response to the content script, and answers "which caption
// tracks does the current video have?" from the player itself. Read-only: it never changes
// a request or a response.
(() => {
  if (window.__ngtHook) return; window.__ngtHook = true;
  const isTT = u => /\/api\/timedtext/.test(String(u || ""));
  const post = (url, body) => { try { if (body) window.postMessage({ __ngt: "timedtext", url: String(url), body: String(body) }, location.origin); } catch {} };

  const origFetch = window.fetch;
  window.fetch = function (input) {
    const p = origFetch.apply(this, arguments);
    try {
      const url = typeof input === "string" ? input : input && input.url;
      if (isTT(url)) p.then(r => r.clone().text().then(t => post(url, t))).catch(() => {});
    } catch {}
    return p;
  };

  const origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    try {
      if (isTT(url)) this.addEventListener("load", () => {
        try { post(url, typeof this.response === "string" ? this.response : JSON.stringify(this.response)); } catch {}
      });
    } catch {}
    return origOpen.apply(this, arguments);
  };

  window.addEventListener("message", e => {
    if (e.source !== window || !e.data || e.data.__ngt !== "info?") return;
    let pr = null;
    try { pr = document.getElementById("movie_player")?.getPlayerResponse?.(); } catch {}
    const tracks = (pr?.captions?.playerCaptionsTracklistRenderer?.captionTracks || [])
      .map(t => ({ lang: t.languageCode, kind: t.kind || "", name: t.name?.simpleText || "" }));
    window.postMessage({ __ngt: "info", id: e.data.id, vid: pr?.videoDetails?.videoId || "", title: pr?.videoDetails?.title || "", tracks }, location.origin);
  });
})();
