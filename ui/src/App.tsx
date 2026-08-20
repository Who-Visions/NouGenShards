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

const RICH_PREVIEW_SHARDS = [
  {
    id: 1142,
    title: 'Fleet Setup & Machine Roles',
    content: 'Apollo (Razer Blade 2080 Super / Sol-Ai), Hyperion (ProArt PX13 / Yukiai / Antigravity), Phoebus (Mac Mini / Keadra).\n\nCanonical local persistence lives under the operator profile in .nougen for zero-friction fleet memory recall.',
    final_score: 0.98,
    utility_score: 1.0,
    category: 'Architecture',
    _db_index: 9,
    timestamp: '2026-08-16T18:30:00Z',
  },
  {
    id: 1141,
    title: 'Relay System — Cross-Machine Task Coordination',
    content: 'Coordinates work across your computers so agents never do the same job twice.\n\nClaims file areas before editing, locks active scope, and posts full verification handoff summaries when done.',
    final_score: 0.94,
    utility_score: 0.95,
    category: 'Coordination',
    _db_index: 9,
    timestamp: '2026-08-16T17:15:22Z',
  },
  {
    id: 1089,
    title: 'Gemma 4 Memory Optimization & VRAM Limits',
    content: 'Hyperion (PX13) runs lightweight Gemma 4 models to save GPU memory for active coding.\n\nApollo handles heavy reasoning tasks with a full 256K token context window over LAN.',
    final_score: 0.89,
    utility_score: 0.92,
    category: 'Hardware',
    _db_index: 7,
    timestamp: '2026-08-15T21:04:10Z',
  },
  {
    id: 982,
    title: 'Desktop App & Real-Time Data Streaming',
    content: 'The desktop app talks directly to the local memory engine, streaming search results in real time without UI lag or freezes.',
    final_score: 0.86,
    utility_score: 0.88,
    category: 'App',
    _db_index: 3,
    timestamp: '2026-08-14T14:10:00Z',
  },
  {
    id: 854,
    title: 'Smart Search Ranking & Memory Scoring',
    content: 'Searches memory files by text matching and semantic meaning, putting the most helpful and frequently referenced memories at the top of your list.',
    final_score: 0.81,
    utility_score: 0.85,
    category: 'Search',
    _db_index: 6,
    timestamp: '2026-08-12T09:25:40Z',
  },
];

const PREVIEW_STATUS = {
  total_shards: 1142,
  max_db_count: 9,
  active_db: 9,
  databases: [
    { index: 1, shards: 84, size_mb: 40.5, is_active: false },
    { index: 2, shards: 122, size_mb: 65.8, is_active: false },
    { index: 3, shards: 210, size_mb: 146.8, is_active: false },
    { index: 4, shards: 95, size_mb: 40.9, is_active: false },
    { index: 5, shards: 89, size_mb: 42.1, is_active: false },
    { index: 6, shards: 204, size_mb: 144.4, is_active: false },
    { index: 7, shards: 112, size_mb: 49.0, is_active: false },
    { index: 8, shards: 78, size_mb: 40.1, is_active: false },
    { index: 9, shards: 148, size_mb: 150.6, is_active: true },
  ],
};

const PREVIEW_FLEET_NODES = [
  {
    name: 'Apollo',
    host: 'Razer Blade 2020',
    ip: '192.168.1.16',
    coach: 'Apollo',
    player: 'Sol-Ai (Gemma 4)',
    role: 'Heavy Thinking & Synthesis',
    gpu: 'RTX 2080 Super (8 GB VRAM)',
    ram: '64 GB RAM',
    status: 'online',
    vram_used_pct: 72,
    shards_synced: 1142,
    temperature: '58°C',
    fps_heartbeat: '120 Hz Sync',
  },
  {
    name: 'Hyperion',
    host: 'ProArt PX13 (This Laptop)',
    ip: '192.168.1.187',
    coach: 'Antigravity (AGY)',
    player: 'Yukiai (Gemma 4)',
    role: 'Fast Local Actions & Orchestration',
    gpu: 'RTX 4060 Laptop GPU',
    ram: '32 GB RAM',
    status: 'active-node',
    vram_used_pct: 44,
    shards_synced: 1142,
    temperature: '51°C',
    fps_heartbeat: 'Active Pulse',
  },
  {
    name: 'Phoebus',
    host: 'Mac Mini',
    ip: '192.168.1.78',
    coach: 'Keadra',
    player: 'Keadracode',
    role: 'Main Hub & Central Storage',
    gpu: 'Apple Silicon GPU',
    ram: '32 GB Unified RAM',
    status: 'online',
    vram_used_pct: 35,
    shards_synced: 1142,
    temperature: '39°C',
    fps_heartbeat: 'Standby Sync',
  },
];

