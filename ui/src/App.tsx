import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

// ---------------------------------------------------------------------------
// Human-friendly date and time helper (Eastern Time)
// ---------------------------------------------------------------------------
function formatEasternTime(dateInput?: string): string {
  if (!dateInput) return 'Recently';
  try {
    let dateStr = dateInput;
    if (!dateStr.includes('Z') && !dateStr.includes('+') && !dateStr.includes('-')) {
      dateStr = dateStr.replace(' ', 'T') + 'Z';
    }
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateInput;
    return d.toLocaleString('en-US', {
      timeZone: 'America/New_York',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    }) + ' EDT';
  } catch {
    return dateInput;
  }
}

function getLiveEasternClock(): string {
  return new Date().toLocaleTimeString('en-US', {
    timeZone: 'America/New_York',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  }) + ' EDT';
}

type InvokeFn = (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;

const tauriInvoke: InvokeFn | null =
  typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
    ? (window as any).__TAURI_INTERNALS__.invoke
    : null;

const CLIENT_TIMEOUT_MS = 35_000;

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error('Memory service did not respond. Is the local engine running?')),
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
  if (tauriInvoke) {
    return withTimeout(tauriInvoke(cmd, args), CLIENT_TIMEOUT_MS);
  }

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(args)) if (value != null) params.set(key, String(value));
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CLIENT_TIMEOUT_MS);
  try {
    const response = await fetch(`/api/${cmd}?${params}`, { signal: controller.signal });
    if (!response.ok) throw new Error(`${cmd} unavailable (${response.status})`);
    return await response.text();
  } finally { clearTimeout(timer); }

}

// ---------------------------------------------------------------------------

interface Shard {
  id: number;
  title: string;
  content: string;
  final_score?: number;
  utility_score?: number;
  _db_index?: number;
  category?: string;
  timestamp?: string;
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
  max_db_count?: number;
  partition_cap_mb?: number;
  active_db?: number;
}



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

type Tab = 'search' | 'substrate' | 'fleet' | 'tracker' | 'relay' | 'stats';

const TABS: { key: Tab; label: string; icon: string }[] = [
  { key: 'search', label: 'Search Memory', icon: '🔍' },
  { key: 'substrate', label: 'Storage', icon: '💾' },
  { key: 'fleet', label: 'Your Machines', icon: '💻' },
  { key: 'tracker', label: 'Token & Cost Meter', icon: '⚡' },
  { key: 'relay', label: 'Team Handoffs', icon: '🤝' },
  { key: 'stats', label: 'Growth Stats', icon: '📈' },
];

const ALL_PARTITIONS = 'all';

function formatCompactNumber(num: number): string {
  if (!num) return '0';
  if (num >= 1_000_000_000) return (num / 1_000_000_000).toFixed(1) + 'B';
  if (num >= 1_000_000) return (num / 1_000_000).toFixed(1) + 'M';
  if (num >= 1_000) return (num / 1_000).toFixed(1) + 'K';
  return num.toLocaleString();
}

function getModelDisplayMeta(model: string, provider: string) {
  return { title: model, badge: provider, icon: '◈', isLocal: provider === 'ollama' || provider === 'local', tier: provider || 'Unknown provider' };
}

