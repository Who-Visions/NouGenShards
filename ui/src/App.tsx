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

const DEMO_ACTIVE_DB = 9;

const DEMO_STATUS = {
  total_shards: 12873,
  max_db_count: 9,
  active_db: DEMO_ACTIVE_DB,
  databases: [1, 2, 3, 4, 6, 7, 8, 9].map((i) => ({
    index: i,
    shards: Math.floor(400 + ((i * 7919) % 3000)),
    size_mb: 12 + ((i * 31) % 220),
    is_active: i === DEMO_ACTIVE_DB,
  })),
};

// Demo telemetry is deliberately modest and obviously synthetic — the browser
// preview must never look like a real meter reading.
const DEMO_USAGE = {
  period: 'week',
  invocations: 128,
  total_tokens: 1_284_000,
  prompt_tokens: 1_090_000,
  cached_tokens: 963_000,
  cache_hit_rate: 88.3,
  estimated_cost: 1.42,
  free_share: 61.0,
  by_model: [
    { provider: 'ollama', model: 'gemma4:31b-cloud', invocations: 74, total_tokens: 782_000, estimated_cost: 0 },
    { provider: 'anthropic', model: 'claude-opus-5', invocations: 41, total_tokens: 402_000, estimated_cost: 1.42 },
    { provider: 'google', model: 'gemini-3.7-flash', invocations: 13, total_tokens: 100_000, estimated_cost: 0 },
  ],
  ledger_present: true,
};

const DEMO_RELAY = [
  {
    id: 'demo_handoff_0002',
    timestamp: '2026-08-15T14:56:52',
    agent: 'claude-cli',
    machine: 'demo-node',
    branch: 'main',
    goal: 'Sample relay entry — run inside Tauri for your real handoff registry',
    tasks_done: 3,
    tasks_total: 4,
    status: 'open',
    live_status: 'in_progress',
    acknowledged_by: '',
  },
  {
    id: 'demo_handoff_0001',
    timestamp: '2026-08-15T11:04:10',
    agent: 'gemini',
    machine: 'demo-node',
    branch: 'main',
    goal: 'Second agent picked up the baton',
    tasks_done: 5,
    tasks_total: 5,
    status: 'acknowledged',
    live_status: 'acknowledged',
    acknowledged_by: 'codex',
  },
];

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
    if (cmd === 'token_usage') return JSON.stringify(DEMO_USAGE);
    if (cmd === 'relay_feed') return JSON.stringify(DEMO_RELAY);
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
  is_active?: boolean;
}

interface EngineStatus {
  total_shards: number;
  databases: DbInfo[];
  // Partition count is engine-owned (shards.MAX_DB_COUNT). Never assume 9 here.
  max_db_count?: number;
  active_db?: number;
}

// Per-partition capacity ceiling the engine rolls over at, in MB. Overridable
// so a rebuilt substrate with a different ceiling doesn't misdraw the gauges.
const PARTITION_CAP_MB = Number(import.meta.env.VITE_NOUGEN_PARTITION_CAP_MB ?? 1024);

interface UsageModel {
  provider: string;
  model: string;
  invocations: number;
  total_tokens: number;
  estimated_cost: number;
}

interface UsageSummary {
  period: string;
  invocations: number;
  total_tokens: number;
  prompt_tokens: number;
  cached_tokens: number;
  cache_hit_rate: number;
  estimated_cost: number;
  free_share: number;
  by_model: UsageModel[];
  ledger_present: boolean;
}

interface RelayEntry {
  id: string;
  timestamp: string;
  agent: string;
  machine: string;
  branch: string;
  goal: string;
  tasks_done: number;
  tasks_total: number;
  status: string;
  live_status: string;
  acknowledged_by: string;
}

type Tab = 'search' | 'substrate' | 'stats' | 'tracker' | 'relay';

const TABS: { key: Tab; label: string }[] = [
  { key: 'search', label: 'Search' },
  { key: 'substrate', label: 'Substrate' },
  { key: 'tracker', label: 'Tracker' },
  { key: 'relay', label: 'Relay' },
  { key: 'stats', label: 'Stats' },
];

const ALL_PARTITIONS = 'all';

