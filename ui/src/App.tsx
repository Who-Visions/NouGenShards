import { useCallback, useEffect, useMemo, useState } from 'react';

// ---------------------------------------------------------------------------
// Tauri bridge with browser fallback.
// Inside the Tauri shell, commands hit the real Python engine. In a plain
// browser (e.g. vite dev preview without Tauri) we show demo data so the HUD
// is still inspectable.
// ---------------------------------------------------------------------------

type InvokeFn = (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;

const tauriInvoke: InvokeFn | null =
  typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
    ? (window as any).__TAURI_INTERNALS__.invoke
    : null;

const DEMO_SHARDS = [
  {
    id: 1,
    title: 'Demo shard — run inside Tauri for live data',
    content:
      'This is sample data shown because the HUD is running in a plain browser. Launch with `npm run tauri dev` to search your real substrate.',
    final_score: 0.92,
    utility_score: 1.0,
    _db_index: 3,
  },
  {
    id: 2,
    title: 'Bayesian ranking demo',
    content: 'Shards are ranked by BM25 + semantic similarity, weighted by utility priors.',
    final_score: 0.71,
    utility_score: 0.8,
    _db_index: 7,
  },
];

const DEMO_STATUS = {
  total_shards: 12873,
  databases: [1, 2, 3, 4, 6, 7, 8, 9].map((i) => ({
    index: i,
    shards: Math.floor(400 + ((i * 7919) % 3000)),
    size_mb: 12 + ((i * 31) % 220),
    is_active: false,
  })),
};

// Client-side guard slightly longer than the Rust engine timeout (30s), so a
// real engine error message wins the race; this only fires if the bridge itself
// wedges. Guarantees the UI never sticks on a spinner.
const CLIENT_TIMEOUT_MS = 35_000;

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error('Engine did not respond (timed out). Is the substrate reachable?')),
      ms
    );
    p.then(
      (v) => {
        clearTimeout(timer);
        resolve(v);
      },
      (e) => {
        clearTimeout(timer);
        reject(e);
      }
    );
  });
}

async function callEngine(cmd: string, args: Record<string, unknown>): Promise<unknown> {
  if (!tauriInvoke) {
    await new Promise((r) => setTimeout(r, 250));
    if (cmd === 'search_shards') return JSON.stringify(DEMO_SHARDS);
    if (cmd === 'engine_status') return JSON.stringify(DEMO_STATUS);
    return JSON.stringify({ period: args.period ?? 'week', demo: true });
  }
  return withTimeout(tauriInvoke(cmd, args), CLIENT_TIMEOUT_MS);
}

// ---------------------------------------------------------------------------

interface Shard {
  id: number;
  title: string;
  content: string;
  final_score?: number;
  utility_score?: number;
  _db_index?: number;
}

interface DbInfo {
  index: number;
  shards: number;
  size_mb: number;
}

type Tab = 'search' | 'substrate' | 'stats';