export default function App() {
  const [tab, setTab] = useState<Tab>('search');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Shard[]>([]);
  const [identity, setIdentity] = useState<any>(null);
  const [status, setStatus] = useState<EngineStatus | null>(null);
  const [partition, setPartition] = useState<number | typeof ALL_PARTITIONS>(ALL_PARTITIONS);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [period, setPeriod] = useState('week');
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [usagePeriod, setUsagePeriod] = useState('week');
  const [machineScope, setMachineScope] = useState<'local' | 'fleet'>('local');
  const [relay, setRelay] = useState<RelayEntry[]>([]);
  const [fleetNodes, setFleetNodes] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileMenuOpen, setFileMenuOpen] = useState(false);
  const [selectedShard, setSelectedShard] = useState<Shard | null>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [clockEastern, setClockEastern] = useState<string>(getLiveEasternClock);
  const requestVersions = useRef({usage: 0, stats: 0, search: 0});
  const memoryDialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = memoryDialog.current;
    if (selectedShard && dialog && !dialog.open) dialog.showModal();
    return () => { if (dialog?.open) dialog.close(); };
  }, [selectedShard]);

  // Trigger token usage refresh whenever time period or machine scope changes
  const loadUsage = useCallback(async () => {
    const version = ++requestVersions.current.usage;
    setUsage(null);
    setBusy(true);
    try {
      const raw = (await callEngine('token_usage', { period: usagePeriod, scope: machineScope })) as string;
      if (version !== requestVersions.current.usage) return;
      setUsage(JSON.parse(raw));

    } catch (e) {
      if (version !== requestVersions.current.usage) return;
      setError(String(e));
    } finally {
      if (version === requestVersions.current.usage) setBusy(false);
    }
  }, [usagePeriod, machineScope]);

  // Live clock updated every second in Eastern Time
  useEffect(() => {
    const timer = setInterval(() => {
      setClockEastern(getLiveEasternClock());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

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

    } catch (e) {
      setStatus(null);
      setError(String(e));
    }
  }, []);

  const loadFleet = useCallback(async () => {
    try {
      const raw = (await callEngine('fleet_nodes', {})) as string;
      const parsed = JSON.parse(raw);
      setFleetNodes(Array.isArray(parsed) ? parsed : []);
      setIdentity(JSON.parse(await callEngine('identity', {}) as string));
    } catch (e) { setFleetNodes([]); setError(String(e)); }
  }, []);

  const loadStats = useCallback(async () => {
    const version = ++requestVersions.current.stats;
    setStats(null);
    setBusy(true);
    try {
      const raw = (await callEngine('memory_stats', { period })) as string;
      if (version !== requestVersions.current.stats) return;
      setStats(JSON.parse(raw));

    } catch (e) {
      if (version !== requestVersions.current.stats) return;
      setError(String(e));
    } finally {
      if (version === requestVersions.current.stats) setBusy(false);
    }
  }, [period]);

  const loadRelay = useCallback(async () => {
    setBusy(true);
    try {
      const raw = (await callEngine('relay_feed', {})) as string;
      const parsed = JSON.parse(raw);
      setRelay(Array.isArray(parsed) ? parsed : []);

    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const runSearch = useCallback(async () => {
    const version = ++requestVersions.current.search;
    setResults([]);
    setBusy(true);
    try {
      const raw = (await callEngine('search_shards', { query })) as string;
      if (version !== requestVersions.current.search) return;
      const parsed = JSON.parse(raw);
      setResults(parsed.length > 0 ? parsed : []);
      setPartition(ALL_PARTITIONS);

    } catch (e) {
      if (version !== requestVersions.current.search) return;
      setError(String(e));
      setResults([]);
    } finally {
      if (version === requestVersions.current.search) setBusy(false);
    }
  }, [query]);

  // File menu actions. Declared after the loaders they call: a useCallback
  // dependency array is evaluated at render, so an earlier declaration hits the TDZ.
  const handleRefresh = useCallback(() => {
    setFileMenuOpen(false);
    refreshStatus();
    runSearch();
    loadFleet();
    loadRelay();
    loadUsage();
    loadStats();
  }, [refreshStatus, runSearch, loadFleet, loadRelay, loadUsage, loadStats]);

  // No dedicated scan command exists; engine_status and memory_stats read every database.
  const handleScan = useCallback(() => {
    setFileMenuOpen(false);
    refreshStatus();
    loadStats();
  }, [refreshStatus, loadStats]);

  // The relay tab is the activity feed (Team Handoffs).
  const handleImport = useCallback(() => {
    setFileMenuOpen(false);
    setTab('relay');
  }, []);

  const handleExit = useCallback(() => {
    setFileMenuOpen(false);
    handleClose();
  }, [handleClose]);

  // Tab change triggers
  useEffect(() => {
    if (tab === 'tracker') loadUsage();
    if (tab === 'relay') loadRelay();
    if (tab === 'fleet') loadFleet();
    if (tab === 'stats') loadStats();
    if (tab === 'search') runSearch();
  }, [tab, loadUsage, loadRelay, loadFleet, loadStats, runSearch]);

  // Poll only discovery; query and period changes load their own active tab.
  useEffect(() => {
    let pending = false;
    const poll = async () => {
      if (pending || document.hidden) return;
      pending = true;
      try { await Promise.all([refreshStatus(), loadFleet()]); }
      finally { pending = false; }
    };
    poll();
    const timer = setInterval(poll, 15000);
    return () => clearInterval(timer);
  }, [refreshStatus, loadFleet]);

  const retry = useCallback(() => {
    setError(null);

    refreshStatus();
    if (tab === 'search') runSearch();
    if (tab === 'stats') loadStats();
    if (tab === 'tracker') loadUsage();
    if (tab === 'relay') loadRelay();
  }, [tab, refreshStatus, runSearch, loadStats, loadUsage, loadRelay]);

  const copyShardText = useCallback((shard: Shard, e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(`[Memory #${shard.id}] ${shard.title}\n\n${shard.content}`);
    setCopiedId(shard.id);
    setTimeout(() => setCopiedId(null), 2000);
  }, []);

  const totalShards = status?.total_shards ?? 0;

  const partitionIndices = useMemo(() => {
    const reported = status?.databases?.map((d) => d.index) ?? [];
    return reported;
  }, [status]);

  const activeDb = useMemo(
    () => status?.active_db ?? status?.databases?.find((d) => d.is_active)?.index ?? null,
    [status]
  );

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

  const growth = useMemo(() => {
    const g = (stats?.growth ?? {}) as Record<string, unknown>;
    return {
      new_shards: Number(g.new_shards ?? 0),
      total_shards: Number(g.total_shards ?? status?.total_shards ?? 0),
    };
  }, [stats]);

  const utilityDelta = Number(stats?.utility_delta ?? 0);

  const accelerationRate =
    growth.total_shards > 0 ? (growth.new_shards / growth.total_shards) * 100 : 0;

  return (
    <div className="app-container">
      {/* Live Particle Backdrop */}
      {/* NouGenDesigns: decorative canvas motion is not part of the workbench. */}

      {/* Top Fixed Zone: Titlebar + Streamlined Header + Navigation */}
      <div className="fixed-header-zone">
        <div className="titlebar" data-tauri-drag-region>
          <div className="titlebar-left">
            <div className="menu-item">
              <button
                className={`menu-btn ${fileMenuOpen ? 'active' : ''}`}
                onClick={toggleFileMenu}
              >
                ◈ Menu
              </button>
              {fileMenuOpen && (
                <div className="dropdown-content" onClick={(e) => e.stopPropagation()}>
                  <button onClick={handleRefresh}>
                    <span>Refresh Memory</span>
                    <span className="shortcut">F5</span>
                  </button>
                  <button onClick={handleScan}>
                    <span>Check All {status?.databases.length ?? 0} Databases</span>
                  </button>
                  <button onClick={handleImport}>
                    <span>View Activity Log</span>
                  </button>
                  <div className="divider" />
                  <button onClick={handleExit} className="danger-item">
                    <span>Exit</span>
                    <span className="shortcut">Ctrl+Q</span>
                  </button>
                </div>
              )}
            </div>
            <span className="node-tag pulsing-glow">{identity?.hostname ?? 'Discovering machine'}</span>
          </div>

          <div className="titlebar-center" data-tauri-drag-region>
            <span className="live-status-dot" />
            <span className="titlebar-glow">NOUGEN MEMORY HUB</span>
            <span className="version-pill shimmer-pill">LIVE 60 FPS</span>
          </div>

          <div className="titlebar-right">
            <button className="titlebar-btn minimize" onClick={handleMinimize} title="Minimize">
              <svg width="10" height="1" viewBox="0 0 10 1" fill="none"><path d="M0 0.5H10" stroke="currentColor" strokeWidth="1.2"/></svg>
            </button>
            <button className="titlebar-btn maximize" onClick={handleMaximize} title="Maximize">
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><rect x="0.5" y="0.5" width="9" height="9" stroke="currentColor" strokeWidth="1.2"/></svg>
            </button>
            <button className="titlebar-btn close" onClick={handleClose} title="Close">
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M0.5 0.5L9.5 9.5M9.5 0.5L0.5 9.5" stroke="currentColor" strokeWidth="1.2"/></svg>
            </button>
          </div>
        </div>

        {/* Streamlined Main Header */}
        <header className="hud-header-bar">
          <div className="brand">
            <div className="brand-logo-wrap floating-anim">
              <span className="brand-mark">◈</span>
              <div className="brand-pulse-ring" />
            </div>
            <div className="brand-text-block">
              <div className="brand-title-row">
                <h1>NouGen Memory Hub</h1>
                <span className="badge-grid glow-border">{status ? `${status.databases.length}-DB GRID` : 'STORAGE UNKNOWN'}</span>
              </div>
              <p className="tagline">Local Memory & Multi-Machine Coordination</p>
            </div>
          </div>

          <div className="header-right">
            <span className="badge preview-mode glow-teal">
              <span className="dot ok" /> {status ? 'ENGINE RESPONDING' : 'ENGINE UNAVAILABLE'}
            </span>
            <span className="badge live-status glow-teal">
              <span className={`dot ${status ? 'ok' : 'warn'}`} />
              <strong>{status ? totalShards.toLocaleString() : 'Unavailable'}</strong> memories
            </span>
            <div className="node-indicator glow-indigo" title="Current Active Machine">
              <span className="pulse-beacon" />
              <span>{identity?.hostname ?? 'Unknown machine'}</span>
            </div>
          </div>
        </header>

        {/* Navigation Tabs */}
        <nav className="tabs">
          {TABS.map(({ key, label, icon }) => (
            <button
              key={key}
              className={tab === key ? 'tab active tab-glow' : 'tab'}
              onClick={() => setTab(key)}
            >
              <span className="tab-icon bounce-hover">{icon}</span>
              <span className="tab-label">{label}</span>
              {key === 'substrate' && <span className="tab-counter glow-pill">{status?.databases.length ?? 'Unknown'} DBs</span>}
              {key === 'fleet' && <span className="tab-counter node-live">{fleetNodes.length} Machines</span>}
            </button>
          ))}
        </nav>
      </div>

      {/* Main Expansive Center Workspace (Takes all remaining screen height) */}
      <main className="main-content-zone">
        <div className="main-inner-shell">
        {/* Global Error Banner */}
        {error && (
          <div className="error-bar slide-down">
            <span className="error-icon">⚠️</span>
            <span className="error-msg">{error}</span>
            <button className="error-retry" onClick={retry} disabled={busy}>
              Retry Connection
            </button>
          </div>
        )}

        {/* TAB 1: Search Memory */}
        {tab === 'search' && (
          <section className="panel search-panel fade-in">
            <div className="search-box-wrap neon-glow-box">
              <div className="search-row">
                <div className="input-glow-wrap">
                  <span className="search-icon">🔍</span>
                  <input
                    aria-label="Search memories"
                    value={query}
                    placeholder="Search your saved memories (e.g. fleet setup, gemma 4, hardware, notes)..."
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && runSearch()}
                    autoFocus
                  />
                  {query && (
                    <button className="clear-btn" aria-label="Clear search" onClick={() => setQuery('')}>
                      ✕
                    </button>
                  )}
                </div>
                <button className="primary-cyber-btn ripple-btn" onClick={runSearch} disabled={busy}>
                  {busy ? <span className="spinner" /> : '⚡ Search Now'}
                </button>
              </div>

              {/* Quick Topic Buttons */}
              <div className="quick-tags-row">
                <span className="quick-label">Quick Topics:</span>
                {['fleet', 'gemma 4', 'vram', 'desktop app', 'relay', 'hardware', 'apollo'].map((tag) => (
                  <button
                    key={tag}
                    className="tag-pill interactive-pill"
                    onClick={() => {
                      setQuery(tag);
                      setTimeout(() => runSearch(), 50);
                    }}
                  >
                    #{tag}
                  </button>
                ))}
              </div>
            </div>

            {results.length > 0 && (
              <div className="filter-row">
                <div className="partition-chips">
                  <button
                    className={partition === ALL_PARTITIONS ? 'chip active' : 'chip'}
                    onClick={() => setPartition(ALL_PARTITIONS)}
                  >
                    All Databases ({results.length})
                  </button>
                  {hitPartitions.map((idx) => (
                    <button
                      key={idx}
                      className={partition === idx ? 'chip active' : 'chip'}
                      onClick={() => setPartition(idx)}
                    >
                      Database #{idx}
                      {idx === activeDb ? ' ⭐' : ''}
                    </button>
                  ))}
                </div>
                <span className="result-count">
                  Showing <strong>{visibleResults.length}</strong> of {results.length} memories
                </span>
              </div>
            )}

            {/* Results Grid - Fully Visible & Scrollable */}
            <div className="results-grid">
              {visibleResults.length === 0 && !busy && (
                <div className="empty-state floating-empty">
                  <span className="empty-icon bounce-icon">📁</span>
                  <h3>No matching memories found</h3>
                  <p>Try searching another keyword or select "All Databases".</p>
                </div>
              )}

              {visibleResults.map((s, idx) => (
                <article
                  key={`${s._db_index}-${s.id}`}
                  style={{ animationDelay: `${idx * 0.05}s` }}
                  className={`shard-card card-lift ${selectedShard?.id === s.id ? 'selected' : ''}`}
                >
                  <div className="shard-head">
                    <div className="shard-title-wrap">
                      <span className="db-badge">Database #{s._db_index ?? 'Unknown'}</span>
                      <h3>{s.title}</h3>
                    </div>
                    <div className="shard-actions">
                      <button className="copy-btn" onClick={() => setSelectedShard(s)}>
                        Inspect
                      </button>
                      <button
                        className={`copy-btn ${copiedId === s.id ? 'copied' : ''}`}
                        onClick={(e) => copyShardText(s, e)}
                        title="Copy Memory Text"
                      >
                        {copiedId === s.id ? '✓ Copied' : '📋 Copy'}
                      </button>
                    </div>
                  </div>

                  <p className="shard-body">
                    {s.content.length > 600 ? `${s.content.replace(/\s+/g, ' ').slice(0, 360).trimEnd()}…` : s.content}
                  </p>
                  {s.content.length > 600 && (
                    <details className="memory-disclosure">
                      <summary>Read full memory ({s.content.length.toLocaleString()} characters)</summary>
                      <p className="shard-body">{s.content}</p>
                    </details>
                  )}

                  <div className="shard-footer">
                    <div className="score-bars-wrap">
                      <div className="score-track">
                        <div
                          className="score-fill animated-shimmer"
                          style={{ width: `${((s.final_score ?? 0) / maxScore) * 100}%` }}
                        />
                      </div>
                      <div className="score-labels">
                        <span>Match: <strong>{s.final_score == null ? 'Not scored' : `${Math.round(s.final_score * 100)}%`}</strong></span>
                        {s.timestamp && <span>Saved: <strong>{formatEasternTime(s.timestamp)}</strong></span>}
                      </div>
                    </div>
                    <span className="shard-id-tag">Memory #{s.id}</span>
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}

        {/* TAB 2: Memory Storage (9 DBs) */}
        {tab === 'substrate' && (
          <section className="panel fade-in">
            <div className="panel-intro-card neon-box">
              <div className="intro-text">
                <h2>Memory Storage ({status?.databases.length ?? 'Unknown'} Database Partitions)</h2>
                <p>
                  Saved securely on this computer at{' '}
                  <code>{identity?.vault_path ?? 'Unknown vault path'}</code>. Automatically rolls to the next partition as storage expands.
                </p>
              </div>
              <button className="primary-cyber-btn mini ripple-btn" onClick={refreshStatus}>
                🔄 Refresh Storage
              </button>
            </div>

            <div className="substrate-grid-9">
              {partitionIndices.map((idx) => {
                const db = status?.databases?.find((d) => d.index === idx);
                const sizeMb = db ? db.size_mb : 0;
                const shardsCount = db ? db.shards : 0;
                const pct = Math.min(100, (sizeMb / (status?.partition_cap_mb ?? Infinity)) * 100);
                const isActive = idx === activeDb;

                return (
                  <div
                    key={idx}
                    className={`matrix-cell card-lift ${db ? 'live' : 'empty'} ${isActive ? 'active-write wave-glow' : ''}`}
                    onClick={() => {
                      setPartition(idx);
                      setTab('search');
                    }}
                    title={`Click to view memories in Database #${idx}`}
                  >
                    <div className="cell-top">
                      <span className="cell-num">Database #{idx}</span>
                      {isActive && <span className="live-write-pill pulsing-pill">● DEFAULT ROUTE</span>}
                    </div>

                    <div className="cell-main-stat">
                      <span className="cell-shard-val">{shardsCount == null ? 'Unavailable' : shardsCount.toLocaleString()}</span>
                      <span className="cell-shard-lbl">memories</span>
                    </div>

                    <div className="cell-storage">
                      <span>{sizeMb.toFixed(1)} MB</span>
                      <span className="cap-pct">{pct.toFixed(0)}% used</span>
                    </div>

                    <div className="cap-gauge-track">
                      <div
                        className={`cap-gauge-fill animated-shimmer ${pct > 80 ? 'warn' : ''}`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* TAB 3: Your Machines */}
        {tab === 'fleet' && (
          <section className="panel fade-in">
            <div className="panel-intro-card neon-box">
              <div className="intro-text">
                <h2>💻 Your Active Fleet Machines</h2>
                <p>Registry and live probes for {fleetNodes.length} discovered machines. Missing readings are unavailable.</p>
              </div>
            </div>

            <div className="fleet-node-grid">
              {fleetNodes.map((node) => (
                <div key={node.name} className={`fleet-card card-lift ${node.status}`}>
                  <div className="fleet-card-header">
                    <div>
                      <span className="fleet-station">{node.host ?? 'Unavailable'}</span>
                      <h3>{node.name}</h3>
                    </div>
                    <span className={`fleet-badge ${node.status}`}>
                      {node.is_local ? '● THIS MACHINE' : node.status.toUpperCase()}
                    </span>
                  </div>

                  <div className="fleet-roles">
                    <div className="role-item">
                      <span className="role-lbl">Agent Lead</span>
                      <span className="role-val">{node.coach ?? 'Unavailable'}</span>
                    </div>
                    <div className="role-item">
                      <span className="role-lbl">Model on Duty</span>
                      <span className="role-val accent">{node.player ?? 'Unavailable'}</span>
                    </div>
                  </div>

                  <div className="fleet-hardware-box">
                    <div className="hw-row">
                      <span className="hw-lbl">Role:</span>
                      <span className="hw-val">{node.role ?? 'Unavailable'}</span>
                    </div>
                    <div className="hw-row">
                      <span className="hw-lbl">Graphics / GPU:</span>
                      <span className="hw-val">{node.gpu ?? 'Unavailable'}</span>
                    </div>
                    <div className="hw-row">
                      <span className="hw-lbl">Memory (RAM):</span>
                      <span className="hw-val">{node.ram ?? 'Unavailable'}</span>
                    </div>
                    <div className="hw-row">
                      <span className="hw-lbl">Local IP:</span>
                      <span className="hw-val mono">{node.ip ?? 'Unavailable'}</span>
                    </div>
                    <div className="hw-row">
                      <span className="hw-lbl">Temp / Heartbeat:</span>
                      <span className="hw-val glow-text">{node.temperature ?? 'Unavailable'} · {node.health_status ?? 'Unprobed'}</span>
                    </div>
                  </div>

                  <div className="vram-section">
                    <div className="vram-header">
                      <span>GPU Memory Used</span>
                      <span>{node.vram_used_pct == null ? 'Unavailable' : `${node.vram_used_pct}%`}</span>
                    </div>
                    <div className="vram-track">
                      <div className="vram-fill animated-shimmer" style={{ width: `${node.vram_used_pct ?? 0}%` }} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {tab === "tracker" && !usage?.ledger_present && <p className="panel">No published usage records are available for this scope and period.</p>}
        {/* TAB 4: Token & Cost Meter */}
        {tab === 'tracker' && (
          <section className="panel fade-in">
            <div className="tracker-header-strip">
              <div>
                <div className="tracker-title-row">
                  <h2>⚡ Fleet Token & Cold-Boot Cost Meter</h2>
                  <div className="scope-switch-group">
                    <button
                      className={machineScope === 'local' ? 'scope-chip active' : 'scope-chip'}
                      onClick={() => setMachineScope('local')}
                    >
                      💻 This machine: {identity?.hostname ?? "Unknown"}
                    </button>
                    <button
                      className={machineScope === 'fleet' ? 'scope-chip active' : 'scope-chip'}
                      onClick={() => setMachineScope('fleet')}
                    >
                      🛰️ Published fleet usage
                    </button>
                  </div>
                </div>
                <p>
                  {machineScope === 'local' ? identity?.hostname ?? 'Unknown machine' : `${fleetNodes.length} registered fleet machines`} · {' '}
                  {usagePeriod === '24h' && 'Past 24 Hours of Activity'}
                  {usagePeriod === 'week' && 'Past 7 Days (Weekly Rolling)'}
                  {usagePeriod === 'month' && 'Past 30 Days (Monthly Rolling)'}
                  {usagePeriod === 'quarter' && 'Past 90 Days (Quarterly Rolling)'}
                  {usagePeriod === 'year' && 'Past 365 Days (Annual Rolling)'}
                  {usagePeriod === 'all' && 'All-Time Recorded History'}
                </p>
              </div>
              <div className="period-segmented-group">
                {['24h', 'week', 'month', 'quarter', 'year', 'all'].map((p) => (
                  <button
                    key={p}
                    className={usagePeriod === p ? 'period-chip active' : 'period-chip'}
                    onClick={() => setUsagePeriod(p)}
                  >
                    {p === '24h' ? 'Past 24h' : p === 'all' ? 'All Time' : p.charAt(0).toUpperCase() + p.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            {usage?.ledger_present && <>
            <div className="tile-grid human-grid">
              <div className="tile neon-border card-lift">
                <span className="tile-label">Total Volume Processed</span>
                <div className="tile-primary-metric">
                  <span className="tile-hero-val accent">
                    {formatCompactNumber(usage?.total_tokens ?? 0)}
                  </span>
                  <span className="tile-hero-unit">tokens</span>
                </div>
                <span className="tile-sub">
                  {(usage?.total_tokens ?? 0).toLocaleString()} published tokens · {(usage?.invocations ?? 0).toLocaleString()} calls
                </span>
              </div>

              <div className="tile neon-border card-lift">
                <span className="tile-label">Context Reused (Cache)</span>
                <div className="tile-primary-metric">
                  <span className="tile-hero-val accent-cyan">
                    {usage?.cache_hit_rate == null ? 'Unavailable' : `${usage.cache_hit_rate.toFixed(1)}%`}
                  </span>
                  <span className="tile-hero-unit">hot context</span>
                </div>
                <span className="tile-sub">
                  {formatCompactNumber(usage?.cached_tokens ?? 0)} reported cached-input tokens
                </span>
              </div>

              <div className="tile neon-border card-lift gold-border">
                <span className="tile-label">Cold Turkey Sticker Price</span>
                <div className="tile-primary-metric">
                  <span className="tile-hero-val accent-gold">
                    {usage?.estimated_cost == null ? 'Unavailable' : `$${usage.estimated_cost.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`}
                  </span>
                </div>
                <span className="tile-sub">No recorded price is substituted with a guess</span>
              </div>

              <div className="tile neon-border card-lift green-border">
                <span className="tile-label">Recorded Local Share</span>
                <div className="tile-primary-metric">
                  <span className="tile-hero-val accent-green glow-green">
                    {usage?.free_share == null ? 'Unavailable' : `${usage.free_share.toFixed(1)}%`}
                  </span>
                  <span className="tile-hero-unit">on-device</span>
                </div>
                <span className="tile-sub">Share requires published execution-source records</span>
              </div>
            </div>

            {/* Human-Readable Model Breakdown Table */}
            <div className="human-ledger-table-card">
              <div className="human-ledger-header">
                <div className="col-model">MODEL & INFRASTRUCTURE</div>
                <div className="col-stat text-right">TOKENS RUN</div>
                <div className="col-stat text-right">REQUESTS</div>
                <div className="col-cost text-right">COLD TURKEY PRICE</div>
              </div>

              <div className="human-ledger-body">
                {(usage?.by_model ?? []).map((m) => {
                  const meta = getModelDisplayMeta(m.model, m.provider);
                  return (
                    <div key={`${m.provider}/${m.model}`} className="human-ledger-row row-hover">
                      <div className="col-model">
                        <div className="model-avatar-box">
                          <span className="avatar-symbol">{meta.icon}</span>
                        </div>
                        <div className="model-text-stack">
                          <div className="model-main-line">
                            <span className="model-name-text">{meta.title}</span>
                            <span className={`model-tier-pill ${meta.isLocal ? 'local-tier' : 'cloud-tier'}`}>
                              {meta.tier}
                            </span>
                          </div>
                          <span className="model-sub-text">{meta.badge}</span>
                        </div>
                      </div>

                      <div className="col-stat text-right">
                        <span className="stat-highlight">{formatCompactNumber(m.total_tokens)}</span>
                        <span className="stat-exact-sub">{m.total_tokens.toLocaleString()}</span>
                      </div>

                      <div className="col-stat text-right">
                        <span className="stat-highlight">{m.invocations == null ? 'Unavailable' : m.invocations.toLocaleString()}</span>
                        <span className="stat-exact-sub">invocations</span>
                      </div>

                      <div className="col-cost text-right">
                        {meta.isLocal ? (
                          <span className="badge-free-gpu glow-green">Price unavailable</span>
                        ) : (
                          <span className="cold-cost-text">
                            {m.estimated_cost == null ? 'Unavailable' : `$${m.estimated_cost.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
            </>}
          </section>
        )}

        {/* TAB 5: Team Handoffs */}
        {tab === 'relay' && (
          <section className="panel fade-in">
            <div className="panel-intro-card neon-box">
              <div className="intro-text">
                <h2>🤝 Cross-Machine Handoffs & Updates</h2>
                <p>Recent task logs and handoffs across your computers so work stays in sync.</p>
              </div>
              <button className="primary-cyber-btn mini ripple-btn" onClick={loadRelay} disabled={busy}>
                🔄 Refresh Handoffs
              </button>
            </div>

            <div className="relay-feed-grid">
              {relay.map((h, idx) => (
                <article
                  key={h.id}
                  style={{ animationDelay: `${idx * 0.08}s` }}
                  className={`relay-card-pro card-lift ${h.live_status}`}
                >
                  <div className="relay-pro-head">
                    <div className="agent-badge-wrap">
                      <span className="agent-name">{(h.agent ?? 'Unknown agent').toUpperCase()}</span>
                      <span className="machine-tag">on {h.machine}</span>
                    </div>
                    <span className={`status-pill ${h.live_status}`}>
                      ● {h.live_status.toUpperCase()}
                      {h.acknowledged_by && ` (Seen by ${h.acknowledged_by})`}
                    </span>
                  </div>

                  <p className="relay-goal-text">{h.goal}</p>

                  <div className="relay-footer-meta">
                    {h.branch && <span className="branch-pill">Branch: {h.branch}</span>}
                    <span>🕒 {formatEasternTime(h.timestamp)}</span>
                    {h.tasks_total > 0 && (
                      <span className="tasks-stat glow-green">
                        ✅ {h.tasks_done} of {h.tasks_total} Tasks Done
                      </span>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}

        {/* TAB 6: Growth Stats */}
        {tab === 'stats' && (
          <section className="panel fade-in">
            <div className="period-row">
              {['24h', 'week', 'month', 'quarter', 'year'].map((p) => (
                <button
                  key={p}
                  className={period === p ? 'chip active' : 'chip'}
                  onClick={() => setPeriod(p)}
                >
                  {p === '24h' ? 'Past 24 Hours' : `This ${p.charAt(0).toUpperCase() + p.slice(1)}`}
                </button>
              ))}
            </div>

            <div className="tile-grid">
              <div className="tile card-lift">
                <span className="tile-label">New Memories Saved</span>
                <span className="tile-value accent">{stats ? growth.new_shards.toLocaleString() : 'Unavailable'}</span>
                <span className="tile-sub">in the selected period</span>
              </div>
              <div className="tile card-lift">
                <span className="tile-label">Total Memory Bank</span>
                <span className="tile-value">{stats ? growth.total_shards.toLocaleString() : 'Unavailable'}</span>
                <span className="tile-sub">total memories stored</span>
              </div>
              <div className="tile card-lift">
                <span className="tile-label">Helpfulness Gain</span>
                <span className={`tile-value ${utilityDelta >= 0 ? 'accent-green glow-green' : 'warn'}`}>
                  {stats?.utility_delta == null ? 'Unavailable' : `${utilityDelta >= 0 ? '+' : ''}${utilityDelta.toFixed(2)}`}
                </span>
                <span className="tile-sub">memory quality drift</span>
              </div>
              <div className="tile card-lift">
                <span className="tile-label">Growth Rate</span>
                <span className="tile-value">{stats ? `${accelerationRate.toFixed(1)}%` : 'Unavailable'}</span>
                <span className="tile-sub">expansion speed</span>
              </div>
            </div>

            <details className="raw-json-box">
              <summary>View Technical Data</summary>
              <pre className="stats-code-block">{JSON.stringify(stats ?? { available: false }, null, 2)}</pre>
            </details>
          </section>
        )}

        {/* Shard Detail Modal */}
        {selectedShard && (
            <dialog ref={memoryDialog} className="shard-modal pop-in" aria-labelledby="memory-dialog-title" onCancel={() => setSelectedShard(null)}>
              <div className="modal-header">
                <div>
                  <span className="db-badge">DATABASE #{selectedShard._db_index ?? 'Unknown'}</span>
                  <h2 id="memory-dialog-title">{selectedShard.title}</h2>
                </div>
                <button className="modal-close-btn" aria-label="Close memory" onClick={() => setSelectedShard(null)}>
                  ✕
                </button>
              </div>

              <div className="modal-body">
                <div className="modal-meta-bar">
                  <span>Memory ID: <strong>#{selectedShard.id}</strong></span>
                  <span>Match Rating: <strong>{selectedShard.final_score == null ? 'Not scored' : `${Math.round(selectedShard.final_score * 100)}%`}</strong></span>
                  {selectedShard.timestamp && <span>Saved: <strong>{formatEasternTime(selectedShard.timestamp)}</strong></span>}
                </div>

                <div className="modal-content-box">
                  <pre>{selectedShard.content}</pre>
                </div>
              </div>

              <div className="modal-footer">
                <button
                  className="primary-cyber-btn mini ripple-btn"
                  onClick={(e) => copyShardText(selectedShard, e)}
                >
                  {copiedId === selectedShard.id ? '✓ Copied to Clipboard' : '📋 Copy Memory'}
                </button>
                <button className="ghost-btn mini" onClick={() => setSelectedShard(null)}>
                  Close
                </button>
              </div>
            </dialog>
        )}
        </div>
      </main>

      {/* Sleek Docked Bottom Footer - Always Visible, Zero Content Interference */}
      <footer className="hud-footer-dock">
        <div className="footer-dock-left">
          <div className="dock-item">
            <span className="dock-icon">💾</span>
            <code className="dock-code">{identity?.vault_path ?? 'Unknown vault path'}</code>
            <span className="dock-tag">{status?.databases.length ?? 'Unknown'} DBs</span>
          </div>
          <span className="dock-sep">·</span>
          <div className="fleet-pings-dock">{fleetNodes.map(node => <span key={node.name} className={`ping-pill ${node.is_local ? 'active-pill' : ''}`}>{node.name} · {node.status}</span>)}</div>
        </div>

        <div className="footer-dock-center">
          <div className="live-clock-dock">
            <span className="clock-pulse-dot" />
            <span className="clock-val">{clockEastern}</span>
          </div>
        </div>

        <div className="footer-dock-right">
          <div className="hotkeys-dock">
            <span><kbd>Ctrl</kbd>+<kbd>F</kbd> Search</span>
            <span><kbd>F5</kbd> Refresh</span>
            <span><kbd>Ctrl</kbd>+<kbd>Q</kbd> Exit</span>
          </div>
          <span className="dock-sep">·</span>
          <span className="brand-copyright">Who Visions LLC</span>
        </div>
      </footer>
    </div>
  );
}