export default function App() {
  const [tab, setTab] = useState<Tab>('search');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Shard[]>([]);
  const [status, setStatus] = useState<EngineStatus | null>(null);
  const [partition, setPartition] = useState<number | typeof ALL_PARTITIONS>(ALL_PARTITIONS);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [period, setPeriod] = useState('week');
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [usagePeriod, setUsagePeriod] = useState('week');
  const [relay, setRelay] = useState<RelayEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileMenuOpen, setFileMenuOpen] = useState(false);

  const toggleFileMenu = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setFileMenuOpen((o) => !o);
  }, []);

  useEffect(() => {
    if (!fileMenuOpen) return;
    const close = () => setFileMenuOpen(false);
    window.addEventListener('click', close);
    return () => window.removeEventListener('click', close);
  }, [fileMenuOpen]);

  const handleMinimize = useCallback(() => {
    tauriInvoke?.('minimize_window');
  }, []);

  const handleMaximize = useCallback(() => {
    tauriInvoke?.('toggle_maximize_window');
  }, []);

  const handleClose = useCallback(() => {
    tauriInvoke?.('close_window');
  }, []);

  const refreshStatus = useCallback(async () => {
    try {
      const raw = (await callEngine('engine_status', {})) as string;
      setStatus(JSON.parse(raw));
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const handleRefresh = useCallback(() => {
    setFileMenuOpen(false);
    refreshStatus();
  }, [refreshStatus]);

  const handleScan = useCallback(() => {
    setFileMenuOpen(false);
    setTab('substrate');
    refreshStatus();
  }, [refreshStatus]);

  const handleImport = useCallback(() => {
    setFileMenuOpen(false);
    setTab('stats');
  }, []);

  const handleExit = useCallback(() => {
    tauriInvoke?.('close_window');
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'q') {
        e.preventDefault();
        tauriInvoke?.('close_window');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
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

  const loadUsage = useCallback(async () => {
    setBusy(true);
    try {
      const raw = (await callEngine('token_usage', { period: usagePeriod })) as string;
      setUsage(JSON.parse(raw));
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, [usagePeriod]);

  useEffect(() => {
    if (tab !== 'tracker') return;
    loadUsage();
  }, [tab, loadUsage]);

  const loadRelay = useCallback(async () => {
    setBusy(true);
    try {
      const raw = (await callEngine('relay_feed', {})) as string;
      setRelay(JSON.parse(raw));
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (tab !== 'relay') return;
    loadRelay();
  }, [tab, loadRelay]);

  const runSearch = useCallback(async () => {
    if (!query.trim()) return;
    setBusy(true);
    try {
      const raw = (await callEngine('search_shards', { query })) as string;
      setResults(JSON.parse(raw));
      setPartition(ALL_PARTITIONS);
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

  // Partition list is whatever the engine reports, not a fixed grid.
  const partitionIndices = useMemo(() => {
    const reported = status?.databases?.map((d) => d.index) ?? [];
    const ceiling =
      status?.max_db_count ?? (reported.length ? Math.max(...reported) : 0);
    return Array.from({ length: ceiling }, (_, i) => i + 1);
  }, [status]);

  const activeDb = useMemo(
    () => status?.active_db ?? status?.databases?.find((d) => d.is_active)?.index ?? null,
    [status]
  );

  // Partitions that actually returned hits — the only ones worth offering as filters.
  const hitPartitions = useMemo(() => {
    const seen = new Set<number>();
    for (const r of results) if (typeof r._db_index === 'number') seen.add(r._db_index);
    return [...seen].sort((a, b) => a - b);
  }, [results]);

  const visibleResults = useMemo(
    () => (partition === ALL_PARTITIONS ? results : results.filter((r) => r._db_index === partition)),
    [results, partition]
  );

  const maxScore = useMemo(
    () => Math.max(0.0001, ...visibleResults.map((r) => r.final_score ?? 0)),
    [visibleResults]
  );

  // `nougen stats --json` returns { period, growth: {new_shards, total_shards}, utility_delta }.
  const growth = useMemo(() => {
    const g = (stats?.growth ?? {}) as Record<string, unknown>;
    return {
      new_shards: Number(g.new_shards ?? 0),
      total_shards: Number(g.total_shards ?? 0),
    };
  }, [stats]);

  const utilityDelta = Number(stats?.utility_delta ?? 0);

  const accelerationRate =
    growth.total_shards > 0 ? (growth.new_shards / growth.total_shards) * 100 : null;

  return (
    <div className="app-container">
      <div className="titlebar" data-tauri-drag-region>
        <div className="titlebar-left">
          <div className="menu-item">
            <button
              className={`menu-btn ${fileMenuOpen ? 'active' : ''}`}
              onClick={toggleFileMenu}
            >
              File
            </button>
            {fileMenuOpen && (
              <div className="dropdown-content" onClick={(e) => e.stopPropagation()}>
                <button onClick={handleRefresh}>
                  <span>Refresh Substrate</span>
                </button>
                <button onClick={handleScan}>
                  <span>Scan Workspace</span>
                </button>
                <button onClick={handleImport}>
                  <span>Import History</span>
                </button>
                <div className="divider" />
                <button onClick={handleExit} className="danger-item">
                  <span>Exit</span>
                  <span className="shortcut">Ctrl+Q</span>
                </button>
              </div>
            )}
          </div>
        </div>
        <div className="titlebar-center" data-tauri-drag-region>
          NouGenShards Cortex HUD
        </div>
        <div className="titlebar-right">
          <button className="titlebar-btn minimize" onClick={handleMinimize} title="Minimize">
            <svg width="10" height="1" viewBox="0 0 10 1" fill="none"><path d="M0 0.5H10" stroke="currentColor" strokeWidth="1"/></svg>
          </button>
          <button className="titlebar-btn maximize" onClick={handleMaximize} title="Maximize">
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><rect x="0.5" y="0.5" width="9" height="9" stroke="currentColor" strokeWidth="1"/></svg>
          </button>
          <button className="titlebar-btn close" onClick={handleClose} title="Close">
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M0.5 0.5L9.5 9.5M9.5 0.5L0.5 9.5" stroke="currentColor" strokeWidth="1"/></svg>
          </button>
        </div>
      </div>
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
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            className={tab === key ? 'tab active' : 'tab'}
            onClick={() => setTab(key)}
          >
            {label}
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

          {results.length > 0 && (
            <div className="filter-row">
              <div className="partition-chips">
                <button
                  className={partition === ALL_PARTITIONS ? 'chip active' : 'chip'}
                  onClick={() => setPartition(ALL_PARTITIONS)}
                >
                  All Partitions
                </button>
                {hitPartitions.map((idx) => (
                  <button
                    key={idx}
                    className={partition === idx ? 'chip active' : 'chip'}
                    onClick={() => setPartition(idx)}
                  >
                    DB #{idx}
                    {idx === activeDb ? ' (Active)' : ''}
                  </button>
                ))}
              </div>
              <span className="result-count">
                Showing {visibleResults.length} of {results.length} shards
              </span>
            </div>
          )}

          <div className="results">
            {results.length === 0 && !busy && (
              <p className="empty">No results yet. Recall something from the fabric.</p>
            )}
            {visibleResults.map((s) => (
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
            {partitionIndices.map((idx) => {
              const db = status?.databases?.find((d) => d.index === idx);
              const pct = db ? Math.min(100, (db.size_mb / PARTITION_CAP_MB) * 100) : 0;
              const isActive = idx === activeDb;
              return (
                <div key={idx} className={`cell${db ? ' live' : ''}${isActive ? ' active' : ''}`}>
                  <span className="cell-index">
                    DB {idx}
                    {isActive && <span className="cell-active">ACTIVE</span>}
                  </span>
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

      {tab === 'tracker' && (
        <section className="panel">
          <div className="period-row">
            {['24h', 'week', 'month', 'quarter', 'year', 'all'].map((p) => (
              <button
                key={p}
                className={usagePeriod === p ? 'chip active' : 'chip'}
                onClick={() => setUsagePeriod(p)}
              >
                {p}
              </button>
            ))}
          </div>

          {busy && !usage ? (
            <p className="empty">Loading telemetry…</p>
          ) : usage && !usage.ledger_present ? (
            <p className="empty">
              No usage ledger yet. Route a request through <code>nougen router</code> and the meter
              starts filling.
            </p>
          ) : (
            <>
              <div className="tile-grid">
                <div className="tile">
                  <span className="tile-label">Blended tokens</span>
                  <span className="tile-value accent">
                    {(usage?.total_tokens ?? 0).toLocaleString()}
                  </span>
                  <span className="tile-sub">
                    {(usage?.invocations ?? 0).toLocaleString()} invocations
                  </span>
                </div>
                <div className="tile">
                  <span className="tile-label">Cache read rate</span>
                  <span className="tile-value accent">{(usage?.cache_hit_rate ?? 0).toFixed(1)}%</span>
                  <span className="tile-sub">
                    {(usage?.cached_tokens ?? 0).toLocaleString()} of{' '}
                    {(usage?.prompt_tokens ?? 0).toLocaleString()} input
                  </span>
                </div>
                <div className="tile">
                  <span className="tile-label">Shadow cost</span>
                  <span className="tile-value">${(usage?.estimated_cost ?? 0).toFixed(2)}</span>
                  <span className="tile-sub">list-price estimate, not an invoice</span>
                </div>
                <div className="tile">
                  <span className="tile-label">Free-lane share</span>
                  <span className="tile-value accent">{(usage?.free_share ?? 0).toFixed(1)}%</span>
                  <span className="tile-sub">tokens that cost nothing</span>
                </div>
              </div>

              <div className="ledger">
                {(usage?.by_model ?? []).length === 0 && (
                  <p className="empty">No metered calls in this window.</p>
                )}
                {(usage?.by_model ?? []).map((m) => (
                  <div key={`${m.provider}/${m.model}`} className="ledger-row">
                    <span className="ledger-model">
                      <span className="ledger-provider">{m.provider}</span>
                      {m.model}
                    </span>
                    <span className="ledger-tokens">{m.total_tokens.toLocaleString()} tok</span>
                    <span className="ledger-calls">{m.invocations.toLocaleString()}×</span>
                    <span className={m.estimated_cost > 0 ? 'ledger-cost' : 'ledger-cost free'}>
                      {m.estimated_cost > 0 ? `$${m.estimated_cost.toFixed(2)}` : 'free'}
                    </span>
                  </div>
                ))}
              </div>
              <button className="ghost" onClick={loadUsage} disabled={busy}>
                Refresh telemetry
              </button>
            </>
          )}
        </section>
      )}

      {tab === 'relay' && (
        <section className="panel">
          {busy && relay.length === 0 ? (
            <p className="empty">Reading relay…</p>
          ) : relay.length === 0 ? (
            <p className="empty">No handoffs on the registry yet.</p>
          ) : (
            <div className="relay-feed">
              {relay.map((h) => (
                <article key={h.id} className={`relay-card ${h.live_status}`}>
                  <div className="relay-head">
                    <span className="relay-agent">{h.agent.toUpperCase()}</span>
                    <span className={`relay-status ${h.live_status}`}>
                      {h.live_status.replace('_', ' ')}
                      {h.acknowledged_by && ` · ${h.acknowledged_by.toUpperCase()}`}
                    </span>
                  </div>
                  <p className="relay-goal">{h.goal || '(no goal recorded)'}</p>
                  <div className="relay-meta">
                    <span>{h.machine || 'unknown host'}</span>
                    {h.branch && <span>{h.branch}</span>}
                    <span>{(h.timestamp || '').replace('T', ' ').slice(0, 16)}</span>
                    {h.tasks_total > 0 && (
                      <span>
                        {h.tasks_done}/{h.tasks_total} tasks
                      </span>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
          <button className="ghost" onClick={loadRelay} disabled={busy}>
            Refresh relay
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
          {busy ? (
            <p className="empty">Loading…</p>
          ) : (
            <>
              <div className="tile-grid">
                <div className="tile">
                  <span className="tile-label">New shards captured</span>
                  <span className="tile-value accent">{growth.new_shards.toLocaleString()}</span>
                  <span className="tile-sub">this {stats?.period as string ?? period}</span>
                </div>
                <div className="tile">
                  <span className="tile-label">Total memory size</span>
                  <span className="tile-value">{growth.total_shards.toLocaleString()}</span>
                  <span className="tile-sub">shards on disk</span>
                </div>
                <div className="tile">
                  <span className="tile-label">Usefulness Δ</span>
                  <span className={`tile-value ${utilityDelta >= 0 ? 'accent' : 'warn'}`}>
                    {utilityDelta >= 0 ? '+' : ''}
                    {utilityDelta.toFixed(2)}
                  </span>
                  <span className="tile-sub">utility prior drift</span>
                </div>
                <div className="tile">
                  <span className="tile-label">Acceleration rate</span>
                  <span className="tile-value">
                    {accelerationRate === null ? '—' : `${accelerationRate.toFixed(1)}%`}
                  </span>
                  <span className="tile-sub">
                    {accelerationRate === null ? 'no shards yet' : 'expansion'}
                  </span>
                </div>
              </div>
              <details className="raw-json">
                <summary>Raw engine payload</summary>
                <pre className="stats-json">{JSON.stringify(stats, null, 2)}</pre>
              </details>
            </>
          )}
        </section>
      )}

      <footer className="hud-footer">
        local-first · encrypted vault · Who Visions LLC
      </footer>
    </div>
    </div>
  );
}
