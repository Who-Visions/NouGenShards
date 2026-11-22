// Which Mono Violet scheme "Auto" shows. No DOM, no chrome.* calls, so it runs in node too.
// Loaded before content.js (manifest order); content.js reads it as NGT_THEME.
// Following Electron's nativeTheme model: the app's own theme is the truth when it has one, the system setting is the
// fallback, and the caller re-asks whenever either changes.
(function (root) {
  // "#0f0f0f", "#fff", "rgb(15, 15, 15)" or "rgba(...)" -> {r, g, b}; anything else -> null.
  function parseColor(s) {
    const t = String(s == null ? "" : s).trim();
    let m = t.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if (m) {
      const h = m[1].length === 3 ? m[1].split("").map(c => c + c).join("") : m[1];
      return { r: parseInt(h.slice(0, 2), 16), g: parseInt(h.slice(2, 4), 16), b: parseInt(h.slice(4, 6), 16) };
    }
    m = t.match(/^rgba?\(\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})/i);
    return m ? { r: +m[1], g: +m[2], b: +m[3] } : null;
  }

  // WCAG relative luminance, 0 (black) to 1 (white).
  function luminance(c) {
    const lin = v => { const s = v / 255; return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4); };
    return 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  }

  // ytBackground: YouTube's page colour (its --yt-spec-base-background); ytDarkAttr: <html dark>; osDark: prefers-color-scheme.
  function resolveAuto(i) {
    i = i || {};
    const c = parseColor(i.ytBackground);
    if (c) return luminance(c) < 0.35 ? "dark" : "light";
    if (i.ytDarkAttr) return "dark";
    return i.osDark ? "dark" : "light";
  }

  const api = { parseColor, luminance, resolveAuto };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.NGT_THEME = api;
})(typeof self !== "undefined" ? self : globalThis);