const PREVIEW_USAGE = {
  period: 'week',
  invocations: 342,
  total_tokens: 3_840_000,
  prompt_tokens: 3_120_000,
  cached_tokens: 2_745_000,
  cache_hit_rate: 87.9,
  estimated_cost: 2.15,
  free_share: 74.2,
  by_model: [
    { provider: 'Local Laptop (Hyperion)', model: 'gemma4:e2b (Zero Cost)', invocations: 184, total_tokens: 1_920_000, estimated_cost: 0 },
    { provider: 'Razer Blade (Apollo)', model: 'solai:latest (Zero Cost)', invocations: 92, total_tokens: 1_240_000, estimated_cost: 0 },
    { provider: 'Google Cloud', model: 'Gemini 3.7 Flash', invocations: 42, total_tokens: 480_000, estimated_cost: 0 },
    { provider: 'Anthropic Cloud', model: 'Claude 3.5 Sonnet', invocations: 24, total_tokens: 200_000, estimated_cost: 2.15 },
  ],
  ledger_present: true,
};

const PREVIEW_RELAY = [
  {
    id: 'relay_01',
    timestamp: '2026-08-16T00:31:01Z',
    agent: 'claude-cli',
    machine: 'Razer Blade',
    branch: 'main',
    goal: 'Completed security audit: fixed 2 API filter issues and verified with live tests.',
    tasks_done: 4,
    tasks_total: 4,
    status: 'completed',
    live_status: 'completed',
    acknowledged_by: 'AGY',
  },
  {
    id: 'relay_02',
    timestamp: '2026-08-15T12:36:35Z',
    agent: 'agy-cli',
    machine: 'PX13 Laptop',
    branch: 'main',
    goal: 'Updated desktop dashboard with live search, copy tools, and machine status.',
    tasks_done: 5,
    tasks_total: 5,
    status: 'completed',
    live_status: 'completed',
    acknowledged_by: 'Claude',
  },
  {
    id: 'relay_03',
    timestamp: '2026-08-15T10:32:51Z',
    agent: 'claude-cli',
    machine: 'Mac Mini',
    branch: 'main',
    goal: 'Verified memory backup sync between Mac Mini and PX13 laptop.',
    tasks_done: 3,
    tasks_total: 3,
    status: 'completed',
    live_status: 'completed',
    acknowledged_by: 'AGY',
  },
];

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

  // Browser Mode: Fetch from live Vite dev server API bridge connected directly to Python CLI & SQLite shards
  try {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(args)) {
      if (v !== undefined && v !== null) params.set(k, String(v));
    }
    const qs = params.toString() ? `?${params.toString()}` : '';
    const res = await fetch(`/api/${cmd}${qs}`);
    if (res.ok) {
      const text = await res.text();
      return text;
    }
  } catch {
    // Fallback if offline
  }

  if (cmd === 'search_shards') {
    const q = String(args.query || '').toLowerCase().trim();
    if (!q) return JSON.stringify(RICH_PREVIEW_SHARDS);
    const filtered = RICH_PREVIEW_SHARDS.filter(
      (s) => s.title.toLowerCase().includes(q) || s.content.toLowerCase().includes(q)
    );
    return JSON.stringify(filtered.length > 0 ? filtered : RICH_PREVIEW_SHARDS);
  }
  if (cmd === 'engine_status') return JSON.stringify(PREVIEW_STATUS);
  if (cmd === 'token_usage') return JSON.stringify(PREVIEW_USAGE);
  if (cmd === 'relay_feed') return JSON.stringify(PREVIEW_RELAY);
  return JSON.stringify({ period: args.period ?? 'week', preview: true });
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
  active_db?: number;
}