export default function App() {
  const [tab, setTab] = useState<Tab>('search');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Shard[]>([]);
  const [status, setStatus] = useState<{ total_shards: number; databases: DbInfo[] } | null>(null);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [period, setPeriod] = useState('week');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshStatus = useCallback(async () => {
    try {
      const raw = (await callEngine('engine_status', {})) as string;
      setStatus(JSON.parse(raw));
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  const loadStats = useCallback(async () => {
    setBusy(true);
    try {
      const raw = (await callEngine('memory_stats', { period })) as string;
      setStats(JSON.parse(raw));
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, [period]);

  useEffect(() => {
    if (tab !== 'stats') return;
    loadStats();
  }, [tab, loadStats]);

  const runSearch = useCallback(async () => {
    if (!query.trim()) return;
    setBusy(true);
    try {
      const raw = (await callEngine('search_shards', { query })) as string;
      setResults(JSON.parse(raw));
      setError(null);
    } catch (e) {
      setError(String(e));
      setResults([]);
    } finally {
      setBusy(false);
    }
  }, [query]);

  const retry = useCallback(() => {
    setError(null);
    refreshStatus();
    if (tab === 'search' && query.trim()) runSearch();
    if (tab === 'stats') loadStats();
  }, [tab, query, refreshStatus, runSearch, loadStats]);

  const totalShards = status?.total_shards ?? 0;
  const maxScore = useMemo(
    () => Math.max(0.0001, ...results.map((r) => r.final_score ?? 0)),
    [results]
  );

  return (
    <div className="hud">
      <header className="hud-header">
        <div className="brand">
          <span className="brand-mark">◈</span>
          <div>
            <h1>NouGenShards</h1>
            <p className="tagline">Cortex HUD — local memory substrate</p>
          </div>
        </div>
        <div className="header-right">
          {!tauriInvoke && <span className="badge demo">browser preview — demo data</span>}
          <span className="badge">
            <span className={`dot ${status ? 'ok' : 'warn'}`} />
            {status ? `${totalShards.toLocaleString()} shards` : 'connecting…'}
          </span>
        </div>
      </header>

      <nav className="tabs">
        {(['search', 'substrate', 'stats'] as Tab[]).map((t) => (
          <button key={t} className={tab === t ? 'tab active' : 'tab'} onClick={() => setTab(t)}>
            {t === 'search' ? 'Search' : t === 'substrate' ? 'Substrate' : 'Stats'}
          </button>
        ))}
      </nav>

      {error && (
        <div className="error-bar">
          <span className="error-msg">{error}</span>
          <button className="error-retry" onClick={retry} disabled={busy}>
            Retry
          </button>
        </div>
      )}

      {tab === 'search' && (
        <section className="panel">
          <div className="search-row">
            <input
              value={query}
              placeholder="Search your memory substrate…"
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && runSearch()}
              autoFocus
            />
            <button className="primary" onClick={runSearch} disabled={busy}>
              {busy ? 'Searching…' : 'Recall'}
            </button>
          </div>

          <div className="results">
            {results.length === 0 && !busy && (
              <p className="empty">No results yet. Recall something from the fabric.</p>
            )}
            {results.map((s) => (
              <article key={`${s._db_index}-${s.id}`} className="shard">
                <div className="shard-head">
                  <h3>{s.title}</h3>
                  <span className="shard-meta">
                    DB {s._db_index ?? '?'} · #{s.id}
                  </span>
                </div>
                <p className="shard-body">{s.content}</p>
                <div className="score-track">
                  <div
                    className="score-fill"
                    style={{ width: `${((s.final_score ?? 0) / maxScore) * 100}%` }}
                  />
                </div>
                <span className="score-label">
                  posterior {(s.final_score ?? 0).toFixed(2)} · prior{' '}
                  {(s.utility_score ?? 0).toFixed(2)}
                </span>
              </article>
            ))}
          </div>
        </section>
      )}

      {tab === 'substrate' && (
        <section className="panel">
          <div className="substrate-grid">
            {Array.from({ length: 9 }, (_, i) => i + 1).map((idx) => {
              const db = status?.databases?.find((d) => d.index === idx);
              const pct = db ? Math.min(100, (db.size_mb / 1024) * 100) : 0;
              return (
                <div key={idx} className={db ? 'cell live' : 'cell'}>
                  <span className="cell-index">DB {idx}</span>
                  {db ? (
                    <>
                      <span className="cell-count">{db.shards.toLocaleString()}</span>
                      <span className="cell-sub">{db.size_mb.toFixed(1)} MB</span>
                      <div className="cap-track">
                        <div className="cap-fill" style={{ width: `${pct}%` }} />
                      </div>
                    </>
                  ) : (
                    <span className="cell-sub">empty</span>
                  )}
                </div>
              );
            })}
          </div>
          <button className="ghost" onClick={refreshStatus}>
            Refresh substrate
          </button>
        </section>
      )}

      {tab === 'stats' && (
        <section className="panel">
          <div className="period-row">
            {['24h', 'week', 'month', 'quarter', 'year'].map((p) => (
              <button
                key={p}
                className={period === p ? 'chip active' : 'chip'}
                onClick={() => setPeriod(p)}
              >
                {p}
              </button>
            ))}
          </div>
          <pre className="stats-json">
            {busy ? 'Loading…' : JSON.stringify(stats, null, 2)}
          </pre>
        </section>
      )}

      <footer className="hud-footer">
        local-first · encrypted vault · Who Visions LLC
      </footer>
    </div>
  );
}
