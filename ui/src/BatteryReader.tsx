import { useCallback, useEffect, useMemo, useState } from 'react';
import './battery-reader.css';

type BatterySnapshot = {
  present: boolean;
  chargePercent: number | null;
  healthPercent: number | null;
  energyWh: number | null;
  fullCapacityWh: number | null;
  designCapacityWh: number | null;
  dischargeWatts: number | null;
  timeToEmptyMinutes: number | null;
  cycleCount: number | null;
  state: string;
  observedAt: string;
};

type Sample = { at: number; charge: number; energy: number; state: string };
type HealthSample = { at: number; health: number; fullCapacity: number };

const HISTORY_KEY = 'nougen.cortex.battery.history.v1';
const HISTORY_WINDOW_MS = 24 * 60 * 60 * 1000;
const HEALTH_HISTORY_KEY = 'nougen.cortex.battery.health.v1';
const HEALTH_HISTORY_WINDOW_MS = 365 * 24 * 60 * 60 * 1000;
const POLL_INTERVAL_MS = 60_000;
const MAX_SAMPLE_GAP_MS = 3 * POLL_INTERVAL_MS;

export function computeMeasuredDrain(samples: Sample[], isDischarging: boolean): number | null {
  if (!isDischarging || samples.length < 2) return null;
  const latest = samples[samples.length - 1];
  if (!latest.state.includes('Discharging')) return null;

  let prior: Sample | null = null;
  for (let i = samples.length - 1; i >= 1; i--) {
    const curr = samples[i];
    const prev = samples[i - 1];
    if (!prev.state.includes('Discharging')) break;
    const stepMs = curr.at - prev.at;
    if (stepMs <= 0 || stepMs > MAX_SAMPLE_GAP_MS) break;
    if (latest.at - prev.at > 6 * 60 * 60_000) break;
    prior = prev;
  }
  if (!prior || latest.at - prior.at < 5 * 60_000) return null;
  const elapsedHours = (latest.at - prior.at) / 3_600_000;
  const watts = (prior.energy - latest.energy) / elapsedHours;
  return watts > 0.1 ? watts : null;
}

function loadHistory(): Sample[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(HISTORY_KEY) ?? '[]');
    if (!Array.isArray(value)) return [];
    return value.filter((entry): entry is Sample =>
      entry && typeof entry.at === 'number' && typeof entry.charge === 'number' &&
      typeof entry.energy === 'number' && typeof entry.state === 'string' &&
      Date.now() - entry.at < HISTORY_WINDOW_MS,
    ).slice(-1440);
  } catch {
    return [];
  }
}

function loadHealthHistory(): HealthSample[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(HEALTH_HISTORY_KEY) ?? '[]');
    if (!Array.isArray(value)) return [];
    return value.filter((entry): entry is HealthSample =>
      entry && typeof entry.at === 'number' && typeof entry.health === 'number' &&
      Number.isFinite(entry.health) && entry.health > 0 && entry.health <= 120 &&
      typeof entry.fullCapacity === 'number' && Number.isFinite(entry.fullCapacity) && entry.fullCapacity > 0 &&
      Date.now() - entry.at < HEALTH_HISTORY_WINDOW_MS,
    ).slice(-1000);
  } catch {
    return [];
  }
}

function estimateHealthTrend(history: HealthSample[]) {
  if (history.length < 3) return null;
  const ordered = [...history].sort((a, b) => a.at - b.at);
  if (ordered.at(-1)!.at - ordered[0].at < 14 * 24 * 60 * 60 * 1000) return null;

  // Theil–Sen slope resists individual OS capacity recalibration jumps.
  const slopes: number[] = [];
  for (let i = 0; i < ordered.length; i++) {
    for (let j = i + 1; j < ordered.length; j++) {
      const days = (ordered[j].at - ordered[i].at) / 86_400_000;
      if (days >= 7) slopes.push((ordered[j].health - ordered[i].health) / days);
    }
  }
  if (!slopes.length) return null;
  slopes.sort((a, b) => a - b);
  const dailySlope = slopes[Math.floor(slopes.length / 2)];
  const spanDays = (ordered.at(-1)!.at - ordered[0].at) / 86_400_000;
  if (dailySlope >= -0.0005 || dailySlope < -0.08) return null;

  const recent = ordered.filter((sample) => sample.at >= ordered.at(-1)!.at - 30 * 86_400_000);
  const oldest = recent[0] ?? ordered[0];
  const newest = ordered.at(-1)!;
  return {
    healthPerMonth: dailySlope * 30,
    daysTo80: Math.max(0, (newest.health - 80) / -dailySlope),
    currentHealth: newest.health,
    spanDays,
    points: ordered.length,
    baselineHealth: oldest.health,
    baselineAt: oldest.at,
  };
}