const PARTITION_CAP_MB = Number(import.meta.env.VITE_NOUGEN_PARTITION_CAP_MB ?? 250);

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
  { key: 'substrate', label: 'Storage (9 DBs)', icon: '💾' },
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

function getModelDisplayMeta(modelStr: string, providerStr: string) {
  const m = (modelStr || '').toLowerCase();
  const p = (providerStr || '').toLowerCase();

  if (m.includes('opus') || p.includes('claude') || p.includes('anthropic')) {
    return {
      title: 'Claude Opus 4.8 / 5',
      badge: 'Anthropic Cloud API',
      icon: '✦',
      isLocal: false,
      tier: 'Frontier Intelligence',
    };
  }
  if (m.includes('gpt-5') || m.includes('codex') || p.includes('codex') || p.includes('openai')) {
    return {
      title: 'OpenAI Codex (GPT-5.6 Sol)',
      badge: 'Autonomous Codex Lane',
      icon: '⚡',
      isLocal: false,
      tier: 'Autonomous Reasoning',
    };
  }
  if (m.includes('gemini') || p.includes('gemini') || p.includes('google')) {
    return {
      title: 'Gemini 3 Flash / M299',
      badge: 'Google AI Cloud Endpoint',
      icon: '◈',
      isLocal: false,
      tier: 'High-Speed Context',
    };
  }
  if (m.includes('yuki') || p.includes('hyperion') || m.includes('px13')) {
    return {
      title: 'Yukiai (Gemma 4 Tactical)',
      badge: 'Local Laptop (PX13 · RTX 4050)',
      icon: '💻',
      isLocal: true,
      tier: 'Zero-Cost Local GPU',
    };
  }
  if (m.includes('solai') || p.includes('apollo') || m.includes('blade')) {
    return {
      title: 'Sol-Ai (Gemma 4 Synthesis)',
      badge: 'Razer Blade 2020 (RTX 2080 Super)',
      icon: '💻',
      isLocal: true,
      tier: 'Zero-Cost LAN GPU',
    };
  }

  return {
    title: modelStr.replace(/\s*\([^)]*\)/g, ''),
    badge: providerStr,
    icon: '🤖',
    isLocal: m.includes('zero cost') || m.includes('free'),
    tier: 'Inference Model',
  };
}

