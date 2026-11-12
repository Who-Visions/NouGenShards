import React from 'react';
import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import BatteryReader, { computeMeasuredDrain } from './BatteryReader';

describe('Cortex Hub battery reader', () => {
  it('outside the desktop app: says telemetry needs the desktop app and disables refresh', () => {
    const html = renderToStaticMarkup(<BatteryReader readBattery={async () => ({})} isDesktop={false} />);
    expect(html).toContain('aria-labelledby="battery-reader-title"');
    expect(html).toContain('available inside the Cortex Hub desktop app');
    expect(html).toMatch(/<button[^>]*class="battery-refresh"[^>]*disabled/);
  });

  it('inside the desktop app: starts its first reading and shows no web-only notice', () => {
    const html = renderToStaticMarkup(<BatteryReader readBattery={async () => ({ present: false })} isDesktop={true} />);
    expect(html).not.toContain('available inside the Cortex Hub desktop app');
    expect(html).toContain('Reading…');
  });

  it('measures drain across a continuous discharge window and resets across charging or gaps', () => {
    const min = 60_000;
    // Codex P2 repro: intervening Charging resets baseline so pre-charge 40 Wh isn't compared to 39.8 Wh.
    expect(computeMeasuredDrain([
      { at: 0, charge: 80, energy: 40.0, state: 'Discharging' },
      { at: 2 * min, charge: 82, energy: 40.8, state: 'Charging' },
      { at: 5 * min, charge: 79, energy: 39.8, state: 'Discharging' },
    ], true)).toBeNull();

    // After 5+ min continuous 1-min discharge samples post-charge, measure only post-charge interval (1.2 W, not 0.4 W).
    const postCharge = computeMeasuredDrain([
      { at: 0, charge: 80, energy: 40.0, state: 'Discharging' },
      { at: 2 * min, charge: 82, energy: 40.8, state: 'Charging' },
      { at: 5 * min, charge: 79, energy: 39.8, state: 'Discharging' },
      { at: 6 * min, charge: 78.8, energy: 39.78, state: 'Discharging' },
      { at: 7 * min, charge: 78.6, energy: 39.76, state: 'Discharging' },
      { at: 8 * min, charge: 78.4, energy: 39.74, state: 'Discharging' },
      { at: 9 * min, charge: 78.2, energy: 39.72, state: 'Discharging' },
      { at: 10 * min, charge: 78, energy: 39.7, state: 'Discharging' },
    ], true);
    expect(postCharge).not.toBeNull();
    expect(postCharge!).toBeCloseTo(1.2, 5);

    // Sampling gap > 3 min breaks continuity and clears stale baseline.
    expect(computeMeasuredDrain([
      { at: 0, charge: 80, energy: 40.0, state: 'Discharging' },
      { at: 5 * min, charge: 78, energy: 39.0, state: 'Discharging' },
    ], true)).toBeNull();
  });
});