function formatTime(minutes: number | null) {
  if (minutes === null || !Number.isFinite(minutes) || minutes < 1) return '—';
  const hours = Math.floor(minutes / 60);
  const remainder = Math.round(minutes % 60);
  return hours > 0 ? `${hours}h ${remainder}m` : `${remainder}m`;
}

function formatWatts(value: number | null) {
  return value === null || !Number.isFinite(value) ? '—' : `${value.toFixed(1)} W`;
}

function BatteryTrend({ samples }: { samples: Sample[] }) {
  const points = samples.slice(-60);
  if (points.length < 2) {
    return <div className="battery-trend-empty"><span aria-hidden="true">◷</span><span>Collecting a baseline. Leave the reader open while unplugged to see the drain trend.</span></div>;
  }

  const min = Math.min(...points.map((point) => point.charge));
  const max = Math.max(...points.map((point) => point.charge));
  const span = max - min;
  const polyline = points.map((point, index) => {
    const x = (index / (points.length - 1)) * 100;
    // Flat line: plot at its absolute level instead of pinning it to the floor.
    const y = span > 0 ? 92 - ((point.charge - min) / span) * 76 : 92 - (point.charge / 100) * 76;
    return `${x},${y}`;
  }).join(' ');

  return (
    <div className="battery-chart-wrap">
      <svg className="battery-chart" viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Battery charge trend from this device's local samples">
        <line x1="0" y1="16" x2="100" y2="16" />
        <line x1="0" y1="54" x2="100" y2="54" />
        <line x1="0" y1="92" x2="100" y2="92" />
        <polyline points={polyline} />
      </svg>
      <div className="battery-chart-labels"><span>Oldest saved sample</span><span>Latest</span></div>
    </div>
  );
}

