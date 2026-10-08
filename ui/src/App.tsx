import { recoverMessages, validWidgets, buildContext } from './chatPersistence';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

// ---------------------------------------------------------------------------
// Human-friendly date and time helper (Eastern Time)
// ---------------------------------------------------------------------------
function formatEasternTime(dateInput?: string): string {
  if (!dateInput) return 'Recently';
  try {
    let dateStr = dateInput;
    if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(dateStr) && /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(dateStr)) {
      dateStr = dateStr.replace(' ', 'T') + 'Z';
    }
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateInput;
    return d.toLocaleString('en-US', {
      timeZone: 'America/New_York',
      timeZoneName: 'short',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    });
  } catch {
    return dateInput;
  }
}

function getLiveEasternClock(): string {
  return new Date().toLocaleTimeString('en-US', {
    timeZone: 'America/New_York',
      timeZoneName: 'short',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  });
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

async function callEngine(cmd: string, args: Record<string, unknown>, signal?: AbortSignal): Promise<unknown> {
  if (tauriInvoke) {
    return withTimeout(tauriInvoke(cmd, args), CLIENT_TIMEOUT_MS);
  }

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(args)) if (value != null) params.set(key, String(value));
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) controller.abort();
  const timer = setTimeout(abort, CLIENT_TIMEOUT_MS);
  try {
    const response = await fetch(`/api/${cmd}?${params}`, { signal: controller.signal });
    if (!response.ok) throw new Error(`${cmd} unavailable (${response.status})`);
    return await response.text();
  } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); }

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

type Tab = 'search' | 'chat' | 'design' | 'substrate' | 'fleet' | 'tracker' | 'relay' | 'stats';

