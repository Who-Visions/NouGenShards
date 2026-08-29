// nougen-shard-failover — public gateway front with graceful degradation.
// Space-primary (persistent, always-up) -> blade-fallback (full live vault).
// The whole point: shards.nougenai.com keeps answering when blade dies, instead
// of a hard 502. Origins and timeouts are env-overridable so nothing is hardcoded.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname + url.search;
    const SPACE = env.SPACE_ORIGIN || "https://nougenai-nougenshards.hf.space";
    const BLADE = env.BLADE_ORIGIN || "https://blade.nougenai.com";
    // Federated search legitimately takes 10-30s (blade answers /search in
    // 9-11s over the tunnel; the Space adds read-through on top), so the old
    // 8s budget aborted every real query and manufactured 502s.
    const SPACE_MS = Number(env.SPACE_TIMEOUT_MS) || 35000;
    const BLADE_MS = Number(env.BLADE_TIMEOUT_MS) || 35000;

    // A request body is single-use: buffer it once so the blade fallback
    // doesn't replay an already-consumed stream after the Space attempt.
    const body = (request.method === "GET" || request.method === "HEAD")
      ? undefined : await request.arrayBuffer();

    const proxy = async (origin, ms) => {
      const ctl = new AbortController();
      const t = setTimeout(() => ctl.abort(), ms);
      try {
        return await fetch(origin + path, {
          method: request.method,
          headers: request.headers,
          body,
          signal: ctl.signal,
        });
      } finally { clearTimeout(t); }
    };

    // Try the always-up Space first. Only fall back on a real failure
    // (5xx or network/timeout) — a 4xx (e.g. 401 auth) is a valid answer.
    let spaceStatus = null;
    try {
      const rs = await proxy(SPACE, SPACE_MS);
      spaceStatus = rs.status;
      if (rs.status < 500) {
        const out = new Response(rs.body, rs);
        out.headers.set("x-nougen-origin", "space");
        return out;
      }
    } catch (_) { /* space down -> fall through */ }

    try {
      const rb = await proxy(BLADE, BLADE_MS);
      if (rb.status >= 500) {
        // Never pass Cloudflare's edge-502 body through as a healthy fallback:
        // name both statuses so the caller sees both origins are down.
        return new Response(JSON.stringify({ error: "both origins down",
            space_status: spaceStatus, blade_status: rb.status }),
          { status: 502, headers: { "content-type": "application/json", "x-nougen-origin": "none" } });
      }
      const out = new Response(rb.body, rb);
      out.headers.set("x-nougen-origin", "blade");
      return out;
    } catch (_) {
      return new Response(JSON.stringify({ error: "both origins unreachable" }),
        { status: 502, headers: { "content-type": "application/json", "x-nougen-origin": "none" } });
    }
  }
};