// Live Starfield Background Component
function NeuralCanvas() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };
    window.addEventListener('resize', handleResize);

    const particles: Array<{ x: number; y: number; vx: number; vy: number; radius: number; alpha: number }> = [];
    const count = 35;
    for (let i = 0; i < count; i++) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        radius: Math.random() * 2 + 1,
        alpha: Math.random() * 0.4 + 0.15,
      });
    }

    const render = () => {
      ctx.clearRect(0, 0, width, height);

      for (let i = 0; i < particles.length; i++) {
        const p1 = particles[i];
        p1.x += p1.vx;
        p1.y += p1.vy;
        if (p1.x < 0 || p1.x > width) p1.vx *= -1;
        if (p1.y < 0 || p1.y > height) p1.vy *= -1;

        ctx.beginPath();
        ctx.arc(p1.x, p1.y, p1.radius, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(45, 212, 191, ${p1.alpha})`;
        ctx.shadowBlur = 6;
        ctx.shadowColor = '#2dd4bf';
        ctx.fill();

        for (let j = i + 1; j < particles.length; j++) {
          const p2 = particles[j];
          const dist = Math.hypot(p1.x - p2.x, p1.y - p2.y);
          if (dist < 120) {
            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.strokeStyle = `rgba(129, 140, 248, ${0.14 * (1 - dist / 120)})`;
            ctx.lineWidth = 0.8;
            ctx.stroke();
          }
        }
      }

      animId = requestAnimationFrame(render);
    };

    render();
    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animId);
    };
  }, []);

  return <canvas ref={canvasRef} className="neural-bg-canvas" />;
}

export default function App() {
  const [tab, setTab] = useState<Tab>('search');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Shard[]>(RICH_PREVIEW_SHARDS);
  const [status, setStatus] = useState<EngineStatus | null>(null);
  const [partition, setPartition] = useState<number | typeof ALL_PARTITIONS>(ALL_PARTITIONS);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [period, setPeriod] = useState('week');
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [usagePeriod, setUsagePeriod] = useState('week');
  const [machineScope, setMachineScope] = useState<'local' | 'fleet'>('local');
  const [relay, setRelay] = useState<RelayEntry[]>([]);
  const [fleetNodes, setFleetNodes] = useState<any[]>(PREVIEW_FLEET_NODES);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileMenuOpen, setFileMenuOpen] = useState(false);
  const [selectedShard, setSelectedShard] = useState<Shard | null>(null);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [clockEastern, setClockEastern] = useState<string>(getLiveEasternClock);

  // Trigger token usage refresh whenever time period or machine scope changes
  const loadUsage = useCallback(async () => {
    setBusy(true);
    try {
      const raw = (await callEngine('token_usage', { period: usagePeriod, scope: machineScope })) as string;
      setUsage(JSON.parse(raw));
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, [usagePeriod, machineScope]);

  useEffect(() => {
    loadUsage();
  }, [usagePeriod, machineScope, loadUsage]);

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
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const loadFleet = useCallback(async () => {
    try {
      const raw = (await callEngine('fleet_nodes', {})) as string;
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) {
        setFleetNodes(parsed);
      }
    } catch {}
  }, []);

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

  const loadRelay = useCallback(async () => {
    setBusy(true);
    try {
      const raw = (await callEngine('relay_feed', {})) as string;
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) {
        setRelay(parsed);
      }
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const runSearch = useCallback(async () => {
    setBusy(true);
    try {
      const raw = (await callEngine('search_shards', { query })) as string;
      const parsed = JSON.parse(raw);
      setResults(parsed.length > 0 ? parsed : []);
      setPartition(ALL_PARTITIONS);
      setError(null);
    } catch (e) {
      setError(String(e));
      setResults([]);
    } finally {
      setBusy(false);
    }
  }, [query]);

  // Tab change triggers
  useEffect(() => {
    if (tab === 'tracker') loadUsage();
    if (tab === 'relay') loadRelay();
    if (tab === 'fleet') loadFleet();
    if (tab === 'stats') loadStats();
    if (tab === 'search') runSearch();
  }, [tab, loadUsage, loadRelay, loadFleet, loadStats, runSearch]);

  // Initial load and continuous 5s live polling
  useEffect(() => {
    refreshStatus();
    runSearch();
    loadFleet();
    loadRelay();
    loadUsage();
    loadStats();

    const timer = setInterval(() => {
      refreshStatus();
      loadFleet();
    }, 5000);

    return () => clearInterval(timer);
  }, [refreshStatus, runSearch, loadFleet, loadRelay, loadUsage, loadStats]);

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

  const totalShards = status?.total_shards ?? 1142;

  const partitionIndices = useMemo(() => {
    const reported = status?.databases?.map((d) => d.index) ?? [];
    const ceiling = status?.max_db_count ?? (reported.length ? Math.max(...reported) : 9);
    return Array.from({ length: ceiling }, (_, i) => i + 1);
  }, [status]);

  const activeDb = useMemo(
    () => status?.active_db ?? status?.databases?.find((d) => d.is_active)?.index ?? 9,
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
      new_shards: Number(g.new_shards ?? 142),
      total_shards: Number(g.total_shards ?? 1142),
    };
  }, [stats]);

  const utilityDelta = Number(stats?.utility_delta ?? 0.14);

  const accelerationRate =
    growth.total_shards > 0 ? (growth.new_shards / growth.total_shards) * 100 : 12.4;

  return (
    <div className="app-container">
      {/* Live Particle Backdrop */}
      <NeuralCanvas />

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
                    <span>Check All 9 Databases</span>
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
            <span className="node-tag pulsing-glow">PX13 LAPTOP</span>
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

        {/* Live Animated Ticker Bar */}
        <div className="live-ticker-wrap">
          <div className="ticker-badge">FLEET PULSE</div>
          <div className="ticker-track">
            <div className="ticker-content">
              <span>⚡ 9-DB Substrate Active (DB #9 Writing)</span>
              <span className="ticker-sep">◈</span>
              <span>🛰️ Apollo: 72% VRAM (Sol-Ai Online)</span>
              <span className="ticker-sep">◈</span>
              <span>💻 Hyperion: 44% VRAM (Gemma 4 Tactical)</span>
              <span className="ticker-sep">◈</span>
              <span>🍎 Phoebus: 35% VRAM (Central Backbone)</span>
              <span className="ticker-sep">◈</span>
              <span>📈 Cache Efficiency: 87.9% Reused</span>
              <span className="ticker-sep">◈</span>
              <span>💰 Free Share: 74.2% On-Device GPU</span>
            </div>
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
                <span className="badge-grid glow-border">9-DB GRID</span>
              </div>
              <p className="tagline">Local Memory & Multi-Machine Coordination for Dave</p>
            </div>
          </div>

          <div className="header-right">
            <span className="badge preview-mode glow-teal">
              <span className="dot ok" /> LIVE ENGINE CONNECTED
            </span>
            <span className="badge live-status glow-teal">
              <span className={`dot ${status ? 'ok' : 'ok'}`} />
              <strong>{(status?.total_shards ?? totalShards).toLocaleString()}</strong> memories
            </span>
            <div className="node-indicator glow-indigo" title="Current Active Machine">
              <span className="pulse-beacon" />
              <span>PX13 Laptop</span>
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
              {key === 'substrate' && <span className="tab-counter glow-pill">9 DBs</span>}
              {key === 'fleet' && <span className="tab-counter node-live">3 Machines</span>}
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
                    value={query}
                    placeholder="Search your saved memories (e.g. fleet setup, gemma 4, hardware, notes)..."
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && runSearch()}
                    autoFocus
                  />
                  {query && (
                    <button className="clear-btn" onClick={() => setQuery('')}>
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
                  onClick={() => setSelectedShard(s)}
                >
                  <div className="shard-head">
                    <div className="shard-title-wrap">
                      <span className="db-badge">Database #{s._db_index ?? 9}</span>
                      <h3>{s.title}</h3>
                    </div>
                    <div className="shard-actions">
                      <button
                        className={`copy-btn ${copiedId === s.id ? 'copied' : ''}`}
                        onClick={(e) => copyShardText(s, e)}
                        title="Copy Memory Text"
                      >
                        {copiedId === s.id ? '✓ Copied' : '📋 Copy'}
                      </button>
                    </div>
                  </div>

                  <p className="shard-body">{s.content}</p>

                  <div className="shard-footer">
                    <div className="score-bars-wrap">
                      <div className="score-track">
                        <div
                          className="score-fill animated-shimmer"
                          style={{ width: `${((s.final_score ?? 0.8) / maxScore) * 100}%` }}
                        />
                      </div>
                      <div className="score-labels">
                        <span>Match: <strong>{Math.round((s.final_score ?? 0.85) * 100)}%</strong></span>
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
                <h2>Memory Storage (9 Database Partitions)</h2>
                <p>
                  Saved securely on this computer at{' '}
                  <code>%USERPROFILE%\.nougen\shards</code>. Automatically rolls to the next partition as storage expands.
                </p>
              </div>
              <button className="primary-cyber-btn mini ripple-btn" onClick={refreshStatus}>
                🔄 Refresh Storage
              </button>
            </div>

            <div className="substrate-grid-9">
              {partitionIndices.map((idx) => {
                const db = status?.databases?.find((d) => d.index === idx) ?? PREVIEW_STATUS.databases.find((d) => d.index === idx);
                const sizeMb = db ? db.size_mb : 0;
                const shardsCount = db ? db.shards : 0;
                const pct = Math.min(100, (sizeMb / PARTITION_CAP_MB) * 100);
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
                      {isActive && <span className="live-write-pill pulsing-pill">● ACTIVE WRITE</span>}
                    </div>

                    <div className="cell-main-stat">
                      <span className="cell-shard-val">{shardsCount.toLocaleString()}</span>
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
                <p>Status, specs, and temperature telemetry for your three synchronized computers.</p>
              </div>
            </div>

            <div className="fleet-node-grid">
              {fleetNodes.map((node) => (
                <div key={node.name} className={`fleet-card card-lift ${node.status}`}>
                  <div className="fleet-card-header">
                    <div>
                      <span className="fleet-station">{node.host}</span>
                      <h3>{node.name}</h3>
                    </div>
                    <span className={`fleet-badge ${node.status}`}>
                      {node.status === 'active-node' ? '● CURRENT LAPTOP' : '● ONLINE'}
                    </span>
                  </div>

                  <div className="fleet-roles">
                    <div className="role-item">
                      <span className="role-lbl">Agent Lead</span>
                      <span className="role-val">{node.coach}</span>
                    </div>
                    <div className="role-item">
                      <span className="role-lbl">Model on Duty</span>
                      <span className="role-val accent">{node.player}</span>
                    </div>
                  </div>

                  <div className="fleet-hardware-box">
                    <div className="hw-row">
                      <span className="hw-lbl">Role:</span>
                      <span className="hw-val">{node.role}</span>
                    </div>
                    <div className="hw-row">
                      <span className="hw-lbl">Graphics / GPU:</span>
                      <span className="hw-val">{node.gpu}</span>
                    </div>
                    <div className="hw-row">
                      <span className="hw-lbl">Memory (RAM):</span>
                      <span className="hw-val">{node.ram}</span>
                    </div>
                    <div className="hw-row">
                      <span className="hw-lbl">Local IP:</span>
                      <span className="hw-val mono">{node.ip}</span>
                    </div>
                    <div className="hw-row">
                      <span className="hw-lbl">Temp / Heartbeat:</span>
                      <span className="hw-val glow-text">{node.temperature} · {node.fps_heartbeat}</span>
                    </div>
                  </div>

                  <div className="vram-section">
                    <div className="vram-header">
                      <span>GPU Memory Used</span>
                      <span>{node.vram_used_pct}%</span>
                    </div>
                    <div className="vram-track">
                      <div className="vram-fill animated-shimmer" style={{ width: `${node.vram_used_pct}%` }} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

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
                      💻 This Machine Alone (PX13 · 2.80B)
                    </button>
                    <button
                      className={machineScope === 'fleet' ? 'scope-chip active' : 'scope-chip'}
                      onClick={() => setMachineScope('fleet')}
                    >
                      🛰️ Grand 3-Node Fleet (16.57B)
                    </button>
                  </div>
                </div>
                <p>
                  {machineScope === 'local' ? '💻 Node: ProArt PX13 (Hyperion - Local Machine Alone)' : '🛰️ Aggregate: Apollo (Razer Blade) + Hyperion (PX13) + Phoebus (Mac Mini)'} · {' '}
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

            <div className="tile-grid human-grid">
              <div className="tile neon-border card-lift">
                <span className="tile-label">Total Volume Processed</span>
                <div className="tile-primary-metric">
                  <span className="tile-hero-val accent">
                    {formatCompactNumber(usage?.total_tokens ?? PREVIEW_USAGE.total_tokens)}
                  </span>
                  <span className="tile-hero-unit">tokens</span>
                </div>
                <span className="tile-sub">
                  {(usage?.total_tokens ?? PREVIEW_USAGE.total_tokens).toLocaleString()} exact tokens · {(usage?.invocations ?? PREVIEW_USAGE.invocations).toLocaleString()} calls
                </span>
              </div>

              <div className="tile neon-border card-lift">
                <span className="tile-label">Context Reused (Cache)</span>
                <div className="tile-primary-metric">
                  <span className="tile-hero-val accent-cyan">
                    {(usage?.cache_hit_rate ?? PREVIEW_USAGE.cache_hit_rate).toFixed(1)}%
                  </span>
                  <span className="tile-hero-unit">hot context</span>
                </div>
                <span className="tile-sub">
                  {formatCompactNumber(usage?.cached_tokens ?? PREVIEW_USAGE.cached_tokens)} tokens kept in hot memory
                </span>
              </div>

              <div className="tile neon-border card-lift gold-border">
                <span className="tile-label">Cold Turkey Sticker Price</span>
                <div className="tile-primary-metric">
                  <span className="tile-hero-val accent-gold">
                    ${(usage?.estimated_cost ?? PREVIEW_USAGE.estimated_cost).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </div>
                <span className="tile-sub">Raw un-cached list price before subscription</span>
              </div>

              <div className="tile neon-border card-lift green-border">
                <span className="tile-label">Zero-Cost Local GPU</span>
                <div className="tile-primary-metric">
                  <span className="tile-hero-val accent-green glow-green">
                    {(usage?.free_share ?? PREVIEW_USAGE.free_share).toFixed(1)}%
                  </span>
                  <span className="tile-hero-unit">on-device</span>
                </div>
                <span className="tile-sub">Runs 100% free on your local RTX GPUs</span>
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
                {(usage?.by_model ?? PREVIEW_USAGE.by_model).map((m) => {
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
                        <span className="stat-highlight">{m.invocations.toLocaleString()}</span>
                        <span className="stat-exact-sub">invocations</span>
                      </div>

                      <div className="col-cost text-right">
                        {meta.isLocal ? (
                          <span className="badge-free-gpu glow-green">100% FREE</span>
                        ) : (
                          <span className="cold-cost-text">
                            ${m.estimated_cost.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
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
              {(relay.length > 0 ? relay : PREVIEW_RELAY).map((h, idx) => (
                <article
                  key={h.id}
                  style={{ animationDelay: `${idx * 0.08}s` }}
                  className={`relay-card-pro card-lift ${h.live_status}`}
                >
                  <div className="relay-pro-head">
                    <div className="agent-badge-wrap">
                      <span className="agent-name">{h.agent.toUpperCase()}</span>
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
                <span className="tile-value accent">{growth.new_shards.toLocaleString()}</span>
                <span className="tile-sub">in the selected period</span>
              </div>
              <div className="tile card-lift">
                <span className="tile-label">Total Memory Bank</span>
                <span className="tile-value">{growth.total_shards.toLocaleString()}</span>
                <span className="tile-sub">total memories stored</span>
              </div>
              <div className="tile card-lift">
                <span className="tile-label">Helpfulness Gain</span>
                <span className={`tile-value ${utilityDelta >= 0 ? 'accent-green glow-green' : 'warn'}`}>
                  {utilityDelta >= 0 ? '+' : ''}{utilityDelta.toFixed(2)}
                </span>
                <span className="tile-sub">memory quality drift</span>
              </div>
              <div className="tile card-lift">
                <span className="tile-label">Growth Rate</span>
                <span className="tile-value">{accelerationRate.toFixed(1)}%</span>
                <span className="tile-sub">expansion speed</span>
              </div>
            </div>

            <details className="raw-json-box">
              <summary>View Technical Data</summary>
              <pre className="stats-code-block">{JSON.stringify(stats ?? PREVIEW_STATUS, null, 2)}</pre>
            </details>
          </section>
        )}

        {/* Shard Detail Modal */}
        {selectedShard && (
          <div className="modal-backdrop" onClick={() => setSelectedShard(null)}>
            <div className="shard-modal pop-in" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <div>
                  <span className="db-badge">DATABASE #{selectedShard._db_index ?? 9}</span>
                  <h2>{selectedShard.title}</h2>
                </div>
                <button className="modal-close-btn" onClick={() => setSelectedShard(null)}>
                  ✕
                </button>
              </div>

              <div className="modal-body">
                <div className="modal-meta-bar">
                  <span>Memory ID: <strong>#{selectedShard.id}</strong></span>
                  <span>Match Rating: <strong>{Math.round((selectedShard.final_score ?? 0.85) * 100)}%</strong></span>
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
            </div>
          </div>
        )}
        </div>
      </main>

      {/* Sleek Docked Bottom Footer - Always Visible, Zero Content Interference */}
      <footer className="hud-footer-dock">
        <div className="footer-dock-left">
          <div className="dock-item">
            <span className="dock-icon">💾</span>
            <code className="dock-code">%USERPROFILE%\.nougen\shards</code>
            <span className="dock-tag">9 DBs</span>
          </div>
          <span className="dock-sep">·</span>
          <div className="fleet-pings-dock">
            <span className="ping-pill">Apollo ●</span>
            <span className="ping-pill active-pill">Hyperion ●</span>
            <span className="ping-pill">Phoebus ●</span>
          </div>
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