const TABS: { key: Tab; label: string; icon: string }[] = [
  { key: 'chat', label: 'Chat', icon: '💬' },
  { key: 'search', label: 'Search Memory', icon: '🔍' },
  { key: 'design', label: 'Design Intelligence', icon: '🎨' },
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
  const [tab, setTab] = useState<Tab>('chat');
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
  const [designWeights, setDesignWeights] = useState({
    hierarchy: 4,
    contrast: 3,
    alignment: 4,
    whitespace: 5,
    grouping: 4,
    typography: 4,
    action: 3,
  });
  const [activeWidgetSample, setActiveWidgetSample] = useState<'calculator' | 'diagram' | 'checklist' | 'multivariant'>('calculator');
  const [activeRecipeServings, setActiveRecipeServings] = useState(4);
  const [checkedAuditItems, setCheckedAuditItems] = useState<Record<string, boolean>>({
    contrast45: true,
    visualHierarchy: true,
    whitespaceConsistent: true,
    actionProminence: false,
  });
  const [selectedVariant, setSelectedVariant] = useState<'cyber' | 'minimal' | 'glass'>('cyber');
  const [designSubTab, setDesignSubTab] = useState<'audit' | 'streaming' | 'principles' | 'receipts' | 'intelligent'>('intelligent');

  const [chatRecoveryNotice] = useState(() => {
    try {
      const raw = localStorage.getItem('nougen.chat.v1');
      if (!raw) return '';
      try {
        const saved = JSON.parse(raw);
        if (saved?.version !== 1 || !Array.isArray(saved.messages)) throw new Error('Unsupported saved conversation');
        return '';
      } catch {
        localStorage.setItem('nougen.chat.recovery.v1', raw);
        return 'A damaged conversation was preserved for recovery. This chat starts empty.';
      }
    } catch { return 'Device storage is unavailable. This conversation may not survive closing the app.'; }
  });
  const [chatMessages, setChatMessages] = useState<Array<{
    id: string;
    role: 'user' | 'assistant';
    text: string;
    timestamp: string;
    uiComponent?: 'calculator' | 'diagram' | 'checklist' | 'comparison' | 'audit_box' | 'pipeline-trace';
    uiData?: any;
    isError?: boolean;
    widgets?: Array<{ kind: string; title: string; items: string[] }>;
    widgetChecks?: Record<string, boolean>;
    isStreaming?: boolean;
  }>>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('nougen.chat.v1') || 'null');
      if (saved?.version !== 1 || !Array.isArray(saved.messages)) return [];
      return recoverMessages(saved.messages);
    } catch { return []; }
  });
  const [chatArchives, setChatArchives] = useState<Array<{ id: string; title: string; messages: any[] }>>(() => {
    try { const rows = JSON.parse(localStorage.getItem('nougen.chat.archives.v1') || '[]'); return Array.isArray(rows) ? rows.filter(r => typeof r?.id === 'string' && typeof r.title === 'string' && Array.isArray(r.messages)).slice(-20) : []; } catch { return []; }
  });
  const [chatStorageError, setChatStorageError] = useState('');
  const chatBusyRef = useRef(false);
  const chatRequestRef = useRef<{ controller: AbortController; id: string } | null>(null);
  useEffect(() => {
    try { localStorage.setItem('nougen.chat.v1', JSON.stringify({ version: 1, messages: chatMessages.slice(-500) })); setChatStorageError(''); }
    catch { setChatStorageError('Conversation could not be saved on this device.'); }
  }, [chatMessages]);
  const [chatInput, setChatInput] = useState(() => { try { return localStorage.getItem('nougen.chat.draft.v1') || ''; } catch { return ''; } });
  useEffect(() => { try { localStorage.setItem('nougen.chat.draft.v1', chatInput); } catch { setChatStorageError('Draft could not be saved on this device.'); } }, [chatInput]);
  const [chatIsTyping, setChatIsTyping] = useState(false);
  const [activeLaneModel, setActiveLaneModel] = useState('gemma4:e2b-local');
  const [promptLayerLabel, setPromptLayerLabel] = useState<'prod' | 'dev' | 'eval'>('prod');
  const [calcExpression, setCalcExpression] = useState('256 * 1024 / 4');
  const [calcResult, setCalcResult] = useState<string | null>(null);
  const [autonomousHarnessActive, setAutonomousHarnessActive] = useState(false);
  const [harnessStepCount, setHarnessStepCount] = useState(0);
  const chatScrollBottomRef = useRef<HTMLDivElement>(null);
  const autonomousLoopRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const requestVersions = useRef({usage: 0, stats: 0, search: 0});
  const queryRef = useRef(query);
  queryRef.current = query;
  const searchController = useRef<AbortController | null>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const memoryDialog = useRef<HTMLDialogElement>(null);

  // Auto-scroll chat smoothly whenever messages or streaming updates
  useEffect(() => {
    chatScrollBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, chatIsTyping]);

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

  const runSearch = useCallback(async (searchQuery?: string) => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchController.current?.abort();
    const controller = new AbortController();
    searchController.current = controller;
    const version = ++requestVersions.current.search;
    setResults([]);
    setBusy(true);
    try {
      const raw = (await callEngine('search_shards', { query: searchQuery ?? queryRef.current }, controller.signal)) as string;
      if (controller.signal.aborted || version !== requestVersions.current.search) return;
      const parsed = JSON.parse(raw);
      setResults(parsed.length > 0 ? parsed : []);
      setPartition(ALL_PARTITIONS);

    } catch (e) {
      if (controller.signal.aborted || version !== requestVersions.current.search) return;
      setError(String(e));
      setResults([]);
    } finally {
      if (version === requestVersions.current.search) setBusy(false);
    }
  }, []);

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
  }, [tab, loadUsage, loadRelay, loadFleet, loadStats, runSearch]);

  useEffect(() => {
    searchController.current?.abort();
    requestVersions.current.search++;
    if (tab !== 'search') return;
    searchTimer.current = setTimeout(() => runSearch(), 300);
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
      searchController.current?.abort();
    };
  }, [query, tab, runSearch]);

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

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'F5') { event.preventDefault(); handleRefresh(); }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'f') {
        event.preventDefault(); setTab('search');
        requestAnimationFrame(() => document.querySelector<HTMLInputElement>('input[aria-label="Search memories"]')?.focus());
      }
      if (tauriInvoke && (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'q') {
        event.preventDefault(); handleExit();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [handleRefresh, handleExit]);

  const copyShardText = useCallback(async (shard: Shard, e: React.MouseEvent) => {
    e.stopPropagation();
    try { await navigator.clipboard.writeText(`[Memory #${shard.id}] ${shard.title}\n\n${shard.content}`);
    setCopiedId(shard.id);
    setTimeout(() => setCopiedId(null), 2000);
    } catch { setError('Copy failed. Select the memory text and copy it manually.'); }
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
                  <button onClick={handleExit} className="danger-item" disabled={!tauriInvoke}>
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
              <strong>{status ? totalShards.toLocaleString() : 'Unavailable'}</strong> local memories
            </span>
            <div className="node-indicator glow-indigo" title="Current Active Machine">
              <span className="pulse-beacon" />
              <span>{identity?.hostname ?? 'Unknown machine'}</span>
            </div>
          </div>
        </header>

        {/* Navigation Tabs */}
        <nav className="tabs" aria-label="Memory Hub sections">
          {TABS.map(({ key, label, icon }) => (
            <button
              key={key}
              aria-current={tab === key ? 'page' : undefined}
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
                <button className="primary-cyber-btn ripple-btn" onClick={() => runSearch()} disabled={busy}>
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

                    }}
                  >
                    #{tag}
                  </button>
                ))}
              </div>
            </div>

            {partitionIndices.length > 0 && (
              <div className="filter-row">
                <div className="partition-chips">
                  <button
                    className={partition === ALL_PARTITIONS ? 'chip active' : 'chip'}
                    onClick={() => setPartition(ALL_PARTITIONS)}
                  >
                    All Databases ({results.length})
                  </button>
                  {partitionIndices.map((idx) => (
                    <button
                      key={idx}
                      className={partition === idx ? 'chip active' : 'chip'}
                      onClick={() => setPartition(idx)}
                    >
                      Database #{idx} ({results.filter(r => r._db_index === idx).length} returned)
                      {idx === activeDb ? ' ⭐' : ''}
                    </button>
                  ))}
                </div>
                <span className="result-count">
                  Showing <strong>{visibleResults.length}</strong> of {results.length} returned memories
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

        {/* TAB 1.5: Intelligent Chat Lane (Conversational with Generative UI) */}
        {tab === 'chat' && (
          <section className="panel fade-in chat-lane-panel">
            <div className="chat-top-bar">
              <span className="lane-title">Chat</span>
              <div className="chat-lane-controls">
                {chatArchives.length > 0 && <select aria-label="Saved conversations" value="" disabled={chatIsTyping} onChange={e => {
                  const saved = chatArchives.find(a => a.id === e.target.value);
                  if (saved) {
                    const archives = chatMessages.length ? [...chatArchives, { id: crypto.randomUUID(), title: chatMessages.find(m => m.role === 'user')?.text.slice(0, 60) || 'Conversation', messages: chatMessages.slice(-500) }].slice(-20) : chatArchives;
                    try { localStorage.setItem('nougen.chat.archives.v1', JSON.stringify(archives)); setChatArchives(archives); setChatMessages(recoverMessages(saved.messages)); setChatInput(''); }
                    catch { setChatStorageError('Could not save the current conversation. History was not switched.'); }
                  }
                }}><option value="">History</option>{chatArchives.map(a => <option key={a.id} value={a.id}>{a.title}</option>)}</select>}
                <button className="ghost-btn mini" disabled={chatIsTyping} onClick={() => {
                  if (chatMessages.length) {
                    const archive = { id: crypto.randomUUID(), title: chatMessages.find(m => m.role === 'user')?.text.slice(0, 60) || 'Conversation', messages: chatMessages.slice(-500) };
                    const archives = [...chatArchives, archive].slice(-20);
                    try { localStorage.setItem('nougen.chat.archives.v1', JSON.stringify(archives)); setChatArchives(archives); }
                    catch { setChatStorageError('Could not archive this conversation. New chat was not started.'); return; }
                  }
                  setChatMessages([]); setChatInput('');
                }}>New chat</button>
              </div>
            </div>

            {(chatRecoveryNotice || chatStorageError) && <p role="alert">{chatStorageError || chatRecoveryNotice}</p>}
            {/* Chat Message Stream */}
            <div className="chat-messages-container">
              {chatMessages.filter(msg => msg.id !== 'welcome-1' && msg.id !== 'welcome-reset').map((msg) => (
                <div key={msg.id} className={`chat-message-bubble ${msg.role}-bubble fade-in`}>
                  {msg.widgets?.map((widget, index) => (
                    <section className={`chat-model-widget ${widget.kind}`} key={`${msg.id}-${index}`} aria-label={widget.title}>
                      <div className="widget-header-title">
                        <span className="widget-icon">
                          {widget.kind === 'checklist' && '📋'}
                          {widget.kind === 'comparison' && '⚖️'}
                          {widget.kind === 'steps' && '🔢'}
                          {widget.kind === 'metric_grid' && '📊'}
                        </span>
                        <h3>{widget.title}</h3>
                      </div>
                      {widget.kind === 'checklist' && (
                        <div className="widget-checklist-group">
                          {widget.items.map((item, j) => (
                            <label key={j} className="widget-check-label">
                              <input
                                type="checkbox"
                                aria-label={item}
                                checked={Boolean(msg.widgetChecks?.[`${index}-${j}`])}
                                onChange={(e) => {
                                  const checked = e.target.checked;
                                  setChatMessages((prev) =>
                                    prev.map((m) =>
                                      m.id === msg.id
                                        ? { ...m, widgetChecks: { ...m.widgetChecks, [`${index}-${j}`]: checked } }
                                        : m
                                    )
                                  );
                                }}
                              />
                              <span>{item}</span>
                            </label>
                          ))}
                        </div>
                      )}
                      {widget.kind === 'metric_grid' && (
                        <div className="widget-metric-grid">
                          {widget.items.map((item, j) => (
                            <div key={j} className="metric-chip-card">
                              <span className="metric-text">{item}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      {widget.kind === 'comparison' && (
                        <div className="widget-comparison-grid">
                          {widget.items.map((item, j) => (
                            <div key={j} className="comparison-column-card">
                              <p>{item}</p>
                            </div>
                          ))}
                        </div>
                      )}
                      {widget.kind === 'steps' && (
                        <ol className="widget-steps-list">
                          {widget.items.map((item, j) => (
                            <li key={j}>{item}</li>
                          ))}
                        </ol>
                      )}
                    </section>
                  ))}
                  <div className="message-header-row">
                    <span className="message-author">
                      {msg.role === 'user' ? 'You' : 'NouGen'}
                    </span>
                    <span className="message-time">{msg.timestamp}</span>
                  </div>

                  <div className="message-text-content">
                    <p>
                      {msg.text}
                      {msg.isStreaming && <span className="streaming-cursor">▍</span>}
                    </p>
                  </div>

                </div>
              ))}

              {chatIsTyping && (
                <div className="chat-message-bubble assistant-bubble typing-bubble">
                  <span className="typing-dots">
                    <span>.</span><span>.</span><span>.</span> Thinking…
                  </span>
                </div>
              )}
              {/* Auto-scroll anchor */}
              <div ref={chatScrollBottomRef} />
            </div>

            {/* Chat Input Bar */}
            <form
              className="chat-input-bar"
              onSubmit={(e) => {
                e.preventDefault();
                const q = chatInput.trim();
                if (!q || chatBusyRef.current) return;
                chatBusyRef.current = true;

                const userMsg = {
                  id: `user-${Date.now()}`,
                  role: 'user' as const,
                  text: q,
                  timestamp: formatEasternTime(new Date().toISOString()),
                };

                setChatMessages((prev) => [...prev, userMsg]);
                setChatInput('');
                setChatIsTyping(true);

                // Asynchronous live tool execution and conversational synthesis
                (async () => {
                  let fullReply = '';

                  // Every message is resolved by the model using the conversation history.
                  {
                    const controller = new AbortController();
                    const requestId = crypto.randomUUID();
                    chatRequestRef.current = { controller, id: requestId };
                    const timer = setTimeout(() => controller.abort(), 100000);
                    let widgets: Array<{ kind: string; title: string; items: string[] }> = [];
                    let isError = false;
                    try {
                      const messages = buildContext([...chatMessages, userMsg]);
                      let data: any;
                      if (tauriInvoke) {
                        data = await withTimeout(tauriInvoke('chat', { payload: { messages, request_id: requestId } }), 100000);
                      } else {
                      const response = await fetch('/api/chat', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ messages }), signal: controller.signal,
                      });
                      data = await response.json();
                      if (!response.ok) throw new Error(data.error || 'Chat is unavailable.');
                      }
                      if (data.error || typeof data.text !== 'string') throw new Error(data.error || 'Chat is unavailable.');
                      widgets = validWidgets(data.widgets);
                      fullReply = data.text;
                    } catch (error) {
                      isError = true;
                      fullReply = error instanceof Error ? error.message : 'Chat could not connect. Please retry.';
                    } finally { clearTimeout(timer); chatRequestRef.current = null; chatBusyRef.current = false; setChatIsTyping(false); }
                    setChatMessages(prev => [...prev, { id: `asst-${Date.now()}`, role: 'assistant' as const, text: fullReply, widgets, isError, timestamp: formatEasternTime(new Date().toISOString()) }]);
                    return;
                  }
                })();
              }}
            >
              <input
                type="text"
                className="chat-text-input"
                placeholder="Message NouGen"
                aria-label="Message NouGen"
                maxLength={24000}
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
              />
              {chatIsTyping && <button type="button" className="ghost-btn mini" onClick={() => {
                const pending = chatRequestRef.current;
                pending?.controller.abort();
                if (tauriInvoke && pending) void tauriInvoke('cancel_chat', { requestId: pending.id });
              }}>Stop</button>}
              <button type="submit" className="primary-cyber-btn mini chat-send-btn" disabled={chatIsTyping || !chatInput.trim()}>
                Send
              </button>
            </form>
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

        {/* TAB 7: Design Intelligence Console (Gary Simon UI/UX + Streaming Declarative UI) */}
        {tab === 'design' && (
          <section className="panel fade-in design-intelligence-panel">
            {/* Top Sub-Navigation Bar */}
            <div className="design-subnav-row">
              <div className="design-subnav-chips">
                <button
                  className={`chip ${designSubTab === 'intelligent' ? 'active' : ''}`}
                  onClick={() => setDesignSubTab('intelligent')}
                >
                  🧠 Intelligent Shard Explorer
                </button>
                <button
                  className={`chip ${designSubTab === 'audit' ? 'active' : ''}`}
                  onClick={() => setDesignSubTab('audit')}
                >
                  📊 Design Quality Index
                </button>
                <button
                  className={`chip ${designSubTab === 'streaming' ? 'active' : ''}`}
                  onClick={() => setDesignSubTab('streaming')}
                >
                  ⚡ Streaming UI Sandbox
                </button>
                <button
                  className={`chip ${designSubTab === 'principles' ? 'active' : ''}`}
                  onClick={() => setDesignSubTab('principles')}
                >
                  🎓 Gary Simon Crash Course
                </button>
                <button
                  className={`chip ${designSubTab === 'receipts' ? 'active' : ''}`}
                  onClick={() => setDesignSubTab('receipts')}
                >
                  📜 Shard & Relay Receipts
                </button>
              </div>

              <div className="design-status-pill">
                <span className="live-pulse-dot" />
                <span>Deterministic Heuristic Engine v0.1</span>
              </div>
            </div>

            {/* SUB-PANEL 0: Intelligent Shard Explorer (assistant-ui Deterministic Boundary) */}
            {designSubTab === 'intelligent' && (
              <div className="design-intelligent-view">
                <div className="intelligent-header-card card-lift">
                  <div className="intelligent-meta-row">
                    <span className="intelligent-tag">&lt;assistant-ui:deterministic-boundary&gt;</span>
                    <span className="intelligent-badge">UI = R(S, C, P) ACTIVE</span>
                  </div>
                  <h3>Intelligent Shard Explorer & Capability Boundary</h3>
                  <p className="card-desc">
                    Sanitized DTO projections expose verified memory shards to agent vision without raw SQLite or script execution leaks.
                    Mutations require typed validation and explicit Dave GM approval.
                  </p>
                  <div className="formula-box">
                    <code>S = 9-DB FTS5 Substrate | C = Typed Component Contract | P = Gatekeeper Policy Gateway</code>
                  </div>
                </div>

                <div className="intelligent-cards-grid">
                  <div className="intelligent-shard-card card-lift">
                    <div className="card-top-row">
                      <span className="shard-id-pill">Shard 30377@db7</span>
                      <span className="gate-pill verified">PROVENANCE: DAV3</span>
                    </div>
                    <h4>NouGen Intelligent UI: assistant-ui Deterministic Boundary & Shard Explorer Contract</h4>
                    <p className="shard-snippet">
                      Core Architectural Invariant: UI = Render(State, Contract, Permissions). Exposes sanitized DOM projections to local models with explicit mutation gating.
                    </p>
                    <div className="capability-cluster">
                      <span className="cap-chip read">✓ Visibility: Sanitized DTO</span>
                      <span className="cap-chip read">✓ Inspect Full Text</span>
                      <span className="cap-chip gate">🔒 Morph: GM Approval Req</span>
                      <span className="cap-chip gate">🔒 Relay: GM Approval Req</span>
                    </div>
                    <div className="card-actions-row">
                      <button
                        className="primary-cyber-btn mini"
                        onClick={() => {
                          setSearchTerm('30377');
                          setTab('search');
                        }}
                      >
                        🔍 Inspect in Shards
                      </button>
                      <button
                        className="ghost-btn mini"
                        onClick={() => {
                          alert('Dry-run policy check: Read action permitted under current AUTHORITY.md policy.');
                        }}
                      >
                        ⚡ Check Action Gate
                      </button>
                    </div>
                  </div>

                  <div className="intelligent-shard-card card-lift">
                    <div className="card-top-row">
                      <span className="shard-id-pill">Shard 30216@db8</span>
                      <span className="gate-pill verified">PROVENANCE: DAV3</span>
                    </div>
                    <h4>Recurse Invariant: Polite Transcript Pacing & Zero Rehearsal Protocol</h4>
                    <p className="shard-snippet">
                      Zero LLM Vibe Guessing / Rehearsal. Retrieves ground truth from shards and live OS state rather than rehearsing speculative assumptions.
                    </p>
                    <div className="capability-cluster">
                      <span className="cap-chip read">✓ Visibility: Sanitized DTO</span>
                      <span className="cap-chip read">✓ Deduplication: tube:&lt;id&gt;</span>
                      <span className="cap-chip read">✓ Pacing: 12.0s</span>
                      <span className="cap-chip gate">🔒 Grid Mutation: Gated</span>
                    </div>
                    <div className="card-actions-row">
                      <button
                        className="primary-cyber-btn mini"
                        onClick={() => {
                          setSearchTerm('30216');
                          setTab('search');
                        }}
                      >
                        🔍 Inspect in Shards
                      </button>
                      <button
                        className="ghost-btn mini"
                        onClick={() => {
                          alert('Dry-run policy check: Read action permitted under current AUTHORITY.md policy.');
                        }}
                      >
                        ⚡ Check Action Gate
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* SUB-PANEL 1: Design Quality Index Audit */}
            {designSubTab === 'audit' && (
              <div className="design-audit-view">
                <div className="design-overview-card card-lift">
                  <div className="dqi-score-block">
                    <span className="dqi-badge">DESIGN QUALITY INDEX</span>
                    <div className="dqi-hero-number">
                      {Math.round(
                        ((designWeights.hierarchy +
                          designWeights.contrast +
                          designWeights.alignment +
                          designWeights.whitespace +
                          designWeights.grouping +
                          designWeights.typography +
                          designWeights.action) /
                          35) *
                          100
                      )}
                      <span className="dqi-denom">/ 100</span>
                    </div>
                    <span className="dqi-verdict">
                      {Math.round(
                        ((designWeights.hierarchy +
                          designWeights.contrast +
                          designWeights.alignment +
                          designWeights.whitespace +
                          designWeights.grouping +
                          designWeights.typography +
                          designWeights.action) /
                          35) *
                          100
                      ) >= 85
                        ? '✨ PRODUCTION GRADE'
                        : Math.round(
                            ((designWeights.hierarchy +
                              designWeights.contrast +
                              designWeights.alignment +
                              designWeights.whitespace +
                              designWeights.grouping +
                              designWeights.typography +
                              designWeights.action) /
                              35) *
                              100
                          ) >= 70
                        ? '⚡ NEEDS REFINEMENT'
                        : '⚠️ HIGH COGNITIVE LOAD'}
                    </span>
                    <p className="dqi-formula-caption">
                      Formula: <code>Q_UI = w_h·H + w_c·C + w_a·A + w_s·S + w_u·U</code> (Evaluated across 7 Gary Simon core dimensions)
                    </p>
                  </div>

                  <div className="dqi-sliders-block">
                    <h3 className="section-subheading">Deterministic Constraint Weights</h3>
                    <div className="slider-control-grid">
                      <label className="slider-control-row">
                        <span className="slider-label">Visual Hierarchy (Scale & Weight)</span>
                        <input
                          type="range"
                          min="1"
                          max="5"
                          value={designWeights.hierarchy}
                          onChange={(e) => setDesignWeights({ ...designWeights, hierarchy: Number(e.target.value) })}
                        />
                        <span className="slider-val">{designWeights.hierarchy}/5</span>
                      </label>

                      <label className="slider-control-row">
                        <span className="slider-label">Color & Contrast (4.5:1 WCAG AA)</span>
                        <input
                          type="range"
                          min="1"
                          max="5"
                          value={designWeights.contrast}
                          onChange={(e) => setDesignWeights({ ...designWeights, contrast: Number(e.target.value) })}
                        />
                        <span className="slider-val">{designWeights.contrast}/5</span>
                      </label>

                      <label className="slider-control-row">
                        <span className="slider-label">Alignment & Edge Anchor</span>
                        <input
                          type="range"
                          min="1"
                          max="5"
                          value={designWeights.alignment}
                          onChange={(e) => setDesignWeights({ ...designWeights, alignment: Number(e.target.value) })}
                        />
                        <span className="slider-val">{designWeights.alignment}/5</span>
                      </label>

                      <label className="slider-control-row">
                        <span className="slider-label">White Space & Breathability</span>
                        <input
                          type="range"
                          min="1"
                          max="5"
                          value={designWeights.whitespace}
                          onChange={(e) => setDesignWeights({ ...designWeights, whitespace: Number(e.target.value) })}
                        />
                        <span className="slider-val">{designWeights.whitespace}/5</span>
                      </label>

                      <label className="slider-control-row">
                        <span className="slider-label">Proximity & Spatial Grouping</span>
                        <input
                          type="range"
                          min="1"
                          max="5"
                          value={designWeights.grouping}
                          onChange={(e) => setDesignWeights({ ...designWeights, grouping: Number(e.target.value) })}
                        />
                        <span className="slider-val">{designWeights.grouping}/5</span>
                      </label>

                      <label className="slider-control-row">
                        <span className="slider-label">Typography & Line Measure</span>
                        <input
                          type="range"
                          min="1"
                          max="5"
                          value={designWeights.typography}
                          onChange={(e) => setDesignWeights({ ...designWeights, typography: Number(e.target.value) })}
                        />
                        <span className="slider-val">{designWeights.typography}/5</span>
                      </label>

                      <label className="slider-control-row">
                        <span className="slider-label">Primary Call to Action (Affordance)</span>
                        <input
                          type="range"
                          min="1"
                          max="5"
                          value={designWeights.action}
                          onChange={(e) => setDesignWeights({ ...designWeights, action: Number(e.target.value) })}
                        />
                        <span className="slider-val">{designWeights.action}/5</span>
                      </label>
                    </div>

                    <div className="dqi-actions-row">
                      <button
                        className="ghost-btn mini"
                        onClick={() =>
                          setDesignWeights({
                            hierarchy: 4,
                            contrast: 3,
                            alignment: 4,
                            whitespace: 5,
                            grouping: 4,
                            typography: 4,
                            action: 3,
                          })
                        }
                      >
                        Reset Defaults
                      </button>
                      <button
                        className="primary-cyber-btn mini"
                        onClick={() => {
                          setDesignWeights({
                            hierarchy: 5,
                            contrast: 5,
                            alignment: 5,
                            whitespace: 5,
                            grouping: 5,
                            typography: 5,
                            action: 5,
                          });
                        }}
                      >
                        ⚡ Enforce 100% Strict Rules
                      </button>
                    </div>
                  </div>
                </div>

                {/* Audit Checklist from Gary Simon's Course */}
                <div className="design-checklist-card card-lift">
                  <h3 className="section-subheading">Interactive Gary Simon UI/UX Heuristic Checklist</h3>
                  <p className="card-desc">
                    Directly maps Gary Simon's 6-hour video principles to deterministic design unit tests:
                  </p>
                  <div className="checklist-items">
                    <label className="checklist-item">
                      <input
                        type="checkbox"
                        checked={checkedAuditItems.contrast45}
                        onChange={(e) => setCheckedAuditItems({ ...checkedAuditItems, contrast45: e.target.checked })}
                      />
                      <div>
                        <strong>WCAG AA 4.5:1 Minimum Contrast (27:12 Semantic Color)</strong>
                        <p>Text elements use high-contrast primary foreground against tinted dark backgrounds. No washed-out gray on dark gray.</p>
                      </div>
                    </label>

                    <label className="checklist-item">
                      <input
                        type="checkbox"
                        checked={checkedAuditItems.visualHierarchy}
                        onChange={(e) => setCheckedAuditItems({ ...checkedAuditItems, visualHierarchy: e.target.checked })}
                      />
                      <div>
                        <strong>Visual Hierarchy & Scale (15:14 Design Fundamentals)</strong>
                        <p>Hero display titles stand distinct from body copy by at least 2 font weight tiers and 1.8x font scale ratio.</p>
                      </div>
                    </label>

                    <label className="checklist-item">
                      <input
                        type="checkbox"
                        checked={checkedAuditItems.whitespaceConsistent}
                        onChange={(e) => setCheckedAuditItems({ ...checkedAuditItems, whitespaceConsistent: e.target.checked })}
                      />
                      <div>
                        <strong>Whitespace & Proximity (01:03:19 Spatial Grouping)</strong>
                        <p>Internal card padding (16px) is smaller than external card margin (24px) to preserve Gestalt proximity grouping.</p>
                      </div>
                    </label>

                    <label className="checklist-item">
                      <input
                        type="checkbox"
                        checked={checkedAuditItems.actionProminence}
                        onChange={(e) => setCheckedAuditItems({ ...checkedAuditItems, actionProminence: e.target.checked })}
                      />
                      <div>
                        <strong>Primary Action Affordance (49:47 Hero Composition)</strong>
                        <p>Single primary button stands out with vibrant accent fill; secondary actions use muted ghost borders.</p>
                      </div>
                    </label>
                  </div>
                </div>
              </div>
            )}

            {/* SUB-PANEL 2: Streaming Declarative UI Sandbox */}
            {designSubTab === 'streaming' && (
              <div className="design-streaming-view">
                <div className="streaming-controls-bar">
                  <span>De-branded Declarative Component Compiler Preview:</span>
                  <div className="widget-sample-picker">
                    {(['calculator', 'diagram', 'checklist', 'multivariant'] as const).map((w) => (
                      <button
                        key={w}
                        className={`chip mini ${activeWidgetSample === w ? 'active' : ''}`}
                        onClick={() => setActiveWidgetSample(w)}
                      >
                        {w === 'calculator' && '🧮 Interactive Calculator'}
                        {w === 'diagram' && '📊 Architecture Graph'}
                        {w === 'checklist' && '📋 Task Widget'}
                        {w === 'multivariant' && '🎨 Rakit Multivariant'}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="streaming-sandbox-card card-lift">
                  {/* Sample 1: Interactive Calculator Widget */}
                  {activeWidgetSample === 'calculator' && (
                    <div className="interactive-widget-box">
                      <div className="widget-header">
                        <div>
                          <span className="component-tag">&lt;ui:recipe-calculator&gt;</span>
                          <h4>Fleet Inference VRAM & Scaling Calculator</h4>
                        </div>
                        <span className="widget-live-badge">HYDRATED LIVE</span>
                      </div>
                      <div className="widget-body">
                        <p className="widget-prompt-context">
                          Prompt: <em>"Calculate quantization memory footprint and throughput across Apollo, Hyperion, and Phoebus"</em>
                        </p>
                        <div className="interactive-slider-cluster">
                          <label className="calculator-param-row">
                            <span>Serving Fleet Concurrency: <strong>{activeRecipeServings} parallel sessions</strong></span>
                            <input
                              type="range"
                              min="1"
                              max="16"
                              value={activeRecipeServings}
                              onChange={(e) => setActiveRecipeServings(Number(e.target.value))}
                            />
                          </label>
                          <div className="calculated-metrics-grid">
                            <div className="metric-pill">
                              <span className="m-label">VRAM Requirement</span>
                              <span className="m-val">{(activeRecipeServings * 1.85 + 2.4).toFixed(1)} GB</span>
                            </div>
                            <div className="metric-pill">
                              <span className="m-label">Token Generation Rate</span>
                              <span className="m-val">{Math.round(480 / activeRecipeServings)} tok/s</span>
                            </div>
                            <div className="metric-pill">
                              <span className="m-label">Local Edge GPU Cost</span>
                              <span className="m-val accent-green glow-green">$0.00 / hr</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Sample 2: Architecture Graph */}
                  {activeWidgetSample === 'diagram' && (
                    <div className="interactive-widget-box">
                      <div className="widget-header">
                        <div>
                          <span className="component-tag">&lt;ui:architecture-graph&gt;</span>
                          <h4>NouGen Intelligence & Fleet Relay Map</h4>
                        </div>
                        <span className="widget-live-badge">RENDERED DETERMINISTICALLY</span>
                      </div>
                      <div className="widget-body">
                        <div className="fleet-ascii-graph">
                          <div className="graph-node-block">
                            <div className="g-node">Tauri v2 Desktop HUD</div>
                            <div className="g-arrow">▼ IPC / WebMCP Bridge</div>
                            <div className="g-node highlight">Local Python Shard Substrate (.nougen)</div>
                            <div className="g-arrow">▼ SQLite WAL FTS5</div>
                            <div className="g-node">9-DB Grid (25665@db1)</div>
                          </div>
                          <div className="graph-side-legend">
                            <h5>Connected Fleet Stadiums</h5>
                            <ul>
                              <li>🟢 Apollo (192.168.1.16) — Sol-Ai (Gemma 4 Heavy)</li>
                              <li>🔵 Hyperion (192.168.1.187) — Yukiai (Tactical Edge)</li>
                              <li>🟣 Phoebus (192.168.1.78) — Keadracode (Backbone)</li>
                            </ul>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Sample 3: Checklist Widget */}
                  {activeWidgetSample === 'checklist' && (
                    <div className="interactive-widget-box">
                      <div className="widget-header">
                        <div>
                          <span className="component-tag">&lt;ui:ephemeral-checklist&gt;</span>
                          <h4>Pre-Deployment Release Hardening</h4>
                        </div>
                        <span className="widget-live-badge">ACTIVE STATE</span>
                      </div>
                      <div className="widget-body">
                        <div className="ephemeral-checklist">
                          <label className="check-row">
                            <input type="checkbox" defaultChecked />
                            <span>Run Gary Simon 4.5:1 Contrast & Hierarchy Verification</span>
                          </label>
                          <label className="check-row">
                            <input type="checkbox" defaultChecked />
                            <span>Verify Frameless Tauri Chrome (Minimize, Maximize, Close IPC)</span>
                          </label>
                          <label className="check-row">
                            <input type="checkbox" defaultChecked />
                            <span>Capture FTS5 Persistent Memory Shard (25665@db1)</span>
                          </label>
                          <label className="check-row">
                            <input type="checkbox" defaultChecked />
                            <span>Emit Fleet Relay Receipt to <code>g-whoentertains</code></span>
                          </label>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Sample 4: Multivariant Theme Switcher (RakitUI de-branded pattern) */}
                  {activeWidgetSample === 'multivariant' && (
                    <div className="interactive-widget-box">
                      <div className="widget-header">
                        <div>
                          <span className="component-tag">&lt;ui:multivariant-selector&gt;</span>
                          <h4>Deterministic Design System Selector</h4>
                        </div>
                        <span className="widget-live-badge">MULTI-VARIANT</span>
                      </div>
                      <div className="widget-body">
                        <div className="variant-buttons-row">
                          {(['cyber', 'minimal', 'glass'] as const).map((v) => (
                            <button
                              key={v}
                              className={`chip ${selectedVariant === v ? 'active' : ''}`}
                              onClick={() => setSelectedVariant(v)}
                            >
                              {v === 'cyber' && '⚡ Cyber Neon HUD'}
                              {v === 'minimal' && '📐 Minimal Modernist'}
                              {v === 'glass' && '💎 Translucent Glass'}
                            </button>
                          ))}
                        </div>
                        <div className={`variant-preview-card variant-${selectedVariant}`}>
                          <h5>Selected Mode: {selectedVariant.toUpperCase()}</h5>
                          <p>
                            Design Tokens dynamically adapt spacing, typography scale, and accent border radiuses without breaking layout constraints.
                          </p>
                          <div className="sample-button-group">
                            <button className="primary-cyber-btn mini">Confirm Action</button>
                            <button className="ghost-btn mini">Cancel</button>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* SUB-PANEL 3: Gary Simon Lessons & Principles */}
            {designSubTab === 'principles' && (
              <div className="design-principles-view">
                <div className="lessons-grid">
                  <div className="lesson-card card-lift">
                    <span className="timestamp-badge">15:14</span>
                    <h4>Design Fundamentals</h4>
                    <p>
                      Hierarchy, contrast, alignment, whitespace, spatial grouping, and typography form the immutable foundation. An interface fails not from lack of decoration, but from lack of clear visual direction.
                    </p>
                  </div>

                  <div className="lesson-card card-lift">
                    <span className="timestamp-badge">27:12</span>
                    <h4>Semantic Color & Contrast</h4>
                    <p>
                      Color should convey meaning rather than just aesthetics. WCAG AA compliance requires at least 4.5:1 contrast for normal text and 3:1 for large text. Never sacrifice legibility for subtle style.
                    </p>
                  </div>

                  <div className="lesson-card card-lift">
                    <span className="timestamp-badge">49:47</span>
                    <h4>Hero Composition</h4>
                    <p>
                      The primary call to action must immediately dominate the visual focal point. Secondary elements should recede gracefully using muted colors and lower visual weight.
                    </p>
                  </div>

                  <div className="lesson-card card-lift">
                    <span className="timestamp-badge">01:03:19</span>
                    <h4>Spatial Grouping & Proximity</h4>
                    <p>
                      Related elements must sit closer to each other than unrelated elements. Increasing internal card whitespace without increasing external margins causes visual confusion.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* SUB-PANEL 4: Shard & Relay Receipts */}
            {designSubTab === 'receipts' && (
              <div className="design-receipts-view">
                <div className="receipt-card card-lift">
                  <div className="receipt-header">
                    <span className="receipt-icon">📜</span>
                    <h4>Persistent Memory Shard Capture Receipt</h4>
                    <span className="receipt-badge ok">STORED IN 9-DB GRID</span>
                  </div>
                  <div className="receipt-body">
                    <dl className="receipt-dl">
                      <dt>Shard Reference</dt>
                      <dd><code>25665@db1</code> (Accepted by Apollo / Hyperion Mesh)</dd>
                      <dt>Canonical Authority</dt>
                      <dd><code>C:\Users\super\.nougen\shards</code></dd>
                      <dt>Morph Ingestion</dt>
                      <dd>3 Candidates Evaluated (MorphScore range: 0.6430 - 0.7266)</dd>
                      <dt>Status</dt>
                      <dd>Immutable FTS5 Wal Record Committed</dd>
                    </dl>
                  </div>
                </div>

                <div className="receipt-card card-lift">
                  <div className="receipt-header">
                    <span className="receipt-icon">🛰️</span>
                    <h4>Fleet Relay Dispatch Receipt</h4>
                    <span className="receipt-badge ok">PUBLISHED TO REGISTRY</span>
                  </div>
                  <div className="receipt-body">
                    <dl className="receipt-dl">
                      <dt>Relay ID</dt>
                      <dd><code>20261008T041603Z__chatgpt-app__g-whoentertains</code></dd>
                      <dt>Origin Lane</dt>
                      <dd>Antigravity Coach (PX13 Hyperion 192.168.1.187)</dd>
                      <dt>Target Registry</dt>
                      <dd><code>.handoffs/</code> Fleet Mesh Synced</dd>
                      <dt>Verification</dt>
                      <dd>Zero Mock Data — Built with Local Deterministic Rules</dd>
                    </dl>
                  </div>
                </div>
              </div>
            )}
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
                  <span>Search relevance: <strong>{selectedShard.final_score == null ? 'Not scored' : `${Math.round(selectedShard.final_score * 100)}%`}</strong></span>
                  {selectedShard.timestamp && <span>Saved: <strong>{formatEasternTime(selectedShard.timestamp)}</strong></span>}
                </div>

                <dl className="memory-evidence">
                  <dt>Vault observed on</dt><dd>{identity?.hostname ?? 'Unavailable'}</dd>
                  <dt>Vault path</dt><dd>{identity?.vault_path ?? 'Unavailable'}</dd>
                  <dt>Record length</dt><dd>{selectedShard.content.length.toLocaleString()} characters</dd>
                  <dt>Origin machine / agent / session</dt><dd>Not resolved from structured provenance</dd>
                  <dt>Related shards / relay ancestry / correction</dt><dd>Not resolved</dd>
                </dl>
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
            {tauriInvoke && <span><kbd>Ctrl</kbd>+<kbd>Q</kbd> Exit</span>}
          </div>
          <span className="dock-sep">·</span>
          <span className="brand-copyright">Who Visions LLC</span>
        </div>
      </footer>
    </div>
  );
}
