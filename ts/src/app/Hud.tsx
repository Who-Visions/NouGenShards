/**
 * NouGenShards Cortex HUD. (TSX/JSX mimic of the Gradio Blocks layout in app.py)
 *
 * The Python UI was a `gr.Blocks` with 5 tabs (Search, History, Substrate, Recon,
 * Transcript) wired to server-side functions. Here that layout is a single React
 * function component that fetches the matching /api/* endpoints in server.ts and
 * renders their JSON. Self-contained: no CSS framework, only minimal inline styles.
 */
import React, { useState, useEffect } from "react";

/** Tab identifiers paired with their Gradio emoji labels. */
const TABS: ReadonlyArray<readonly [label: string, id: string]> = [
  ["🔍 Search", "search"],
  ["📈 History", "history"],
  ["🗺️ Substrate", "substrate"],
  ["🧠 Recon", "recon"],
  ["📝 Transcript", "transcript"],
];

const card: React.CSSProperties = {
  whiteSpace: "pre-wrap",
  background: "#1a1d2b",
  padding: 16,
  borderRadius: 6,
};

/** Mimic of gr.Blocks(title="NouGenShards Cortex HUD") with 5 tabs. */
export default function CortexHud(): React.ReactElement {
  const [tab, setTab] = useState<string>("search");
  const [query, setQuery] = useState<string>("");
  const [text, setText] = useState<string>("");
  const [maps, setMaps] = useState<string[]>([]);

  const getJson = (u: string): Promise<any> => fetch(u).then((r) => r.json());

  // 🔍 Search tab: gr_search via /api/search?q=
  const runSearch = (): void => {
    getJson("/api/search?q=" + encodeURIComponent(query)).then((d) => setText(d.markdown));
  };

  // Load data when switching tabs (mirrors Gradle button.click / .load wiring).
  useEffect(() => {
    if (tab === "history") {
      getJson("/api/analytics").then((d) => setText(`${d.stats}\n\n${d.timeline}`));
    } else if (tab === "substrate") {
      getJson("/api/substrate").then((d) => setMaps(d.maps));
    } else if (tab === "recon") {
      getJson("/api/recon").then((d) => setText(d.markdown));
    } else if (tab === "transcript") {
      getJson("/api/transcript").then((d) => setText(`${d.status}\n\n${d.preview}`));
    }
  }, [tab]);

  return (
    <div style={{ padding: 20, fontFamily: "system-ui, sans-serif", color: "#e6e6e6", background: "#0f1117" }}>
      <h1>🪩 NouGenShards Cortex HUD</h1>

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {TABS.map(([label, id]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            style={{
              padding: "8px 12px",
              background: tab === id ? "#2d3350" : "#1a1d2b",
              color: "#fff",
              border: "1px solid #333",
              borderRadius: 6,
              cursor: "pointer",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "search" && (
        <div style={{ marginBottom: 16 }}>
          <input
            value={query}
            placeholder="What do I know about..."
            onChange={(ev) => setQuery(ev.target.value)}
            style={{ width: "60%", padding: 8 }}
          />
          <button onClick={runSearch} style={{ marginLeft: 8, padding: 8 }}>
            Search Memory
          </button>
        </div>
      )}

      {tab === "substrate" ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
          {maps.map((m, i) => (
            <pre key={i} style={card}>
              {m}
            </pre>
          ))}
        </div>
      ) : (
        <pre style={card}>{text}</pre>
      )}
    </div>
  );
}