function Metric({ label, value, detail, mark }: { label: string; value: string; detail: string; mark: string }) {
  return (
    <article className="battery-metric">
      <div className="battery-metric-label"><span className="battery-mark" aria-hidden="true">{mark}</span><span>{label}</span></div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

export default function BatteryReader({ readBattery, isDesktop }: { readBattery: () => Promise<unknown>; isDesktop: boolean }) {
  const [reading, setReading] = useState<BatterySnapshot | null>(null);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [healthHistory, setHealthHistory] = useState<HealthSample[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);

  const refresh = useCallback(async (quiet = false) => {
    if (!isDesktop) {
      setLoading(false);
      return;
    }
    if (!quiet) setLoading(true);
    try {
      const next = await readBattery() as BatterySnapshot;
      setReading(next);
      setError(null);
      if (next.present && next.chargePercent !== null && next.energyWh !== null) {
        const at = Date.now();
        setSamples((previous) => {
          const last = previous.at(-1);
          if (last && at - last.at < 30_000) return previous;
          const retained = [...previous, { at, charge: next.chargePercent!, energy: next.energyWh!, state: next.state }]
            .filter((sample) => at - sample.at < HISTORY_WINDOW_MS)
            .slice(-1440);
          try { localStorage.setItem(HISTORY_KEY, JSON.stringify(retained)); } catch { /* local history is optional */ }
          return retained;
        });
        if (next.healthPercent !== null && next.fullCapacityWh !== null && next.fullCapacityWh > 0) {
          setHealthHistory((previous) => {
            const last = previous.at(-1);
            // Capacity readings update slowly. Keep one representative point per day.
            if (last && at - last.at < 20 * 60 * 60 * 1000) return previous;
            const retained = [...previous, { at, health: next.healthPercent!, fullCapacity: next.fullCapacityWh! }]
              .filter((sample) => at - sample.at < HEALTH_HISTORY_WINDOW_MS)
              .slice(-1000);
            try { localStorage.setItem(HEALTH_HISTORY_KEY, JSON.stringify(retained)); } catch { /* local history is optional */ }
            return retained;
          });
        }
      }
      setUpdatedAt(Date.now());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [isDesktop, readBattery]);

  useEffect(() => {
    setSamples(loadHistory());
    setHealthHistory(loadHealthHistory());
    if (!isDesktop) {
      setLoading(false);
      return;
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(true), POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [isDesktop, refresh]);

  const measuredDrain = useMemo(
    () => computeMeasuredDrain(samples, Boolean(reading?.state.includes('Discharging'))),
    [reading, samples],
  );

  const charge = reading?.chargePercent ?? 0;
  const health = reading?.healthPercent;
  const capacityLoss = health == null ? null : Math.max(0, 100 - health);
  const healthTrend = useMemo(() => estimateHealthTrend(healthHistory), [healthHistory]);
  const rate = measuredDrain ?? reading?.dischargeWatts ?? null;
  const rateLabel = measuredDrain !== null ? 'Measured from local samples' : 'Current OS estimate';
  const observedLabel = updatedAt ? new Date(updatedAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '—';

  return (
    <section className="panel fade-in battery-reader" aria-labelledby="battery-reader-title">
      <div className="battery-eyebrow">LOCAL DEVICE DIAGNOSTICS / BATTERY</div>
      <div className="battery-heading-row">
        <div>
          <h2 id="battery-reader-title">Battery Reader</h2>
          <p>A live view of charge, battery wear and measured discharge. Readings and history stay on this device.</p>
        </div>
        <button className="battery-refresh" type="button" onClick={() => void refresh()} disabled={loading || !isDesktop}>
          <span className={loading ? 'battery-spin' : ''} aria-hidden="true">↻</span>
          <span>{loading ? 'Reading…' : 'Refresh'}</span>
        </button>
      </div>

      {!isDesktop && <div className="battery-notice" role="status"><span aria-hidden="true">ⓘ</span><span>Battery telemetry is available inside the Cortex Hub desktop app.</span></div>}
      {error && <div className="battery-notice" role="alert"><span aria-hidden="true">!</span><span>{error}</span></div>}
      {!error && reading && !reading.present && <div className="battery-notice" role="status"><span aria-hidden="true">ⓘ</span><span>No battery was reported by the operating system. This reader is designed for laptops and battery-powered devices.</span></div>}

      {reading?.present && <>
        <div className="battery-hero">
          <div className="battery-charge-icon" aria-hidden="true">ϟ</div>
          <div className="battery-charge-copy">
            <span>Current charge</span>
            <strong>{Math.round(charge)}<small>%</small></strong>
            <p>{reading.state} · updated {observedLabel}</p>
          </div>
          <div className="battery-capacity-ring" aria-label={`${Math.round(charge)} percent charge`}>
            <div><span aria-hidden="true">▰</span><span>{Math.round(charge)}%</span></div>
            <div className="battery-capacity-ring-track" aria-hidden="true"><span style={{ width: `${Math.min(Math.max(charge, 0), 100)}%` }} /></div>
          </div>
        </div>

        <div className="battery-metrics-grid">
          <Metric label="Battery health" value={health == null ? 'Unavailable' : `${Math.round(health)}%`} detail={capacityLoss == null ? 'Not reported by this battery' : `${Math.round(capacityLoss)}% capacity wear`} mark="◉" />
          <Metric label="Discharge rate" value={formatWatts(rate)} detail={rateLabel} mark="ϟ" />
          <Metric label="Time remaining" value={formatTime(reading.timeToEmptyMinutes)} detail="Operating system estimate" mark="◷" />
          <Metric label="Charge cycles" value={reading.cycleCount === null ? 'Unavailable' : String(reading.cycleCount)} detail="Not all batteries report cycles" mark="↻" />
        </div>

        <div className="battery-detail-grid">
          <article className="battery-panel">
            <div className="battery-panel-heading"><div><span className="battery-eyebrow">CAPACITY</span><h3>What the battery can hold</h3></div></div>
            <div className="battery-capacity-lines">
              <div><span>Energy right now</span><strong>{reading.energyWh === null ? '—' : `${reading.energyWh.toFixed(1)} Wh`}</strong></div>
              <div><span>Full charge capacity</span><strong>{reading.fullCapacityWh === null ? '—' : `${reading.fullCapacityWh.toFixed(1)} Wh`}</strong></div>
              <div><span>Original design capacity</span><strong>{reading.designCapacityWh === null ? '—' : `${reading.designCapacityWh.toFixed(1)} Wh`}</strong></div>
            </div>
            {health != null && <div className="battery-capacity-track" aria-label={`Battery retains ${Math.round(health)} percent of design capacity`}><span style={{ width: `${Math.min(health, 100)}%` }} /></div>}
            <p className="battery-panel-footnote">Health compares full-charge capacity to original design capacity. It explains shorter runtime even when the charge percentage is high.</p>
          </article>
          <article className="battery-panel">
            <div className="battery-panel-heading"><div><span className="battery-eyebrow">LAST 24 HOURS</span><h3>Charge trend</h3></div><span className="battery-sample-count">{samples.length} samples</span></div>
            <BatteryTrend samples={samples} />
            <p className="battery-panel-footnote">Samples are stored locally on this device. Polling runs once per minute while this reader is open.</p>
          </article>
        </div>

        <article className="battery-panel battery-forecast">
          <div className="battery-panel-heading"><div><span className="battery-eyebrow">LONGITUDINAL CHECKUP</span><h3>Battery health outlook</h3></div><span className="battery-sample-count">{healthHistory.length} readings</span></div>
          {healthTrend ? <>
            <div className="battery-forecast-metrics">
              <div><span>Observed health trend</span><strong>{healthTrend.healthPerMonth.toFixed(2)} points / month</strong></div>
              <div><span>Modeled time to 80%</span><strong>{healthTrend.daysTo80 <= 0 ? 'Already below 80%' : healthTrend.daysTo80 < 3650 ? `${Math.round(healthTrend.daysTo80 / 30.4)} months` : '10+ years'}</strong></div>
            </div>
            <p className="battery-panel-footnote">Robust trend from {healthTrend.points} local daily readings across {Math.round(healthTrend.spanDays)} days. Based on this device’s reported capacity history; it is a straight-line estimate, not a cell-test or LLM prediction.</p>
          </> : <>
            <div className="battery-trend-empty"><span aria-hidden="true">⌁</span><span>Building a health baseline. Keep the reader open over the coming weeks; a forecast appears after at least 3 daily readings spanning 14 days.</span></div>
            <p className="battery-panel-footnote">Only health and full-capacity checkups are stored locally. The linked research uses controlled cell-cycle and temperature data that this laptop does not expose.</p>
          </>}
        </article>

        <div className="battery-insight">
          <div className="battery-insight-icon" aria-hidden="true">⌁</div>
          <div>
            <strong>{health != null && health < 80 ? 'Capacity wear is reducing runtime' : rate !== null && rate > 0 ? 'Discharge is being measured' : 'Gathering a discharge baseline'}</strong>
            <p>{health != null && health < 80
              ? `Your battery currently holds about ${Math.round(health)}% of its original design capacity. At a ${Math.round(charge)}% charge, available energy is about ${reading.energyWh?.toFixed(1) ?? '—'} Wh.`
              : rate !== null && rate > 0
                ? `The battery is currently using about ${rate.toFixed(1)} W. Keep the reader open to compare this with your observed charge trend.`
                : 'Leave the reader open while unplugged for several minutes. The trend will estimate drain from changing battery energy.'}</p>
          </div>
        </div>
        <p className="battery-reader-limit">This view measures the whole device. Windows does not provide reliable per-app wattage through this battery interface, so it will not guess which app is responsible.</p>
      </>}
    </section>
  );
}
